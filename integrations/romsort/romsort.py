#!/usr/bin/env python3
"""File completed downloads using RomM's content detector while preserving sources."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

SOURCE_BACKEND = Path(__file__).resolve().parents[2] / "backend"
DEPLOYED_CORE = Path("/data/emulators/operations/romm-intake")
sys.path.insert(0, str(SOURCE_BACKEND if SOURCE_BACKEND.is_dir() else DEPLOYED_CORE))

from handler.rom_identification import (  # noqa: E402
    CARTRIDGE_PLATFORMS,
    SIDECAR_EXTENSIONS,
    identify_path,
)
from utils.platform_slugs import UniversalPlatformSlug  # noqa: E402

VERSION = "content-v2"
PARTIAL_SUFFIXES = {".!qb", ".part", ".crdownload", ".tmp"}
DESCRIPTORS = {".cue", ".gdi", ".m3u"}


def files_in(path: Path) -> list[Path]:
    if path.is_symlink():
        raise ValueError("symlinks are not imported")
    if path.is_file():
        return [path]
    result = []
    for root, directories, filenames in os.walk(path, followlinks=False):
        for name in directories + filenames:
            child = Path(root) / name
            if child.is_symlink():
                raise ValueError("bundle contains a symlink")
        result.extend(Path(root) / name for name in sorted(filenames))
        if len(result) > 10000:
            raise ValueError("bundle exceeds the file limit")
    if any(not stat.S_ISREG(file.lstat().st_mode) for file in result):
        raise ValueError("bundle contains a special file")
    return sorted(result)


def signature(path: Path) -> str:
    digest = hashlib.sha256()
    for file in files_in(path):
        info = file.lstat()
        digest.update(
            json.dumps(
                [
                    str(file.relative_to(path) if path.is_dir() else file.name),
                    info.st_dev,
                    info.st_ino,
                    info.st_size,
                    info.st_mtime_ns,
                ],
            ).encode()
        )
    return digest.hexdigest()


def references(path: Path, bundle: Path) -> list[Path]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("disc descriptor exceeds the size limit")
    text = path.read_text(encoding="utf-8-sig")
    names = []
    if path.suffix.lower() == ".cue":
        names = re.findall(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+', text, re.I | re.M)
        names = [quoted or plain for quoted, plain in names]
    elif path.suffix.lower() == ".gdi":
        for line in text.splitlines()[1:]:
            match = re.fullmatch(
                r'\s*\d+\s+\d+\s+\d+\s+\d+\s+(?:"([^"]+)"|(\S+))\s+\d+\s*', line
            )
            if not match:
                raise ValueError("invalid GDI track entry")
            names.append(match[1] or match[2])
    else:
        names = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")
        ]
    if not names:
        raise ValueError("disc descriptor has no readable references")
    result = []
    for name in names:
        relative = Path(name.replace("\\", "/"))
        target = path.parent / relative
        if relative.is_absolute() or ".." in relative.parts or not target.is_file():
            raise ValueError("disc descriptor references an unsafe or missing file")
        if not target.resolve().is_relative_to(bundle.resolve()):
            raise ValueError("disc descriptor escapes its bundle")
        if any(
            part.is_symlink()
            for part in [target, *target.parents]
            if part.is_relative_to(bundle)
        ):
            raise ValueError("disc descriptor references a symlink")
        result.append(target)
    return result


def chd_index(library: Path) -> dict[str, set[str]]:
    result = {}
    for platform in library.iterdir():
        if (
            platform.is_symlink()
            or not platform.is_dir()
            or platform.name not in UniversalPlatformSlug._value2member_map_
            or platform.name in CARTRIDGE_PLATFORMS
        ):
            continue
        for file in platform.rglob("*.chd"):
            if (
                not file.is_file()
                or file.is_symlink()
                or any(parent.is_symlink() for parent in file.parents)
            ):
                continue
            match = identify_path(file)
            if match.chd_sha1:
                result.setdefault(match.chd_sha1, set()).add(platform.name)
    return result


def identify(item: Path, index: dict[str, set[str]]) -> tuple[str | None, str]:
    files = files_in(item)
    if not files or any(file.suffix.lower() in PARTIAL_SUFFIXES for file in files):
        return None, "empty bundle or download in progress"
    meaningful = [
        file
        for file in files
        if file.suffix.lower() not in SIDECAR_EXTENSIONS
        and not file.name.startswith(".")
    ]
    consumed = set()
    platforms = set()
    for descriptor in meaningful:
        if descriptor.suffix.lower() not in DESCRIPTORS:
            continue
        if not item.is_dir():
            return None, "disc descriptors must be imported with their track folder"
        pending = [descriptor]
        visited = set()
        track_platforms = set()
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            if path.suffix.lower() in DESCRIPTORS:
                pending.extend(references(path, item))
            else:
                match = identify_path(path)
                if match.invalid:
                    return None, "invalid archive in disc bundle"
                track_platforms.update(match.platforms)
                if match.chd_sha1:
                    track_platforms.update(index.get(match.chd_sha1, set()))
        if len(track_platforms) != 1:
            return None, "disc bundle has unknown or conflicting platform headers"
        platforms.update(track_platforms)
        consumed.update(visited)
    for file in meaningful:
        if file in consumed:
            continue
        match = identify_path(file)
        matches = set(match.platforms)
        if match.chd_sha1:
            matches.update(index.get(match.chd_sha1, set()))
        if match.invalid or len(matches) != 1:
            return None, f"{file.name}: {match.evidence}; choose a platform manually"
        platforms.update(matches)
    if len(platforms) != 1:
        return None, "bundle contains unknown or multiple platforms"
    return platforms.pop(), "content header or unique existing-library CHD match"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def identical(source: Path, target: Path) -> bool:
    if target.is_symlink() or source.is_dir() != target.is_dir():
        return False
    if not target.exists():
        return False
    sources, targets = files_in(source), files_in(target)
    if len(sources) != len(targets):
        return False
    for left, right in zip(sources, targets, strict=True):
        if source.is_dir() and left.relative_to(source) != right.relative_to(target):
            return False
        if left.stat().st_size != right.stat().st_size or digest(left) != digest(right):
            return False
    return True


def place(source: Path, target: Path, mode: str, before: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("platform destination is a symlink")
    stage = Path(tempfile.mkdtemp(prefix=".romsort-", dir=target.parent))
    payload = stage / source.name

    def copy(left, right):
        if mode == "link" or (
            mode == "auto" and Path(left).stat().st_dev == stage.stat().st_dev
        ):
            os.link(left, right, follow_symlinks=False)
            if not stat.S_ISREG(Path(right).lstat().st_mode):
                raise ValueError("source changed to a symlink")
        else:
            descriptor = os.open(left, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("source changed to a special file")
                with open(right, "xb") as output:
                    shutil.copyfileobj(stream, output)
            shutil.copystat(left, right, follow_symlinks=False)
        return right

    try:
        if source.is_dir():
            shutil.copytree(source, payload, copy_function=copy, symlinks=True)
            files_in(payload)
        else:
            copy(source, payload)
        if signature(source) != before:
            raise ValueError("source changed during import")
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)
        if payload.is_dir():
            os.rename(payload, target)
        else:
            os.link(payload, target, follow_symlinks=False)
    finally:
        shutil.rmtree(stage)


def run(inbox: Path, library: Path, mode: str, dry: bool, wait: float, index) -> None:
    ledger = inbox / ".romsort-content-v2.json"
    done = json.loads(ledger.read_text()) if ledger.exists() else {}
    items = []

    def collect(folder: Path, depth: int = 0):
        if depth > 10:
            print(f"SKIP {folder}: folder nesting exceeds the limit", flush=True)
            return
        children = [
            child
            for child in sorted(folder.iterdir())
            if not child.name.startswith((".", "_"))
        ]
        for item in children:
            if item.is_dir() and not item.is_symlink():
                contents = list(item.iterdir())
                descriptors = any(
                    child.suffix.lower() in DESCRIPTORS for child in contents
                )
                discs = [child for child in contents if child.is_dir()]
                multidisc = bool(discs) and all(
                    re.fullmatch(r"Disc\s+\d+", child.name, re.I) for child in discs
                )
                if descriptors or multidisc:
                    items.append(item)
                else:
                    collect(item, depth + 1)
            else:
                items.append(item)

    collect(inbox)
    pending = []
    for item in items:
        try:
            before = signature(item)
            if done.get(str(item.relative_to(inbox)), {}).get("signature") != before:
                pending.append((item, before))
        except (OSError, ValueError) as error:
            print(f"SKIP {item.name}: {error}", flush=True)
    if pending and not dry:
        time.sleep(wait)
    for item, before in pending:
        try:
            if signature(item) != before:
                print(f"SKIP {item.name}: still changing", flush=True)
                continue
            slug, reason = identify(item, index)
            state = "unresolved"
            if slug:
                target = library / slug / item.name
                if identical(item, target):
                    state = "duplicate"
                elif not dry:
                    place(item, target, mode, before)
                    state = "imported"
                else:
                    state = "would-import"
            print(f"{state.upper()} {item.name}: {slug or '?'} ({reason})", flush=True)
            if not dry:
                done[str(item.relative_to(inbox))] = {
                    "signature": before,
                    "state": state,
                    "platform": slug,
                    "reason": reason,
                    "version": VERSION,
                }
        except (OSError, ValueError, UnicodeError) as error:
            print(f"SKIP {item.name}: {error}", flush=True)
    if not dry:
        staging = ledger.with_suffix(".tmp")
        staging.write_text(json.dumps(done, indent=2) + "\n")
        staging.replace(ledger)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", nargs="+", type=Path)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--identify", nargs="+", type=Path)
    parser.add_argument("--mode", choices=["auto", "link", "copy"], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--settle-seconds", type=float, default=15)
    args = parser.parse_args()
    library = args.library.resolve(strict=True)
    index = chd_index(library)
    if args.identify:
        for item in args.identify:
            print(item, identify(item, index))
        return
    if not args.inbox:
        parser.error("--inbox is required")
    if args.settle_seconds < 0:
        parser.error("--settle-seconds must be nonnegative")
    with (library / ".romsort.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for inbox in args.inbox:
            if inbox.is_dir() and not inbox.is_symlink():
                resolved = inbox.resolve()
                if (
                    resolved == library
                    or resolved.is_relative_to(library)
                    or library.is_relative_to(resolved)
                ):
                    parser.error("inbox and library must be separate trees")
                run(
                    resolved,
                    library,
                    args.mode,
                    args.dry_run,
                    args.settle_seconds,
                    index,
                )


if __name__ == "__main__":
    main()
