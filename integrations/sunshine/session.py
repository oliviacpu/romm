import json
import pathlib
import socket
import sys
import time


def request(action, args):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.connect("/run/emulators/control.sock")
        sock.sendall((json.dumps({"action": action, "args": args}) + "\n").encode())
        return json.loads(sock.makefile().readline())


action, args = sys.argv[1], sys.argv[2:]
reply = request(action, args)
if (
    not reply.get("ok")
    and action == "game-id"
    and reply.get("error") == "A game is already running"
):
    import catalog
    from systems import SYSTEMS

    system, path = catalog.lookup(args[0])
    status = request("status", [])
    current = status.get("game") or {}
    root = pathlib.Path("/library/roms", SYSTEMS[system].romm_platform).resolve()
    if (
        status.get("game_pid")
        and current.get("system") == system
        and (root / current.get("file", "")).resolve() == pathlib.Path(path).resolve()
    ):
        reply = {"ok": True, "pid": status["game_pid"], "wait": "game"}
if not reply.get("ok"):
    raise SystemExit(reply.get("error", "Session failed"))
if reply.get("wait"):
    while True:
        time.sleep(1)
        state = request("status", [])
        if state.get(reply["wait"] + "_pid") != reply["pid"]:
            break
else:
    print(json.dumps(reply))
