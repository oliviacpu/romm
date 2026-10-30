"""TV session menu rendered on the host and transported by Sunshine."""

import json
import socket
import sys

import gi
import menu_model
import profiles

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


class SessionMenu:
    def __init__(self, pid):
        self.pid = pid
        self.finished = False
        self.scope = "game"
        self.page = "home"
        self.selected = 0
        self.rows = []
        self.message = ""
        self.data = self.request("settings")
        self.draft = dict(self.data["saved"])
        self.draft["bindings"] = dict(self.draft.get("bindings", {}))
        self.window = Gtk.Window(title="RomM session menu")
        self.window.set_keep_above(True)
        self.window.connect("delete-event", lambda *_: self.finish("resume"))
        self.window.connect("key-press-event", self.key)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.box.set_halign(Gtk.Align.CENTER)
        self.box.set_valign(Gtk.Align.CENTER)
        self.box.set_size_request(1000, -1)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.add(self.box)
        self.window.add(self.scroll)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background: #20252b; color: #f7f8fa; }
            label { font-family: sans-serif; font-size: 27px; }
            label.title { font-size: 40px; font-weight: bold; }
            label.hint { font-size: 22px; color: #c4cbd5; }
            button { background: #303844; color: #f7f8fa; border: 2px solid transparent;
                     border-radius: 6px; padding: 12px 24px; font-size: 28px; }
            button:focus { background: #42576e; border-color: #b2d6ff; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.input_reader = menu_model.InputReader(sys.stdin.fileno())
        GLib.io_add_watch(self.input_reader.fd, GLib.IO_IN | GLib.IO_HUP, self.input)
        self.render()
        self.window.fullscreen()
        self.window.show_all()
        self.window.present()
        self.rows[0].grab_focus()
        print("ready", flush=True)

    def request(self, action, **payload):
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(15)
            sock.connect("/run/emulators/control.sock")
            sock.sendall(
                (
                    json.dumps(
                        {
                            "action": "menu-" + action,
                            "args": {"pid": self.pid} | payload,
                        }
                    )
                    + "\n"
                ).encode()
            )
            reply = json.loads(sock.makefile().readline())
        if not reply.get("ok"):
            raise ValueError(reply.get("error", "Session unavailable"))
        return reply

    def text(self, value, style=""):
        label = Gtk.Label(label=value)
        label.set_line_wrap(True)
        label.set_max_width_chars(70)
        if style:
            label.get_style_context().add_class(style)
        self.box.pack_start(label, False, False, 0)

    def button(self, label, callback):
        button = Gtk.Button(label=label)
        button.connect("clicked", lambda *_: self.perform(callback))
        self.box.pack_start(button, False, False, 0)
        self.rows.append(button)

    def perform(self, callback):
        try:
            callback()
        except (OSError, ValueError, KeyError) as error:
            self.message = str(error) + ". Reopen the menu to reload settings."
            self.render()

    def navigate(self, page):
        self.page = page
        self.selected = 0
        self.render()
        GLib.idle_add(self.reset_scroll)

    def reset_scroll(self):
        self.scroll.get_vadjustment().set_value(0)
        return False

    def render(self):
        for child in self.box.get_children():
            child.destroy()
        self.rows = []
        self.text(self.data["title"], "title")
        self.text(self.data["platform"]["label"] + " / Session menu", "hint")
        if self.page == "home":
            self.button("Resume game", lambda: self.finish("resume"))
            self.button("Controller assignments", lambda: self.navigate("bindings"))
            self.button("Graphics and display", lambda: self.navigate("video"))
            self.button("Recent warnings", lambda: self.navigate("messages"))
            if self.data["native_menu"]:
                self.button("Emulator and disc controls", lambda: self.finish("native"))
            self.button("Restart with saved settings", lambda: self.navigate("restart"))
            self.button("Quit game", lambda: self.navigate("quit"))
        elif self.page in ("quit", "restart"):
            self.text("Unsaved game progress will be lost. In-game saves are retained.")
            self.button("Back", lambda: self.navigate("home"))
            self.button(
                "Quit game" if self.page == "quit" else "Restart game",
                lambda: self.finish(self.page),
            )
        elif self.page == "scope":
            self.text("Switch profiles and discard these unsaved settings?")
            self.button("Back", lambda: self.navigate(self.return_page))
            self.button("Discard and switch", self.change_scope)
        elif self.page == "choose":
            self.text(
                "Choose Xbox input for "
                + self.data["platform"]["buttons"][self.binding_target]
            )
            values = [
                key
                for key in profiles.BUTTONS
                if (key in ("lt", "rt")) == (self.binding_target in ("lt", "rt"))
            ]
            for source in values[self.source_page : self.source_page + 5]:
                self.button(
                    profiles.BUTTONS[source],
                    lambda source=source: self.assign_binding(source),
                )
            if len(values) > 5:
                self.button("More Xbox inputs", lambda: self.more_sources(len(values)))
            self.button("Back", lambda: self.navigate("bindings"))
        elif self.page == "messages":
            messages = self.data["messages"][-5:]
            for item in messages:
                self.text(item["source"] + ": " + item["text"][:300], "hint")
            if not messages:
                self.text("No warnings captured for this session.")
            self.button("Back", lambda: self.navigate("home"))
        else:
            self.text(
                "Game override" if self.scope == "game" else "Platform default", "hint"
            )
            self.button(
                "Edit platform defaults" if self.scope == "game" else "Edit this game",
                self.change_scope,
            )
            effective = self.data["effective"] | self.draft
            if self.page == "video":
                self.button(
                    "Rendering: " + effective["resolution"],
                    lambda: self.cycle(
                        "resolution", self.data["platform"]["resolutions"]
                    ),
                )
                if self.data["platform"]["widescreen"]:
                    aspects = ["original", "16:9"] + (
                        ["auto"] if self.data["system"] == "ps2" else []
                    )
                    label = {
                        "original": "Follow game / original",
                        "auto": "Automatic widescreen patches",
                        "16:9": "16:9",
                    }[effective["aspect"]]
                    self.button(
                        "Aspect: " + label, lambda: self.cycle("aspect", aspects)
                    )
                else:
                    self.text(
                        "Aspect and rendering follow this emulator's native settings.",
                        "hint",
                    )
                self.text(
                    "TV stream stays unchanged. Use 16:9 only with native support or a compatible patch.",
                    "hint",
                )
            else:
                bindings = self.data["effective"]["bindings"] | self.draft["bindings"]
                keys = list(self.data["platform"]["buttons"])
                page = getattr(self, "binding_page", 0)
                for target in keys[page : page + 4]:
                    self.button(
                        self.data["platform"]["buttons"][target]
                        + "  =  Xbox "
                        + profiles.BUTTONS[bindings[target]],
                        lambda target=target: self.change_binding(target),
                    )
                if len(keys) > 4:
                    self.button("More buttons", self.more_buttons)
            self.button("Save settings", self.save)
            self.button("Back", lambda: self.navigate("home"))
            self.text(
                "Save here or in RomM. Changes apply on the next game launch.", "hint"
            )
        if self.message:
            self.text(self.message, "hint")
        self.text("D-pad: move    A: confirm / change    B: back", "hint")
        self.window.show_all()
        self.selected = min(self.selected, len(self.rows) - 1)
        self.rows[self.selected].grab_focus()

    def more_buttons(self):
        page = getattr(self, "binding_page", 0) + 4
        self.binding_page = page if page < len(self.data["platform"]["buttons"]) else 0
        self.render()

    def more_sources(self, count):
        self.source_page = self.source_page + 5 if self.source_page + 5 < count else 0
        self.selected = 0
        self.render()

    def change_binding(self, target):
        self.binding_target = target
        self.source_page = 0
        self.navigate("choose")

    def assign_binding(self, source):
        profile = self.data["effective"] | {
            "bindings": self.data["effective"]["bindings"] | self.draft["bindings"]
        }
        self.draft["bindings"] = menu_model.swap_binding(
            profile, self.binding_target, source
        )
        self.navigate("bindings")

    def cycle(self, key, values):
        current = self.draft.get(key, self.data["effective"][key])
        self.draft[key] = values[(values.index(current) + 1) % len(values)]
        self.render()

    def change_scope(self):
        saved = self.data["saved"] | {
            "bindings": self.data["saved"].get("bindings", {})
        }
        if self.draft != saved and self.page != "scope":
            self.return_page = self.page
            self.navigate("scope")
            return
        if self.page == "scope":
            self.page = self.return_page
        self.scope = "platform" if self.scope == "game" else "game"
        self.data = self.request("settings", scope=self.scope)
        self.draft = dict(self.data["saved"])
        self.draft["bindings"] = dict(self.draft.get("bindings", {}))
        self.message = ""
        self.render()

    def save(self):
        self.data = self.request(
            "save", scope=self.scope, revision=self.data["revision"], profile=self.draft
        )
        self.message = "Saved. Restart the game to apply."
        self.render()

    def finish(self, action):
        self.request("finish", choice=action)
        self.finished = True
        Gtk.main_quit()
        return True

    def action(self, action):
        if action == "back":
            if self.page == "home":
                self.finish("resume")
            else:
                self.navigate(
                    "bindings"
                    if self.page == "choose"
                    else self.return_page if self.page == "scope" else "home"
                )
        elif action in ("up", "down"):
            self.selected = (self.selected + (1 if action == "down" else -1)) % len(
                self.rows
            )
            self.rows[self.selected].grab_focus()
        elif action == "confirm":
            self.rows[self.selected].clicked()

    def key(self, _widget, event):
        action = {
            Gdk.KEY_Up: "up",
            Gdk.KEY_Down: "down",
            Gdk.KEY_Return: "confirm",
            Gdk.KEY_Escape: "back",
        }.get(event.keyval)
        if action:
            self.perform(lambda: self.action(action))
            return True
        return False

    def input(self, _channel, _condition):
        for line in self.input_reader.read_lines():
            if self.finished:
                break
            self.perform(lambda: self.action(json.loads(line)))
        if self.input_reader.closed or self.finished:
            Gtk.main_quit()
            return False
        return True


if __name__ == "__main__":
    SessionMenu(int(sys.argv[1]))
    Gtk.main()
