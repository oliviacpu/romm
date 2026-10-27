"""Stage a complete game folder before making it visible to the ROM scanner."""

import ctypes
import errno
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import uuid4

from handler.filesystem import fs_rom_handler
from handler.rom_upload import (
    UploadConflictException,
    UploadDestination,
    UploadRejectedException,
    parse_upload_folder,
    resolve_platform_upload_destination,
    sanitize_upload_filename,
)
from handler.upload_policy import folder_upload_error, upload_policies

MAX_FILES = 256
MAX_GAME_SIZE = 20 * 1024 * 1024 * 1024
STAGING_AGE = 24 * 60 * 60
STAGING_PREFIX = ".romm-upload-"


def _platform_dir(fs_slug: str) -> Path:
    return fs_rom_handler.validate_path(fs_rom_handler.get_roms_upload_path(fs_slug))


def _stage_dir(fs_slug: str, batch_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", batch_id):
        raise UploadRejectedException("Invalid game upload ID")
    return _platform_dir(fs_slug) / f"{STAGING_PREFIX}{batch_id}"


def _safe_game_name(name: str) -> str:
    if not isinstance(name, str) or name.startswith(".") or name != name.strip():
        raise UploadRejectedException("Choose a game folder name")
    parsed = parse_upload_folder(name)
    if not parsed or "/" in parsed:
        raise UploadRejectedException("Game name must be one folder name")
    return parsed


def _safe_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path or path.startswith("/"):
        raise UploadRejectedException("Invalid game file path")
    parts = path.split("/")
    if len(parts) > 12 or any(not part or part.startswith(".") for part in parts):
        raise UploadRejectedException(
            "Game files cannot use hidden or deeply nested folders"
        )
    folder = parse_upload_folder("/".join(parts[:-1]))
    filename = sanitize_upload_filename(parts[-1])
    if filename != parts[-1]:
        raise UploadRejectedException("Invalid game file name")
    return f"{folder}/{filename}" if folder else filename


def _cleanup_expired(platform: Path) -> None:
    now = time.time()
    for path in platform.iterdir():
        if (
            path.name.startswith(STAGING_PREFIX)
            and path.is_dir()
            and not path.is_symlink()
            and now - path.stat().st_mtime > STAGING_AGE
        ):
            shutil.rmtree(path)


def start_batch(
    fs_slug: str,
    platform_id: int,
    user_id: int,
    name: str,
    files: list[dict[str, int | str]],
) -> str:
    game_name = _safe_game_name(name)
    if not 1 <= len(files) <= MAX_FILES:
        raise UploadRejectedException("Choose 1 to 256 files for one game")
    expected: dict[str, int] = {}
    total = 0
    for file in files:
        raw_path = file.get("path", "")
        if not isinstance(raw_path, str):
            raise UploadRejectedException("Invalid game file path")
        path = _safe_relative_path(raw_path)
        size = file.get("size")
        if type(size) is not int or size <= 0:
            raise UploadRejectedException("Game files must not be empty")
        if path.casefold() in (item.casefold() for item in expected):
            raise UploadRejectedException("Game folder has duplicate file paths")
        expected[path] = size
        total += size
    if total > MAX_GAME_SIZE:
        raise UploadRejectedException("Game folder exceeds the 20 GiB upload limit")
    if error := folder_upload_error(fs_slug, list(expected)):
        raise UploadRejectedException(error)

    platform = _platform_dir(fs_slug)
    platform.mkdir(parents=True, exist_ok=True)
    _cleanup_expired(platform)
    if (platform / game_name).exists():
        raise UploadConflictException("That game folder already exists")
    if shutil.disk_usage(platform).free < total + 512 * 1024 * 1024:
        raise UploadRejectedException("Not enough free space for this game")

    batch_id = uuid4().hex
    stage = _stage_dir(fs_slug, batch_id)
    stage.mkdir(mode=0o700)
    try:
        (stage / "game").mkdir(mode=0o700)
        manifest = {
            "platform_id": platform_id,
            "user_id": user_id,
            "name": game_name,
            "files": expected,
        }
        with (stage / "manifest.json").open("x") as output:
            json.dump(manifest, output)
        (stage / "manifest.json").chmod(0o600)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return batch_id


def load_batch(
    fs_slug: str, batch_id: str, platform_id: int, user_id: int
) -> dict[str, Any]:
    stage = _stage_dir(fs_slug, batch_id)
    if stage.is_symlink() or not stage.is_dir():
        raise UploadRejectedException("Game upload expired or was cancelled")
    try:
        manifest = cast(
            dict[str, Any], json.loads((stage / "manifest.json").read_text())
        )
    except (OSError, ValueError) as exc:
        raise UploadRejectedException("Game upload manifest is unavailable") from exc
    if manifest.get("platform_id") != platform_id or manifest.get("user_id") != user_id:
        raise UploadRejectedException("Game upload does not belong to this account")
    return manifest


def resolve_batch_destination(
    fs_slug: str,
    batch_id: str,
    platform_id: int,
    user_id: int,
    folder: str,
    filename: str,
    size: int,
) -> UploadDestination:
    manifest = load_batch(fs_slug, batch_id, platform_id, user_id)
    relative = _safe_relative_path(f"{folder}/{filename}" if folder else filename)
    if manifest["files"].get(relative) != size:
        raise UploadRejectedException("File is not in this game upload")
    stage_folder = f"{STAGING_PREFIX}{batch_id}/game"
    if folder:
        stage_folder += f"/{folder}"
    return resolve_platform_upload_destination(fs_slug, stage_folder, filename)


def _validate_tracks(root: Path) -> set[Path]:
    referenced: set[Path] = set()
    for descriptor in root.rglob("*"):
        if not descriptor.is_file() or descriptor.suffix.lower() not in (
            ".gdi",
            ".cue",
        ):
            continue
        lines = descriptor.read_text(errors="replace").splitlines()
        if descriptor.suffix.lower() == ".gdi":
            if (
                not lines
                or not lines[0].strip().isdigit()
                or int(lines[0]) != len(lines) - 1
            ):
                raise UploadRejectedException(
                    f"Invalid GDI track list: {descriptor.name}"
                )
            names = []
            for line in lines[1:]:
                try:
                    parts = shlex.split(line)
                except ValueError as exc:
                    raise UploadRejectedException(
                        f"Invalid GDI track entry: {descriptor.name}"
                    ) from exc
                if len(parts) < 6:
                    raise UploadRejectedException(
                        f"Invalid GDI track entry: {descriptor.name}"
                    )
                names.append(parts[4])
        else:
            names = []
            for line in lines:
                if line.lstrip().upper().startswith("FILE "):
                    try:
                        parts = shlex.split(line)
                    except ValueError as exc:
                        raise UploadRejectedException(
                            f"Invalid CUE track entry: {descriptor.name}"
                        ) from exc
                    if len(parts) < 3:
                        raise UploadRejectedException(
                            f"Invalid CUE track entry: {descriptor.name}"
                        )
                    names.append(parts[1])
        if not names:
            raise UploadRejectedException(f"No tracks listed in {descriptor.name}")
        for name in names:
            track_name = PurePosixPath(name)
            if track_name.is_absolute() or ".." in track_name.parts:
                raise UploadRejectedException(f"Track path escapes {descriptor.name}")
            track = descriptor.parent / name
            if not track.is_file() or track.is_symlink() or track.stat().st_size == 0:
                raise UploadRejectedException(
                    f"Missing track {name} for {descriptor.name}"
                )
            referenced.add(track.resolve())
    return referenced


def _move_exclusive(source: Path, destination: Path) -> None:
    if sys.platform == "linux":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
            code = ctypes.get_errno()
            if code == errno.EEXIST:
                raise UploadConflictException("That game folder already exists")
            raise OSError(code, os.strerror(code), str(destination))
    else:
        destination.mkdir()
        try:
            source.rename(destination)
        except BaseException:
            destination.rmdir()
            raise


def finish_batch(fs_slug: str, batch_id: str, platform_id: int, user_id: int) -> str:
    manifest = load_batch(fs_slug, batch_id, platform_id, user_id)
    stage = _stage_dir(fs_slug, batch_id)
    source = stage / "game"
    expected = manifest["files"]
    for path, size in expected.items():
        target = source / path
        if not target.is_file() or target.is_symlink() or target.stat().st_size != size:
            raise UploadRejectedException(f"Game file is missing or incomplete: {path}")
    actual = {
        str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()
    }
    if actual != set(expected):
        raise UploadRejectedException("Game folder contains unexpected files")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise UploadRejectedException("Game folder cannot contain symlinks")
    referenced = _validate_tracks(source)
    policy = upload_policies().get(fs_slug)
    if policy:
        for path in source.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in policy.companions
                and path.resolve() not in referenced
            ):
                raise UploadRejectedException(
                    f"Track file is not listed by a GDI or CUE: {path.name}"
                )
    destination = _platform_dir(fs_slug) / manifest["name"]
    _move_exclusive(source, destination)
    shutil.rmtree(stage)
    return cast(str, manifest["name"])


def cancel_batch(fs_slug: str, batch_id: str, platform_id: int, user_id: int) -> None:
    load_batch(fs_slug, batch_id, platform_id, user_id)
    shutil.rmtree(_stage_dir(fs_slug, batch_id))
