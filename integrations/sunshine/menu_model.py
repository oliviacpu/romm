"""Controller-independent session settings shared with the RomM profile store."""

import os

import profiles


def swap_binding(profile, target, source):
    bindings = dict(profile["bindings"])
    previous = bindings[target]
    other = next(key for key, value in bindings.items() if value == source)
    bindings[target], bindings[other] = source, previous
    return bindings


def settings(root, system, game_id, document=None):
    if document is None:
        document = profiles.read_json(
            root / "profiles.json", {"revision": 0, "platforms": {}, "games": {}}
        )
    return {
        "revision": document["revision"],
        "saved": document.get("games" if game_id else "platforms", {}).get(
            game_id or system, {}
        ),
        "effective": profiles.effective_profile(document, system, game_id),
        "platform": profiles.PLATFORMS[system],
    }


def input_action(event):
    if event.type == 1 and event.value == 1:
        return {304: "confirm", 305: "back", 167: "back"}.get(event.code)
    if event.type == 3 and event.code in (16, 17) and event.value:
        return (
            ("left" if event.value < 0 else "right")
            if event.code == 16
            else ("up" if event.value < 0 else "down")
        )
    return None


class InputReader:
    def __init__(self, fd):
        self.fd = fd
        self.pending = bytearray()
        self.closed = False
        os.set_blocking(fd, False)

    def read_lines(self):
        while not self.closed:
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            if not chunk:
                self.closed = True
                break
            self.pending.extend(chunk)
        lines = self.pending.split(b"\n")
        self.pending = bytearray(lines.pop())
        return lines
