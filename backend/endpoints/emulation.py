import json
import os
from pathlib import Path

from fastapi import HTTPException, Query, Request

from decorators.auth import protected_route
from endpoints.responses.emulation import (
    EmulationGame,
    EmulationPlatform,
    EmulationProfile,
    EmulationProfileRequest,
    EmulationProfileResponse,
    EmulationStatus,
)
from handler.auth.constants import Scope
from handler.emulation.profiles import (
    ACTION_BUTTONS,
    BUTTONS,
    ID_PATTERN,
    PLATFORMS,
    SHORTCUTS,
    effective_profile,
    read_json,
    read_sessions,
    save_profile,
)
from models.user import Role
from utils.router import APIRouter

router = APIRouter(prefix="/emulation", tags=["emulation"])


def integration_root(request: Request) -> Path | None:
    if request.user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator access required")
    configured = os.environ.get("ROMM_EMULATION_PATH")
    return Path(configured) if configured else None


def require_root(request: Request) -> Path:
    root = integration_root(request)
    if root is None or not (root / "catalog.json").is_file():
        raise HTTPException(
            status_code=503, detail="Sunshine integration is not configured"
        )
    return root


def check_target(root: Path, system: str, game_id: str | None) -> None:
    if system not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Unknown platform")
    if game_id:
        try:
            games = read_json(root / "catalog.json", {"games": []})["games"]
            found = any(
                game["id"] == game_id and game["system"] == system for game in games
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise HTTPException(
                status_code=503, detail="Sunshine catalog is unavailable"
            ) from error
        if not found:
            raise HTTPException(
                status_code=404, detail="Game is not in the Sunshine catalog"
            )


def profile_response(
    root: Path, system: str, game_id: str | None
) -> EmulationProfileResponse:
    try:
        document = read_json(
            root / "profiles.json", {"revision": 0, "platforms": {}, "games": {}}
        )
        return EmulationProfileResponse(
            revision=document["revision"],
            saved=document["games" if game_id else "platforms"].get(
                game_id or system, {}
            ),
            inherited=EmulationProfile.model_validate(
                effective_profile(document if game_id else {}, system)
            ),
            effective=EmulationProfile.model_validate(
                effective_profile(document, system, game_id)
            ),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise HTTPException(
            status_code=503, detail="Sunshine profile data is unavailable"
        ) from error


@protected_route(router.get, "", [Scope.LOGS_READ])
def get_emulation(request: Request) -> EmulationStatus:
    root = integration_root(request)
    if root is None or not (root / "catalog.json").is_file():
        return EmulationStatus(enabled=False)
    try:
        catalog = read_json(root / "catalog.json", {"games": []})
        return EmulationStatus(
            enabled=True,
            updated=read_json(root / "status.json", {}).get("updated"),
            platforms=[
                EmulationPlatform(id=key, **value) for key, value in PLATFORMS.items()
            ],
            games=[EmulationGame(**game) for game in catalog["games"]],
            buttons=BUTTONS,
            action_buttons=ACTION_BUTTONS,
            shortcuts=SHORTCUTS,
            sessions=read_sessions(root),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise HTTPException(
            status_code=503, detail="Sunshine integration data is unavailable"
        ) from error


@protected_route(router.get, "/profiles/{system}", [Scope.LOGS_READ])
def get_profile(
    request: Request,
    system: str,
    game_id: str | None = Query(default=None, pattern=ID_PATTERN.pattern),
) -> EmulationProfileResponse:
    root = require_root(request)
    check_target(root, system, game_id)
    return profile_response(root, system, game_id)


@protected_route(router.put, "/profiles/{system}", [Scope.USERS_WRITE])
def put_profile(
    request: Request,
    system: str,
    payload: EmulationProfileRequest,
    game_id: str | None = Query(default=None, pattern=ID_PATTERN.pattern),
) -> EmulationProfileResponse:
    root = require_root(request)
    check_target(root, system, game_id)
    try:
        save_profile(
            root,
            system,
            game_id,
            payload.profile.model_dump(exclude_none=True),
            payload.revision,
        )
    except FileExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        raise HTTPException(
            status_code=503, detail="Sunshine profile data is unavailable"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=503, detail="Sunshine settings could not be saved"
        ) from error
    return profile_response(root, system, game_id)
