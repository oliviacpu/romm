from typing import Self, TypedDict

from pydantic import ConfigDict, model_validator

from .base import BaseModel, UTCDatetime


class FirmwareVerificationMatchSchema(BaseModel):
    catalog: str
    file_names: list[str]


class FirmwareSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform_id: int

    file_name: str
    file_name_no_tags: str
    file_name_no_ext: str
    file_extension: str
    file_path: str
    file_size_bytes: int

    full_path: str
    is_verified: bool
    verification_matches: list[FirmwareVerificationMatchSchema]
    crc_hash: str
    md5_hash: str
    sha1_hash: str

    missing_from_fs: bool

    created_at: UTCDatetime
    updated_at: UTCDatetime

    @model_validator(mode="after")
    def set_verified_from_catalog_matches(self) -> Self:
        self.is_verified = bool(self.verification_matches)
        return self


class AddFirmwareResponse(TypedDict):
    uploaded: int
    firmware: list[FirmwareSchema]
