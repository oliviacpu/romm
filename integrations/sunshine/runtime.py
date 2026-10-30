# Commands use the pinned system table and library-confined ROM paths, without a shell.
# trunk-ignore-all(bandit/B404,bandit/B603,bandit/B607)
import errno
import json
import os
import pathlib
import pwd
import select
import signal
import socket
import socketserver
import struct
import subprocess
import threading
import time

import catalog
import firmware_handoff
import profile_runtime
import shortcuts
from systems import SYSTEMS, argv
from systems import ready as system_ready

RUN = pathlib.Path("/run/emulators")
CONFIG = pathlib.Path("/config")
children = []
lock = threading.RLock()
game = None
stopping = False
connected = 0
connected_at = None
disconnected_at = None
transport_lost_at = None
last_event = None
current_game = None
current_profile = None
ready = False
fatal = None
soak_until = None
backup_until = 0
catalog_changed = threading.Event()
user_env = os.environ | {
    "HOME": "/config/home",
    "XDG_CONFIG_HOME": "/config/user",
    "XDG_DATA_HOME": "/saves",
    "XDG_CACHE_HOME": "/config/cache",
    "XDG_RUNTIME_DIR": "/run/emulators/user",
    "QT_QPA_PLATFORM": "xcb",
    "MALLOC_ARENA_MAX": "2",
}


def atomic(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data))
    os.chmod(temp, 0o644)
    os.replace(temp, path)


def state():
    ps2_ready, ps2_reason = system_ready(SYSTEMS["ps2"])
    return {
        "ready": ready,
        "fatal": fatal,
        "game_pid": game.pid if game and game.poll() is None else None,
        "game": current_game if game and game.poll() is None else None,
        "clients": connected,
        "disconnected_at": disconnected_at,
        "soak_until": soak_until,
        "last_event": last_event,
        "ps2": "BIOS available" if ps2_ready else ps2_reason,
        "updated": time.time(),
    }


def spawn(argv, user=False, **kwargs):
    if user:
        kwargs.update(
            user=20000,
            group=20000,
            extra_groups=[995, 44],
            env=user_env | kwargs.pop("env", {}),
        )
    p = subprocess.Popen(argv, start_new_session=True, **kwargs)
    return p


def close_process(p):
    if p is None or p.poll() is not None:
        return
    # WM_DELETE_WINDOW lets the emulator flush native save files first.
    if p == game:
        windows = subprocess.run(
            ["xdotool", "search", "--pid", str(p.pid)],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.split()
        for window in windows:
            subprocess.run(
                ["wmctrl", "-i", "-c", hex(int(window))],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        try:
            p.wait(8)
            return
        except subprocess.TimeoutExpired:
            pass
    os.killpg(p.pid, signal.SIGTERM)
    try:
        p.wait(8)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait(5)


def close_game():
    global game, current_game, current_profile
    with lock:
        close_process(game)
        game = None
        current_game = None
        current_profile = None


def cleanup():
    global last_event, disconnected_at
    with lock:
        close_game()
        disconnected_at = None
        last_event = "Disconnected session closed; saved progress retained"
        atomic(CONFIG / "runtime-state.json", state())


def launch_game(args):
    global game, current_game, current_profile, last_event, disconnected_at
    with lock:
        if time.time() < backup_until:
            raise RuntimeError("Save backup in progress; try again shortly")
        if game and game.poll() is None:
            raise RuntimeError("A game is already running")
        system, name = args
        rom = pathlib.Path(name).resolve()
        definition = SYSTEMS.get(system)
        if not definition:
            raise ValueError("Invalid game system")
        root = pathlib.Path("/library/roms", definition.romm_platform).resolve()
        if (
            not rom.is_relative_to(root)
            or not rom.is_file()
            or rom.suffix.lower() not in definition.extensions
        ):
            raise ValueError("Invalid game path")
        available, reason = system_ready(definition)
        if not available:
            raise RuntimeError(reason)
        catalog.sidecars_complete(rom)
        firmware_handoff.prepare(system)
        profile = profile_runtime.prepare(system, rom)
        session_id = profile_runtime.start_session(system, str(rom.relative_to(root)))
        game = spawn(
            argv(definition, rom),
            user=True,
            env={"ROMM_EMULATION_PROFILE": json.dumps(profile)}
            | (
                profile_runtime.controller_environment(profile)
                if system in ("dreamcast", "xbox")
                else {}
            ),
            cwd=rom.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
        threading.Thread(
            target=profile_runtime.capture, args=(game, session_id), daemon=True
        ).start()
        current_game = {
            "system": system,
            "file": str(rom.relative_to(root)),
            "started": time.time(),
        }
        current_profile = profile
        last_event = "Game started"
        if not connected and disconnected_at is None:
            disconnected_at = time.time()
        return {"ok": True, "pid": game.pid, "wait": "game"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        global soak_until, backup_until
        try:
            request = json.loads(self.rfile.readline(16384))
            action = request["action"]
            if action == "game":
                result = launch_game(request["args"])
            elif action == "game-id":
                system, rom = catalog.lookup(request["args"][0])
                result = launch_game([system, str(rom)])
            elif action == "soak":
                _, uid, _ = struct.unpack(
                    "3i",
                    self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12),
                )
                if uid != 0:
                    raise PermissionError("Root-only stability test")
                result = launch_game(request["args"])
                soak_until = time.time() + 14400
                result.pop("wait", None)
            elif action in ["backup-lock", "backup-unlock"]:
                _, uid, _ = struct.unpack(
                    "3i",
                    self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12),
                )
                if uid != 0:
                    raise PermissionError("Root-only backup control")
                with lock:
                    if action == "backup-lock" and (state()["game_pid"] or connected):
                        raise RuntimeError("Session active; backup deferred")
                    backup_until = time.time() + 300 if action == "backup-lock" else 0
                    result = {"ok": True}
            elif action == "close-game":
                close_game()
                result = {"ok": True}
            elif action == "close-session":
                cleanup()
                result = {"ok": True}
            elif action == "status":
                result = state()
            else:
                raise ValueError("Unsupported action")
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        self.wfile.write((json.dumps(result) + "\n").encode())


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def controller_watch():
    import evdev

    devices = {}
    pressed = {}
    tracker = shortcuts.HeldShortcuts()
    session = None
    codes = {
        evdev.ecodes.BTN_SOUTH: "a",
        evdev.ecodes.BTN_EAST: "b",
        evdev.ecodes.BTN_WEST: "x",
        evdev.ecodes.BTN_NORTH: "y",
        evdev.ecodes.BTN_TL: "lb",
        evdev.ecodes.BTN_TR: "rb",
        evdev.ecodes.BTN_SELECT: "view",
        evdev.ecodes.BTN_START: "menu",
        evdev.ecodes.BTN_THUMBL: "l3",
        evdev.ecodes.BTN_THUMBR: "r3",
        evdev.ecodes.BTN_MODE: "guide",
        evdev.ecodes.KEY_RECORD: "share",
    }
    next_scan = 0
    while not stopping:
        if time.monotonic() >= next_scan:
            next_scan = time.monotonic() + 1
            for path in map(str, pathlib.Path("/dev/input").glob("event*")):
                if path not in devices:
                    try:
                        dev = evdev.InputDevice(path)
                    except OSError:
                        continue
                    if (
                        "sunshine" in dev.name.lower()
                        or "x-box" in dev.name.lower()
                        or "xbox" in dev.name.lower()
                    ):
                        devices[path] = dev
                        pressed[path] = set()
                    else:
                        dev.close()
        if not devices:
            time.sleep(1)
            continue
        with lock:
            active = game if game and game.poll() is None else None
            if active != session:
                tracker = shortcuts.HeldShortcuts()
                session = active
                pressed = {path: set() for path in devices}
        readable, _, _ = select.select(list(devices.values()), [], [], 0.1)
        for dev in readable:
            path = dev.path
            try:
                for event in dev.read():
                    if event.type == evdev.ecodes.EV_KEY:
                        if event.value == 1:
                            pressed[path].add(event.code)
                        elif event.value == 0:
                            pressed[path].discard(event.code)
            except OSError:
                devices.pop(path).close()
                pressed.pop(path, None)
                tracker.forget(path)
        with lock:
            active = game if game and game.poll() is None else None
            if active is None or active != session or current_profile is None:
                continue
            for path, buttons in pressed.items():
                physical = {codes[code] for code in buttons if code in codes}
                for action in tracker.update(
                    path, physical, current_profile, time.monotonic()
                ):
                    if action == "quit":
                        close_game()
                        break
                    key = shortcuts.menu_key(current_game["system"])
                    if key:
                        try:
                            focused = subprocess.run(
                                ["xdotool", "getactivewindow", "getwindowpid"],
                                capture_output=True,
                                text=True,
                                timeout=3,
                                check=True,
                            ).stdout.strip()
                            if focused == str(active.pid):
                                subprocess.run(
                                    ["xdotool", "key", "--clearmodifiers", key],
                                    timeout=3,
                                    check=True,
                                )
                        except (OSError, subprocess.SubprocessError) as error:
                            if profile_runtime.active_session_id:
                                profile_runtime.append_message(
                                    profile_runtime.active_session_id,
                                    "Warning: emulator menu shortcut failed: "
                                    + str(error),
                                    source="Launcher",
                                )
                if game is None:
                    break


def sunshine_log(pipe):
    global ready, fatal, connected, connected_at, disconnected_at, transport_lost_at, last_event
    with open("/config/sunshine/runtime.log", "a", buffering=1) as log:
        for line in pipe:
            print(line, end="", flush=True)
            log.write(line)
            if profile_runtime.active_session_id and profile_runtime.WARNING.search(
                line
            ):
                try:
                    profile_runtime.append_message(
                        profile_runtime.active_session_id, line, source="Sunshine"
                    )
                except (OSError, ValueError):
                    pass
            if "Found H.264 encoder: h264_nvenc" in line:
                ready = True
            if "Fatal:" in line or "Found H.264 encoder: libx264" in line:
                fatal = line.strip()
            if "CLIENT CONNECTED" in line:
                with lock:
                    connected += 1
                    connected_at = time.time()
                    disconnected_at = None
                    transport_lost_at = None
                    last_event = "Client connected"
            if "CLIENT DISCONNECTED" in line:
                with lock:
                    connected = max(0, connected - 1)
                    if not connected:
                        disconnected_at = time.time()
                        transport_lost_at = None
                    last_event = "Client disconnected; 15 minute grace period"


def has_stream_transport():
    try:
        for name in ("/proc/net/udp", "/proc/net/udp6"):
            with open(name) as table:
                next(table)
                for line in table:
                    local = line.split()[1]
                    port = int(local.rsplit(":", 1)[1], 16)
                    if port in (47998, 47999, 48000):
                        return True
    except (OSError, ValueError, IndexError):
        return None
    return False


def catalog_worker():
    while not stopping:
        try:
            if catalog.sync():
                catalog_changed.set()
            profile_runtime.publish_catalog()
        except Exception as error:
            catalog.atomic_json(
                catalog.STATUS,
                {
                    "published": None,
                    "errors": [
                        {"system": "Catalog", "game": "Sync", "reason": str(error)}
                    ],
                    "pending": "Previous cards retained",
                    "updated": time.time(),
                },
            )
        for _ in range(30):
            if stopping:
                return
            time.sleep(1)


def start_sunshine():
    process = spawn(
        ["sunshine", "/config/sunshine/sunshine.conf"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=sunshine_log, args=(process.stdout,), daemon=True).start()
    return process


def request_stop(*_):
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, request_stop)
signal.signal(signal.SIGINT, request_stop)
for path in [
    RUN,
    RUN / "user",
    RUN / "pulse",
    CONFIG / "home",
    CONFIG / "cache",
    CONFIG / "user",
]:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, 20000, 20000)
os.chmod(RUN / "user", 0o700)
pulse_user = pwd.getpwnam("pulse")
os.chown(RUN / "pulse", pulse_user.pw_uid, pulse_user.pw_gid)
auth = pathlib.Path(os.environ["XAUTHORITY"])
auth.touch(mode=0o644)
subprocess.run(
    ["xauth", "-f", str(auth), "add", ":10", ".", os.urandom(16).hex()], check=True
)
xorg = spawn(
    [
        "Xorg",
        ":10",
        "-config",
        "/etc/X11/flycast.conf",
        "-noreset",
        "-nolisten",
        "tcp",
        "-novtswitch",
        "-sharevts",
        "-auth",
        str(auth),
        "-logfile",
        "/config/Xorg.log",
    ]
)
children.append(xorg)
for _ in range(100):
    if xorg.poll() is not None:
        raise RuntimeError("Xorg failed")
    if (
        subprocess.run(
            ["xdpyinfo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode
        == 0
    ):
        break
    time.sleep(0.2)
else:
    raise RuntimeError("Xorg readiness timeout")
subprocess.run(["xhost", "+si:localuser:emulator"], check=True)
children.append(spawn(["openbox", "--sm-disable"]))
pa = RUN / "pulse.pa"
pa.write_text(
    "load-module module-native-protocol-unix socket=/run/emulators/pulse/native auth-anonymous=1\nload-module module-null-sink sink_name=game sink_properties=device.description=Emulators\nset-default-sink game\n"
)
children.append(
    spawn(
        [
            "pulseaudio",
            "--system",
            "--daemonize=no",
            "--disallow-exit",
            "--exit-idle-time=-1",
            "-n",
            "-F",
            str(pa),
        ]
    )
)
for _ in range(50):
    if (RUN / "pulse/native").exists():
        break
    time.sleep(0.2)
control_socket = RUN / "control.sock"
if control_socket.exists():
    with socket.socket(socket.AF_UNIX) as probe:
        try:
            probe.connect(str(control_socket))
        except OSError as error:
            if error.errno not in (errno.ECONNREFUSED, errno.ENOENT):
                raise
            control_socket.unlink(missing_ok=True)
        else:
            raise RuntimeError("Another emulator runtime owns the control socket")
server = Server(str(control_socket), Handler)
# Private socket shared only by root and the emulator group.
# trunk-ignore(bandit/B103)
os.chmod(RUN / "control.sock", 0o660)
os.chown(RUN / "control.sock", 0, 20000)
threading.Thread(target=server.serve_forever, daemon=True).start()
threading.Thread(target=controller_watch, daemon=True).start()
try:
    catalog.sync()
    profile_runtime.publish_catalog()
except Exception as error:
    catalog.atomic_json(
        catalog.STATUS,
        {
            "published": None,
            "errors": [{"system": "Catalog", "game": "Startup", "reason": str(error)}],
            "pending": "Previous cards retained",
            "updated": time.time(),
        },
    )
sunshine = start_sunshine()
children.append(sunshine)
threading.Thread(target=catalog_worker, daemon=True).start()
while not stopping and not fatal and all(p.poll() is None for p in children):
    if connected and connected_at and time.time() - connected_at > 30:
        transport = has_stream_transport()
        if transport is False:
            transport_lost_at = transport_lost_at or time.time()
            if time.time() - transport_lost_at > 30:
                connected = 0
                disconnected_at = time.time()
                transport_lost_at = None
                last_event = "Stream transport ended; 15 minute grace period"
        elif transport is True:
            transport_lost_at = None
    if (
        catalog_changed.is_set()
        and not connected
        and not (game and game.poll() is None)
    ):
        close_process(sunshine)
        ready = False
        disconnected_at = None
        sunshine = start_sunshine()
        children[-1] = sunshine
        catalog_changed.clear()
    if soak_until and time.time() >= soak_until:
        cleanup()
        soak_until = None
    if disconnected_at and time.time() - disconnected_at >= 900 and not soak_until:
        cleanup()
    with lock:
        if game and game.poll() is not None:
            game = None
            current_game = None
            last_event = "Game exited"
        snapshot = state()
        atomic(CONFIG / "runtime-state.json", snapshot)
        try:
            profile_runtime.publish_status(snapshot)
        except OSError as error:
            print("Could not publish RomM session status:", error, flush=True)
    time.sleep(1)
ready = False
cleanup()
server.shutdown()
for p in reversed(children):
    close_process(p)
raise SystemExit(0 if stopping else 1)
