from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from handler.emulation.profiles import BUTTONS


class EmulationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: Literal["native", "720p", "1080p", "1440p"] | None = None
    aspect: Literal["original", "16:9", "auto"] | None = None
    osd_scale: int | None = Field(default=None, ge=100, le=300)
    bindings: dict[str, str] = Field(default_factory=dict, max_length=len(BUTTONS))


class EmulationProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=0)
    profile: EmulationProfile


class EmulationProfileResponse(BaseModel):
    revision: int
    saved: EmulationProfile
    inherited: EmulationProfile
    effective: EmulationProfile


class EmulationPlatform(BaseModel):
    id: str
    label: str
    buttons: dict[str, str]
    resolutions: list[str]
    widescreen: bool
    mapping: bool


class EmulationGame(BaseModel):
    id: str
    title: str
    system: str


class EmulationMessage(BaseModel):
    timestamp: float
    level: Literal["info", "warning", "error"]
    source: str
    text: str = Field(max_length=1500)


class EmulationSession(BaseModel):
    id: str
    system: str
    game: str
    started: float
    ended: float | None = None
    messages: list[EmulationMessage]


class EmulationStatus(BaseModel):
    enabled: bool
    updated: float | None = None
    platforms: list[EmulationPlatform] = Field(default_factory=list)
    games: list[EmulationGame] = Field(default_factory=list)
    buttons: dict[str, str] = Field(default_factory=dict)
    sessions: list[EmulationSession] = Field(default_factory=list)
