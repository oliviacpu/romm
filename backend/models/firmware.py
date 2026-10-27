from __future__ import annotations

import json
from functools import cache, cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, cast

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import (
    FILE_EXTENSION_MAX_LENGTH,
    FILE_NAME_MAX_LENGTH,
    FILE_PATH_MAX_LENGTH,
    BaseModel,
    FileNamePartsMixin,
)

if TYPE_CHECKING:
    from models.platform import Platform

FIRMWARE_FIXTURES_DIR: Final = Path(__file__).parent / "fixtures"


class FirmwareVerificationMatch(TypedDict):
    catalog: str
    file_names: list[str]


class FirmwareCatalogEntry(TypedDict, total=False):
    size: str
    crc: str
    md5: str
    sha1: str


class FirmwareCatalog(TypedDict):
    name: str
    file: str
    source_url: str


@cache
def _load_firmware_catalogs() -> (
    tuple[tuple[str, dict[str, FirmwareCatalogEntry]], ...]
):
    catalogs = cast(
        list[FirmwareCatalog],
        json.loads(
            (FIRMWARE_FIXTURES_DIR / "firmware_catalogs.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    return tuple(
        (
            catalog["name"],
            cast(
                dict[str, FirmwareCatalogEntry],
                json.loads(
                    (FIRMWARE_FIXTURES_DIR / catalog["file"]).read_text(
                        encoding="utf-8"
                    )
                ),
            ),
        )
        for catalog in catalogs
    )


class Firmware(FileNamePartsMixin, BaseModel):
    __tablename__ = "firmware"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform_id: Mapped[int] = mapped_column(
        ForeignKey("platforms.id", ondelete="CASCADE")
    )

    file_name: Mapped[str] = mapped_column(String(length=FILE_NAME_MAX_LENGTH))
    file_name_no_tags: Mapped[str] = mapped_column(String(length=FILE_NAME_MAX_LENGTH))
    file_name_no_ext: Mapped[str] = mapped_column(String(length=FILE_NAME_MAX_LENGTH))
    file_extension: Mapped[str] = mapped_column(
        String(length=FILE_EXTENSION_MAX_LENGTH)
    )
    file_path: Mapped[str] = mapped_column(String(length=FILE_PATH_MAX_LENGTH))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger(), default=0)

    crc_hash: Mapped[str] = mapped_column(String(length=100))
    md5_hash: Mapped[str] = mapped_column(String(length=100))
    sha1_hash: Mapped[str] = mapped_column(String(length=100))
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)

    platform: Mapped[Platform] = relationship(lazy="joined", back_populates="firmware")

    missing_from_fs: Mapped[bool] = mapped_column(default=False, nullable=False)

    @cached_property
    def full_path(self) -> str:
        return f"{self.file_path}/{self.file_name}"

    @property
    def verification_matches(self) -> list[FirmwareVerificationMatch]:
        return self.get_verification_matches(
            platform_slug=self.platform.slug,
            file_size_bytes=self.file_size_bytes,
            md5_hash=self.md5_hash,
            sha1_hash=self.sha1_hash,
            crc_hash=self.crc_hash,
        )

    @classmethod
    def verify_file_hashes(
        cls,
        platform_slug: str,
        file_name: str,
        file_size_bytes: int,
        md5_hash: str,
        sha1_hash: str,
        crc_hash: str,
    ) -> bool:
        return bool(
            cls.get_verification_matches(
                platform_slug=platform_slug,
                file_size_bytes=file_size_bytes,
                md5_hash=md5_hash,
                sha1_hash=sha1_hash,
                crc_hash=crc_hash,
            )
        )

    @classmethod
    def get_verification_matches(
        cls,
        platform_slug: str,
        file_size_bytes: int,
        md5_hash: str,
        sha1_hash: str,
        crc_hash: str,
    ) -> list[FirmwareVerificationMatch]:
        file_hashes = {
            "md5": md5_hash.lower(),
            "sha1": sha1_hash.lower(),
            "crc": crc_hash.lower(),
        }
        matches: list[FirmwareVerificationMatch] = []

        for catalog_name, catalog in _load_firmware_catalogs():
            matched_file_names: set[str] = set()
            for entry_key, entry in catalog.items():
                entry_platform, entry_file_name = entry_key.split(":", maxsplit=1)
                if entry_platform != platform_slug:
                    continue
                if int(entry.get("size", 0)) != file_size_bytes:
                    continue
                if any(
                    file_hashes[hash_name]
                    and file_hashes[hash_name] == entry.get(hash_name)
                    for hash_name in file_hashes
                ):
                    matched_file_names.add(entry_file_name)

            if matched_file_names:
                matches.append(
                    {
                        "catalog": catalog_name,
                        "file_names": sorted(matched_file_names),
                    }
                )

        return matches

    def __repr__(self) -> str:
        return self.file_name
