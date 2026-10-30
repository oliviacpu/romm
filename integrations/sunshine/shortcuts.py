"""Match physical controller shortcuts independently of game button mappings."""

import profiles


def menu_key(system):
    return {"ps2": "Escape", "dreamcast": "Tab", "xbox": "F2", "gc": None}.get(
        system, "F1"
    )


class HeldShortcuts:
    def __init__(self):
        self.started = {}
        self.fired = set()

    def update(self, device, buttons, profile, now):
        actions = []
        for action in ("menu", "quit"):
            key = (device, action)
            chord = profiles.SHORTCUTS[profile[action + "_shortcut"]]
            if not chord or not set(chord) <= buttons:
                self.started.pop(key, None)
                self.fired.discard(key)
                continue
            self.started.setdefault(key, now)
            hold = 2 if action == "quit" else 0
            if key not in self.fired and now - self.started[key] >= hold:
                self.fired.add(key)
                actions.append(action)
        return actions

    def forget(self, device):
        for action in ("menu", "quit"):
            key = (device, action)
            self.started.pop(key, None)
            self.fired.discard(key)
