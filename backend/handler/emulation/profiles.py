"""Portable profile storage used by RomM and the emulator launcher."""

import fcntl
import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypedDict


class PlatformSpec(TypedDict):
    label: str
    buttons: dict[str, str]
    resolutions: list[str]
    widescreen: bool
    mapping: bool


BUTTONS = {
    "a": "A",
    "b": "B",
    "x": "X",
    "y": "Y",
    "lb": "LB",
    "rb": "RB",
    "lt": "LT",
    "rt": "RT",
    "view": "View (overlapping squares)",
    "menu": "Menu (three lines)",
    "l3": "Left stick click",
    "r3": "Right stick click",
    "up": "D-pad up",
    "down": "D-pad down",
    "left": "D-pad left",
    "right": "D-pad right",
}
ACTION_BUTTONS = BUTTONS | {
    "guide": "Xbox / Guide",
    "share": "Share (arrow out of tray)",
}
SHORTCUTS = {
    "both_sticks": ["l3", "r3"],
    "share": ["share"],
    "guide": ["guide"],
    "lb_rb": ["lb", "rb"],
    "l3_menu": ["l3", "menu"],
    "view_y": ["view", "y"],
    "none": [],
}
COMMON = {
    key: key
    for key in (
        "a",
        "b",
        "x",
        "y",
        "lb",
        "rb",
        "lt",
        "rt",
        "view",
        "menu",
        "l3",
        "r3",
        "up",
        "down",
        "left",
        "right",
    )
}
PLATFORMS: dict[str, PlatformSpec] = {
    "ps2": {
        "label": "PlayStation 2",
        "buttons": {
            "a": "Cross",
            "b": "Circle",
            "x": "Square",
            "y": "Triangle",
            "lb": "L1",
            "rb": "R1",
            "view": "Select",
            "menu": "Start",
            "l3": "L3",
            "r3": "R3",
        },
        "resolutions": ["native", "720p", "1080p", "1440p"],
        "widescreen": True,
        "mapping": True,
    },
    "gc": {
        "label": "GameCube",
        "buttons": {"a": "A", "b": "B", "x": "X", "y": "Y", "rb": "Z", "menu": "Start"},
        "resolutions": ["native", "720p", "1080p", "1440p"],
        "widescreen": True,
        "mapping": True,
    },
    "dreamcast": {
        "label": "Dreamcast",
        "buttons": {"a": "A", "b": "B", "x": "X", "y": "Y", "menu": "Start"},
        "resolutions": ["native", "720p", "1080p", "1440p"],
        "widescreen": True,
        "mapping": True,
    },
    "xbox": {
        "label": "Xbox",
        "buttons": {
            "a": "A",
            "b": "B",
            "x": "X",
            "y": "Y",
            "lb": "White",
            "rb": "Black",
            "view": "Back",
            "menu": "Start",
        },
        "resolutions": ["native"],
        "widescreen": False,
        "mapping": True,
    },
}
for _slug, _label in {
    "psx": "PlayStation",
    "nes": "NES",
    "snes": "Super Nintendo",
    "gb": "Game Boy",
    "gbc": "Game Boy Color",
    "gba": "Game Boy Advance",
    "genesis": "Genesis",
    "sms": "Master System",
    "gamegear": "Game Gear",
    "segacd": "Sega CD",
    "nds": "Nintendo DS",
    "n64": "Nintendo 64",
}.items():
    PLATFORMS[_slug] = {
        "label": _label,
        "buttons": {
            "a": "RetroPad B (south)",
            "b": "RetroPad A (east)",
            "x": "RetroPad Y (west)",
            "y": "RetroPad X (north)",
            "lb": "L",
            "rb": "R",
            "view": "Select",
            "menu": "Start",
            "l3": "L3",
            "r3": "R3",
        },
        "resolutions": ["native"],
        "widescreen": False,
        "mapping": True,
    }

CONSOLE_BUTTONS = {
    "psx": {
        "a": "Cross",
        "b": "Circle",
        "x": "Square",
        "y": "Triangle",
        "lb": "L1",
        "rb": "R1",
        "view": "Select",
        "menu": "Start",
    },
    "nes": {"a": "B", "b": "A", "view": "Select", "menu": "Start"},
    "gb": {"a": "B", "b": "A", "view": "Select", "menu": "Start"},
    "gbc": {"a": "B", "b": "A", "view": "Select", "menu": "Start"},
    "gba": {
        "a": "B",
        "b": "A",
        "lb": "L",
        "rb": "R",
        "view": "Select",
        "menu": "Start",
    },
    "snes": {
        "a": "B",
        "b": "A",
        "x": "Y",
        "y": "X",
        "lb": "L",
        "rb": "R",
        "view": "Select",
        "menu": "Start",
    },
    "nds": {
        "a": "B",
        "b": "A",
        "x": "Y",
        "y": "X",
        "lb": "L",
        "rb": "R",
        "view": "Select",
        "menu": "Start",
    },
    "n64": {
        "a": "A",
        "x": "B",
        "b": "C-right",
        "y": "C-up",
        "lb": "L",
        "rb": "R",
        "menu": "Start",
    },
    "genesis": {
        "x": "A",
        "a": "B",
        "b": "C",
        "lb": "X",
        "y": "Y",
        "rb": "Z",
        "menu": "Start",
    },
    "segacd": {
        "x": "A",
        "a": "B",
        "b": "C",
        "lb": "X",
        "y": "Y",
        "rb": "Z",
        "menu": "Start",
    },
    "sms": {"a": "1", "b": "2", "menu": "Pause"},
    "gamegear": {"a": "1", "b": "2", "menu": "Start"},
}
for _system, _buttons in CONSOLE_BUTTONS.items():
    PLATFORMS[_system]["buttons"] = _buttons
for _spec in PLATFORMS.values():
    _spec["buttons"].update(
        {key: BUTTONS[key] for key in ("up", "down", "left", "right")}
    )
for _system in ("ps2", "psx"):
    PLATFORMS[_system]["buttons"].update({"lt": "L2", "rt": "R2"})
for _system in ("gc", "dreamcast", "xbox"):
    PLATFORMS[_system]["buttons"].update({"lt": "L trigger", "rt": "R trigger"})
PLATFORMS["n64"]["buttons"].update({"lt": "Z", "rt": "C buttons mode"})
NINTENDO_SYSTEMS = {"nes", "snes", "gb", "gbc", "gba", "nds"}


DEFAULT_PROFILE = {
    "resolution": "native",
    "aspect": "original",
    "osd_scale": 200,
    "bindings": {},
    "menu_shortcut": "both_sticks",
    "quit_shortcut": "l3_menu",
}
MAX_SESSIONS = 30
MAX_MESSAGES = 40
MAX_MESSAGE_LENGTH = 1500
MAX_JSON_BYTES = 4 * 1024 * 1024
# JSON escaping can use six bytes per character; reserve space for session metadata.
MAX_SESSION_BYTES = MAX_SESSIONS * MAX_MESSAGES * MAX_MESSAGE_LENGTH * 6 + 1024 * 1024
ID_PATTERN = re.compile(r"^[a-f0-9]{20}$")


def read_json(path: Path, default: Any, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    try:
        if path.stat().st_size > max_bytes:
            raise ValueError("Integration file exceeds size limit")
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def read_sessions(root: Path) -> Any:
    return read_json(root / "sessions.json", [], max_bytes=MAX_SESSION_BYTES)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        name = output.name
        try:
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
            os.chmod(name, 0o644)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)


@contextmanager
def locked(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".profiles.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def validate_profile(system: str, profile: dict[str, Any]) -> dict[str, Any]:
    if system not in PLATFORMS or not isinstance(profile, dict):
        raise ValueError("Unknown platform or invalid profile")
    if set(profile) - set(DEFAULT_PROFILE):
        raise ValueError("Unknown profile setting")
    capabilities = PLATFORMS[system]
    if profile.get("resolution", "native") not in capabilities["resolutions"]:
        raise ValueError("Resolution is not supported by this adapter")
    if profile.get("aspect", "original") not in ("original", "16:9", "auto"):
        raise ValueError("Unknown aspect ratio")
    if profile.get("aspect") == "auto" and system != "ps2":
        raise ValueError("Automatic widescreen patches are only available for PS2")
    if profile.get("aspect") == "16:9" and not capabilities["widescreen"]:
        raise ValueError("Widescreen must be configured in the game or emulator")
    scale = profile.get("osd_scale", 200)
    if type(scale) is not int or not 100 <= scale <= 300:
        raise ValueError("Message size must be between 100 and 300 percent")
    for action in ("menu", "quit"):
        shortcut = profile.get(
            action + "_shortcut", DEFAULT_PROFILE[action + "_shortcut"]
        )
        if not isinstance(shortcut, str) or shortcut not in SHORTCUTS:
            raise ValueError("Unknown controller shortcut")
        if action == "quit" and shortcut == "none":
            raise ValueError("A quit shortcut is required")
    if system == "gc" and profile.get("menu_shortcut", "none") != "none":
        raise ValueError("Dolphin does not provide a controller-operated emulator menu")
    bindings = profile.get("bindings", {})
    if not isinstance(bindings, dict) or len(bindings) > len(BUTTONS):
        raise ValueError("Invalid controller mapping")
    if bindings and not capabilities["mapping"]:
        raise ValueError("This emulator adapter does not support button remapping yet")
    if any(
        key not in COMMON or value not in BUTTONS for key, value in bindings.items()
    ):
        raise ValueError("Unknown controller button")
    if any(
        (key in ("lt", "rt")) != (value in ("lt", "rt"))
        for key, value in bindings.items()
    ):
        raise ValueError("Analog triggers can only be mapped to analog triggers")
    return profile


def effective_profile(
    document: dict[str, Any], system: str, game_id: str | None = None
) -> dict[str, Any]:
    platform = validate_profile(system, document.get("platforms", {}).get(system, {}))
    game = validate_profile(system, document.get("games", {}).get(game_id, {}))
    result: dict[str, Any] = (
        DEFAULT_PROFILE
        | ({"aspect": "auto"} if system == "ps2" else {})
        | ({"menu_shortcut": "none"} if system == "gc" else {})
        | platform
        | game
    )
    if result["menu_shortcut"] == result["quit_shortcut"]:
        raise ValueError("Menu and quit must use different shortcuts")
    default_bindings = COMMON | (
        {"a": "b", "b": "a", "x": "y", "y": "x"} if system in NINTENDO_SYSTEMS else {}
    )
    if system == "n64":
        default_bindings |= {"x": "b", "b": "x"}
    result["bindings"] = (
        default_bindings | platform.get("bindings", {}) | game.get("bindings", {})
    )
    if len(set(result["bindings"].values())) != len(result["bindings"]):
        raise ValueError(
            "Each Xbox input must have one assignment. Swap both buttons together."
        )
    return result


def save_profile(
    root: Path, system: str, game_id: str | None, profile: dict[str, Any], revision: int
) -> dict[str, Any]:
    validate_profile(system, profile)
    if game_id is not None and not ID_PATTERN.fullmatch(game_id):
        raise ValueError("Invalid Sunshine game identity")
    with locked(root):
        document: dict[str, Any] = read_json(
            root / "profiles.json", {"revision": 0, "platforms": {}, "games": {}}
        )
        if document["revision"] != revision:
            raise FileExistsError("Settings changed elsewhere. Reload before saving.")
        document["games" if game_id else "platforms"][game_id or system] = profile
        effective_profile(document, system, game_id)
        if game_id is None:
            catalog = read_json(root / "catalog.json", {"games": []})
            for game in catalog["games"]:
                if game["system"] == system and game["id"] in document["games"]:
                    try:
                        effective_profile(document, system, game["id"])
                    except ValueError as error:
                        raise ValueError(
                            "Platform changes conflict with a game override. "
                            "Clear that game's overrides before saving."
                        ) from error
        document["revision"] += 1
        atomic_json(root / "profiles.json", document)
        return document
