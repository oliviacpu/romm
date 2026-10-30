from typing import Annotated

from pydantic import Base64Bytes, BaseModel, Field

from handler.rom_identification import HEAD_BYTES, TAIL_BYTES


class RomInspectionSample(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=2**63 - 1)
    head: Annotated[Base64Bytes, Field(max_length=HEAD_BYTES)]
    tail: Annotated[Base64Bytes, Field(max_length=TAIL_BYTES)]


class RomInspectionLimits(BaseModel):
    head_bytes: int
    tail_bytes: int


class RomInspectionResult(BaseModel):
    format: str
    platforms: list[str]
    evidence: str
    invalid: bool
    members: list[str]
    incompatible_platforms: list[str]
