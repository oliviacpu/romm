"""Match physical controller shortcuts independently of game button mappings."""

import profiles

# Sunshine's sparse Xbox profile uses BTN_NORTH for X and BTN_WEST for Y.
LINUX_BUTTONS = {
    304: "a",
    305: "b",
    307: "x",
    308: "y",
    310: "lb",
    311: "rb",
    314: "view",
    315: "menu",
    316: "guide",
    317: "l3",
    318: "r3",
    167: "share",
}


def physical_buttons(codes):
    return {LINUX_BUTTONS[code] for code in codes if code in LINUX_BUTTONS}


def menu_key(system):
    return {"ps2": "Escape", "dreamcast": "Tab", "xbox": "F2", "gc": None}.get(
        system, "F1"
    )


class HeldShortcuts:
    def __init__(self):
        self.started = {}
        self.fired = set()
        self.pressed = {}

    def event(self, device, code, value, profile, now):
        if code not in LINUX_BUTTONS or value not in (0, 1):
            return []
        buttons = self.pressed.setdefault(device, set())
        if value:
            buttons.add(code)
        else:
            buttons.discard(code)
        return self.tick(device, profile, now)

    def tick(self, device, profile, now):
        return self.update(
            device, physical_buttons(self.pressed.get(device, set())), profile, now
        )

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
        self.pressed.pop(device, None)
        for action in ("menu", "quit"):
            key = (device, action)
            self.started.pop(key, None)
            self.fired.discard(key)
