"""Apply RomM profiles and retain bounded emulator session messages."""

import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

import profiles

ROOT = Path("/config/integration")
CONFIG = Path("/config")
message_lock = threading.RLock()
SDL_BUTTONS = {
    "lt": "+LeftTrigger",
    "rt": "+RightTrigger",
    "a": "FaceSouth",
    "b": "FaceEast",
    "x": "FaceWest",
    "y": "FaceNorth",
    "lb": "LeftShoulder",
    "rb": "RightShoulder",
    "view": "Back",
    "menu": "Start",
    "l3": "LeftStick",
    "r3": "RightStick",
    "up": "DPadUp",
    "down": "DPadDown",
    "left": "DPadLeft",
    "right": "DPadRight",
}
DOLPHIN_BUTTONS = {
    "lt": "Trigger L",
    "rt": "Trigger R",
    "a": "Button S",
    "b": "Button E",
    "x": "Button W",
    "y": "Button N",
    "lb": "Shoulder L",
    "rb": "Shoulder R",
    "view": "Back",
    "menu": "Start",
    "l3": "Thumb L",
    "r3": "Thumb R",
    "up": "Pad N",
    "down": "Pad S",
    "left": "Pad W",
    "right": "Pad E",
}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
WARNING = re.compile(
    r"\b(warn(?:ing)?|error|fatal|unsafe|failed)\b|OSD \[HW\w+Warning\]", re.I
)
MESSAGE = re.compile(WARNING.pattern + r"|\bOSD\b|Patch: Setting aspect ratio", re.I)
CONTINUATION = re.compile(
    r"^(Recommended |You can |This game |This may |graphical quality|accuracy,|quality,)",
    re.I,
)
SOURCES = {"ps2": "PCSX2", "gc": "Dolphin", "dreamcast": "Flycast", "xbox": "xemu"}
active_session_id = None
# Measured against Sunshine's pinned Linux uinput Xbox Series descriptor.
SERIES_GUID = "05004d885e040000130b000000050000"
SERIES_MAPPING = (
    SERIES_GUID + ",Xbox Series X Controller,a:b0,b:b1,x:b3,y:b4,back:b10,guide:b12,"
    "start:b11,leftstick:b13,rightstick:b14,leftshoulder:b6,rightshoulder:b7,"
    "dpup:h0.1,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,misc1:b15,"
    "leftx:a0,lefty:a1,rightx:a3,righty:a4,lefttrigger:a2,righttrigger:a5,platform:Linux,"
)
SDL_KEYS = {
    "lt": "lefttrigger",
    "rt": "righttrigger",
    "a": "a",
    "b": "b",
    "x": "x",
    "y": "y",
    "lb": "leftshoulder",
    "rb": "rightshoulder",
    "view": "back",
    "menu": "start",
    "l3": "leftstick",
    "r3": "rightstick",
    "up": "dpup",
    "down": "dpdown",
    "left": "dpleft",
    "right": "dpright",
}


def write_owned(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    stat = path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        name = output.name
        try:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
            os.chmod(name, stat.st_mode & 0o777 if stat else 0o644)
            os.chown(
                name, stat.st_uid if stat else 20000, stat.st_gid if stat else 20000
            )
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)


def update_ini(path, updates):
    text = path.read_text() if path.exists() else ""
    pending = {section: dict(values) for section, values in updates.items()}
    result = []
    section = None

    def emit(key, value):
        result.extend(
            f"{key} = {item}\n"
            for item in (value if isinstance(value, list) else [value])
        )

    def finish():
        for key, value in pending.get(section, {}).items():
            emit(key, value)
        pending.pop(section, None)

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            finish()
            section = stripped[1:-1]
        if section in updates and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates[section]:
                if key in pending.get(section, {}):
                    emit(key, pending[section].pop(key))
                continue
        result.append(line if line.endswith("\n") else line + "\n")
    finish()
    for section, values in pending.items():
        result.append(f"\n[{section}]\n")
        for key, value in values.items():
            emit(key, value)
    write_owned(path, "".join(result))


def game_identity(system, rom):
    from systems import SYSTEMS

    folder = Path("/library/roms") / SYSTEMS[system].romm_platform
    relative = str(rom.relative_to(folder.resolve()))
    import catalog

    cards = catalog.load_json(CONFIG / "catalog/cards.json", {"cards": {}})["cards"]
    return next(
        (
            key
            for key, value in cards.items()
            if value["system"] == system and value["path"] == relative
        ),
        None,
    )


def series_controller():
    path = CONFIG / "sunshine/sunshine.conf"
    return path.is_file() and any(
        line.strip() == "gamepad = xseries" for line in path.read_text().splitlines()
    )


def controller_environment(profile):
    bindings = profile["bindings"]
    if bindings == profiles.COMMON:
        return {}
    database = CONFIG / "pcsx2/PCSX2/game_controller_db.txt"
    candidates = [
        line
        for line in database.read_text().splitlines()
        if ",Xbox 360 via Sunshine," in line and "platform:Linux" in line
    ]
    if series_controller():
        candidates.append(SERIES_MAPPING)
    if not candidates:
        raise ValueError(
            "Sunshine controller baseline is missing; remapping cannot be applied safely"
        )
    mappings = []
    for line in candidates:
        guid, name, *fields = line.split(",")
        original = dict(field.split(":", 1) for field in fields if ":" in field)
        mapped = dict(original)
        for target, source in bindings.items():
            mapped[SDL_KEYS[target]] = original[SDL_KEYS[source]]
        mappings.append(
            ",".join(
                [guid, name] + [key + ":" + value for key, value in mapped.items()]
            )
            + ","
        )
    return {"SDL_GAMECONTROLLERCONFIG": "\n".join(mappings)}


def prepare(system, rom):
    document = profiles.read_json(ROOT / "profiles.json", {})
    profile = profiles.effective_profile(document, system, game_identity(system, rom))
    bindings = profile["bindings"]
    scale = {"native": 1, "720p": 2, "1080p": 3, "1440p": 4}[profile["resolution"]]
    widescreen = profile["aspect"] == "16:9"
    if system == "ps2":
        keys = {
            "lt": "L2",
            "rt": "R2",
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
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
        }
        update_ini(
            CONFIG / "pcsx2/PCSX2/inis/PCSX2.ini",
            {
                "Pad1": {
                    target: "SDL-0/" + SDL_BUTTONS[bindings[key]]
                    for key, target in keys.items()
                },
                "EmuCore/GS": {
                    "upscale_multiplier": str(scale),
                    "AspectRatio": "16:9" if widescreen else "Auto 4:3/3:2",
                    "OsdScale": str(profile["osd_scale"]),
                },
                "EmuCore": {
                    "EnableWideScreenPatches": str(
                        profile["aspect"] in ("auto", "16:9")
                    ).lower()
                },
                "Hotkeys": {"OpenPauseMenu": "Keyboard/Escape"},
            },
        )
    elif system == "gc":
        keys = {
            "lt": "Triggers/L",
            "rt": "Triggers/R",
            "a": "Buttons/A",
            "b": "Buttons/B",
            "x": "Buttons/X",
            "y": "Buttons/Y",
            "rb": "Buttons/Z",
            "menu": "Buttons/Start",
            "up": "D-Pad/Up",
            "down": "D-Pad/Down",
            "left": "D-Pad/Left",
            "right": "D-Pad/Right",
        }
        update_ini(
            CONFIG / "dolphin/Config/GCPadNew.ini",
            {
                "GCPad1": {
                    target: "`"
                    + DOLPHIN_BUTTONS[bindings[key]]
                    + "`"
                    + (" > 0.9" if key in ("lt", "rt") else "")
                    for key, target in keys.items()
                }
                | {
                    "Device": "SDL/0/"
                    + (
                        "Xbox Series X Controller"
                        if series_controller()
                        else "Xbox 360 Controller"
                    ),
                    "Triggers/L-Analog": "`" + DOLPHIN_BUTTONS[bindings["lt"]] + "`",
                    "Triggers/R-Analog": "`" + DOLPHIN_BUTTONS[bindings["rt"]] + "`",
                }
            },
        )
        update_ini(
            CONFIG / "dolphin/Config/GFX.ini",
            {
                "Settings": {
                    "InternalResolution": str(scale),
                    "AspectRatio": "1" if widescreen else "2",
                    "wideScreenHack": "False",
                }
            },
        )
    elif system == "dreamcast":
        update_ini(
            CONFIG / "user/flycast/emu.cfg",
            {
                "config": {
                    "rend.Resolution": str(
                        {"native": 480, "720p": 720, "1080p": 1080, "1440p": 1440}[
                            profile["resolution"]
                        ]
                    ),
                    "rend.WideScreen": "yes" if widescreen else "no",
                }
            },
        )
    return profile


def publish_catalog():
    import catalog

    cards = catalog.load_json(CONFIG / "catalog/cards.json", {"cards": {}})["cards"]
    profiles.atomic_json(
        ROOT / "catalog.json",
        {
            "games": [
                {"id": key, "title": card["title"], "system": card["system"]}
                for key, card in cards.items()
            ]
        },
    )


def publish_status(state):
    profiles.atomic_json(
        ROOT / "status.json", {"updated": state["updated"], "game": state["game"]}
    )


def start_session(system, game):
    global active_session_id
    session = {
        "id": uuid.uuid4().hex,
        "system": system,
        "game": game,
        "started": time.time(),
        "ended": None,
        "messages": [],
    }
    with message_lock:
        sessions = profiles.read_sessions(ROOT)
        sessions.append(session)
        profiles.atomic_json(ROOT / "sessions.json", sessions[-profiles.MAX_SESSIONS :])
        active_session_id = session["id"]
    return session["id"]


def append_message(session_id, text, source=None, continuation=False):
    text = ANSI.sub("", text).replace("\x00", "").strip()
    if not continuation and not MESSAGE.search(text):
        return
    text = re.sub(
        r"(?i)(token|password|secret|authorization)(\s*[:=]\s*).*",
        r"\1\2[redacted]",
        text,
    )[: profiles.MAX_MESSAGE_LENGTH]
    with message_lock:
        sessions = profiles.read_sessions(ROOT)
        session = next((item for item in sessions if item["id"] == session_id), None)
        if session is None or any(
            message["text"] == text for message in session["messages"]
        ):
            return
        if continuation:
            if session["messages"]:
                message = session["messages"][-1]
                message["text"] = (message["text"] + "\n" + text)[
                    : profiles.MAX_MESSAGE_LENGTH
                ]
        else:
            level = (
                "error"
                if re.search(r"\b(error|fatal|failed)\b", text, re.I)
                else "warning" if WARNING.search(text) else "info"
            )
            session["messages"].append(
                {
                    "timestamp": time.time(),
                    "source": source or SOURCES.get(session["system"], "RetroArch"),
                    "level": level,
                    "text": text,
                }
            )
        session["messages"] = session["messages"][-profiles.MAX_MESSAGES :]
        profiles.atomic_json(ROOT / "sessions.json", sessions)


def capture(process, session_id):
    try:
        with (CONFIG / "game.log").open("a", buffering=1) as log:
            continuing = False
            for line in iter(lambda: process.stdout.readline(8192), ""):
                log.write(line)
                try:
                    continuation = continuing and bool(
                        CONTINUATION.match(ANSI.sub("", line).strip())
                    )
                    append_message(session_id, line, continuation=continuation)
                    continuing = continuation or bool(MESSAGE.search(line))
                except (OSError, ValueError):
                    pass
    finally:
        process.stdout.close()
        with message_lock:
            sessions = profiles.read_sessions(ROOT)
            for session in sessions:
                if session["id"] == session_id:
                    session["ended"] = time.time()
            profiles.atomic_json(ROOT / "sessions.json", sessions)
