"""Bounded platform identification from ROM headers and archive members."""

import io
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from utils.chd import CHD_SIGNATURE, CHD_V5_SHA1_LENGTH, CHD_V5_SHA1_OFFSET
from utils.platform_slugs import UniversalPlatformSlug as UPS

if TYPE_CHECKING:
    from handler.auth.rom_visibility import RomVisibilityFilter

HEAD_BYTES = 128 * 1024
TAIL_BYTES = 1024 * 1024
MAX_ARCHIVE_MEMBERS = 64
DISC_FORMATS = frozenset({"chd", "disc", "compressed-disc"})
CARTRIDGE_PLATFORMS = frozenset(
    {
        UPS.N64,
        UPS.NES,
        UPS.SNES,
        UPS.GENESIS,
        UPS.SEGA32,
        UPS.SEGA_PICO,
        UPS.SMS,
        UPS.GAMEGEAR,
        UPS.GB,
        UPS.GBC,
        UPS.GBA,
    }
)
SIDECAR_EXTENSIONS = frozenset(
    {".txt", ".nfo", ".xml", ".json", ".png", ".jpg", ".jpeg", ".webp", ".pdf"}
)


@dataclass
class Identification:
    format: str = "unknown"
    platforms: list[str] = field(default_factory=list)
    evidence: str = "unknown"
    invalid: bool = False
    chd_sha1: str | None = None
    members: list[str] = field(default_factory=list)
    contains_disc: bool = False
    partial_platforms: list[str] = field(default_factory=list)

    @property
    def incompatible_platforms(self) -> list[str]:
        blocked: set[UPS] = set()
        if self.format in DISC_FORMATS or self.contains_disc:
            blocked.update(CARTRIDGE_PLATFORMS)
        if self.partial_platforms:
            blocked.update(
                platform
                for platform in UPS
                if any(platform != known for known in self.partial_platforms)
            )
        return sorted(str(platform) for platform in blocked)


def identify_header(data: bytes) -> Identification:
    if data[:4] in (b"\x80\x37\x12\x40", b"\x37\x80\x40\x12", b"\x40\x12\x37\x80"):
        return Identification("cartridge", [UPS.N64], "header")
    if data[:4] == b"NES\x1a":
        return Identification("cartridge", [UPS.NES], "header")
    if data[:14] == b"SEGADISCSYSTEM":
        return Identification("disc", [UPS.SEGACD], "header")
    if data[0x100:0x108] == b"SEGA 32X":
        return Identification("cartridge", [UPS.SEGA32], "header")
    if data[0x100:0x109] == b"SEGA PICO":
        return Identification("cartridge", [UPS.SEGA_PICO], "header")
    if data[0x100:0x104] == b"SEGA":
        return Identification("cartridge", [UPS.GENESIS], "header")
    for offset in (0x1FF0, 0x3FF0, 0x7FF0):
        if data[offset : offset + 8] == b"TMR SEGA" and len(data) > offset + 15:
            region = data[offset + 15] >> 4
            platform = (
                UPS.GAMEGEAR
                if region in (5, 6, 7)
                else UPS.SMS if region in (3, 4) else None
            )
            return Identification("cartridge", [platform] if platform else [], "header")
    if data[:16] == b"SEGA SEGAKATANA ":
        return Identification("disc", [UPS.DC], "header")
    if data[:16] == b"SEGA SEGASATURN ":
        return Identification("disc", [UPS.SATURN], "header")
    if data[:12] == b"\0" + b"\xff" * 10 + b"\0":
        # Raw CD sectors carry the same boot header after their sector header.
        for offset in (16, 24):
            boot = data[offset : offset + 16]
            platform = {
                b"SEGA SEGAKATANA ": UPS.DC,
                b"SEGA SEGASATURN ": UPS.SATURN,
            }.get(boot)
            if platform:
                return Identification("disc", [platform], "header")
            if boot.startswith(b"SEGADISCSYSTEM"):
                return Identification("disc", [UPS.SEGACD], "header")
    if data[0x1C:0x20] == b"\xc2\x33\x9f\x3d":
        return Identification("disc", [UPS.NGC], "header")
    if data[0x18:0x1C] == b"\x5d\x1c\x9e\xa3":
        return Identification("disc", [UPS.WII], "header")
    if data[:4] in (b"RVZ\x01", b"WIA\x01"):
        # Dolphin stores the uncompressed disc type at 0x48 in both formats.
        platform = {1: UPS.NGC, 2: UPS.WII}.get(int.from_bytes(data[0x48:0x4C], "big"))
        return Identification(
            "compressed-disc", [platform] if platform else [], "header"
        )
    if data[0x10000:0x10014] == b"MICROSOFT*XBOX*MEDIA":
        return Identification("disc", [UPS.XBOX], "header")
    if data[:8] == CHD_SIGNATURE:
        digest = None
        if (
            len(data) >= CHD_V5_SHA1_OFFSET + CHD_V5_SHA1_LENGTH
            and data[12:16] == b"\0\0\0\x05"
        ):
            value = data[CHD_V5_SHA1_OFFSET : CHD_V5_SHA1_OFFSET + CHD_V5_SHA1_LENGTH]
            if any(value):
                digest = value.hex()
        return Identification("chd", evidence="container", chd_sha1=digest)
    for offset in (16 * 2048, 16 * 2352 + 16, 16 * 2352 + 24):
        descriptor = data[offset : offset + 7]
        if (
            len(descriptor) == 7
            and descriptor[0] in (0, 1, 2, 255)
            and descriptor[1:] == b"CD001\x01"
        ):
            return Identification("disc", evidence="container")
    return Identification()


class SampleUnavailable(OSError):
    pass


class SampleReader(io.RawIOBase):
    def __init__(self, size: int, head: bytes, tail: bytes):
        self.size, self.head, self.tail = size, head, tail
        self.position = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        self.position = offset + (
            self.position if whence == 1 else self.size if whence == 2 else 0
        )
        if self.position < 0:
            raise ValueError("Negative sample position")
        return self.position

    def read(self, size: int = -1) -> bytes:
        end = self.size if size < 0 else min(self.position + size, self.size)
        start = self.position
        if start >= self.size:
            return b""
        if end <= len(self.head):
            data = self.head[start:end]
        elif start >= self.size - len(self.tail):
            data = self.tail[
                start
                - (self.size - len(self.tail)) : end
                - (self.size - len(self.tail))
            ]
        else:
            raise SampleUnavailable("Requested bytes are outside the supplied sample")
        self.position = end
        return data


def identify_archive(stream: io.IOBase) -> Identification:
    try:
        # Reject enormous directories before ZipFile allocates member objects.
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - 65557))
        end = stream.read().rfind(b"PK\x05\x06")
        stream.seek(max(0, size - 65557) + max(end, 0))
        record = stream.read(22)
        if end < 0 or len(record) != 22:
            return Identification("zip", evidence="invalid-archive", invalid=True)
        count = int.from_bytes(record[10:12], "little")
        directory_size = int.from_bytes(record[12:16], "little")
        if count > MAX_ARCHIVE_MEMBERS or directory_size > TAIL_BYTES:
            return Identification("zip", evidence="archive-limit")
        with zipfile.ZipFile(stream) as archive:
            if len(archive.infolist()) > MAX_ARCHIVE_MEMBERS:
                return Identification("zip", evidence="archive-limit")
            entries = [
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
                and Path(entry.filename).suffix.lower() not in SIDECAR_EXTENSIONS
                and not any(
                    part.startswith(".") or part == "__MACOSX"
                    for part in Path(entry.filename).parts
                )
            ]
            names = [entry.filename for entry in entries]
            matches = []
            for entry in entries:
                try:
                    with archive.open(entry) as member:
                        matches.append(identify_header(member.read(0x10014)))
                except SampleUnavailable:
                    return Identification(
                        "zip", evidence="incomplete-sample", members=names
                    )
                except (RuntimeError, NotImplementedError):
                    return Identification(
                        "zip", evidence="unreadable-member", members=names
                    )
            platforms = sorted(
                {platform for match in matches for platform in match.platforms}
            )
            if len(platforms) > 1 or (
                matches and all(match.platforms for match in matches)
            ):
                return Identification(
                    "zip", platforms, "archive-headers", members=names
                )
            return Identification(
                "zip",
                evidence="unknown-members",
                members=names,
                contains_disc=any(match.format in DISC_FORMATS for match in matches),
                partial_platforms=platforms,
            )
    except SampleUnavailable:
        return Identification("zip", evidence="incomplete-sample")
    except (zipfile.BadZipFile, EOFError, ValueError, zlib.error):
        return Identification("zip", evidence="invalid-archive", invalid=True)


def identify_sample(
    filename: str, size: int, head: bytes, tail: bytes
) -> Identification:
    if not 0 <= len(head) <= min(size, HEAD_BYTES) or not 0 <= len(tail) <= min(
        size, TAIL_BYTES
    ):
        raise ValueError("Invalid sample length")
    if filename.lower().endswith(".zip") or head[:4] == b"PK\x03\x04":
        return identify_archive(SampleReader(size, head, tail))
    return identify_header(head)


def identify_path(path: Path, filename: str | None = None) -> Identification:
    with path.open("rb") as stream:
        head = stream.read(HEAD_BYTES)
        if (filename or path.name).lower().endswith(".zip") or head[
            :4
        ] == b"PK\x03\x04":
            return identify_archive(stream)
        return identify_header(head)


def platform_conflict(result: Identification, platform_slug: str) -> bool:
    if result.invalid:
        return True
    if result.platforms:
        return len(result.platforms) != 1 or platform_slug not in result.platforms
    return platform_slug in result.incompatible_platforms


def identify_library_match(
    result: Identification, visibility: RomVisibilityFilter, user_id: int
) -> Identification:
    if not result.chd_sha1:
        return result
    from handler.database import db_rom_handler

    matches = db_rom_handler.get_roms_scalar(
        search_term=result.chd_sha1,
        matched=True,
        missing=False,
        physical=False,
        include_files=True,
        visibility=visibility,
        user_id=user_id,
    )
    platforms = sorted(
        {
            rom.platform.slug
            for rom in matches
            if any(file.chd_sha1_hash == result.chd_sha1 for file in rom.files)
        }
        - CARTRIDGE_PLATFORMS
    )
    if len(platforms) == 1:
        result.platforms = platforms
        result.evidence = "library-hash"
    return result


def validate_platform_file(
    path: Path,
    filename: str,
    platform_slug: str,
    visibility: RomVisibilityFilter,
    user_id: int,
) -> None:
    result = identify_library_match(identify_path(path, filename), visibility, user_id)
    if platform_conflict(result, platform_slug):
        if result.invalid:
            reason = "The ZIP archive is invalid or incomplete"
        elif len(result.platforms) > 1:
            reason = "The archive contains games for different platforms"
        elif result.platforms:
            reason = (
                f"File contents identify {result.platforms[0]}, not {platform_slug}"
            )
        elif result.partial_platforms:
            reason = "The archive contains a file for " + ", ".join(
                result.partial_platforms
            )
        else:
            reason = f"A disc image cannot be uploaded as a {platform_slug} cartridge"
        raise ValueError(f"{filename}: {reason}")
