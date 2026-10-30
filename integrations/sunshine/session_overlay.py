"""Own controller input while a session menu temporarily suspends its game."""

import json
import os
import select
import signal

# The menu process uses a fixed executable and arguments without a shell.
# trunk-ignore(bandit/B404)
import subprocess

import menu_model


class SessionOverlay:
    def __init__(self, spawn):
        self.spawn = spawn
        self.game = None
        self.process = None
        self.devices = []
        self.settled_at = None
        self.choice = None
        self.paused = False
        self.ready = False
        self.opened_at = None

    def open(self, game):
        if self.game is None:
            self.game = game

    def finish(self, choice):
        if choice not in ("resume", "native", "restart", "quit"):
            raise ValueError("Unknown session menu action")
        self.choice = choice

    def close(self):
        try:
            if self.process is not None:
                try:
                    if self.process.poll() is None:
                        self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=3)
                except ProcessLookupError:
                    pass
                finally:
                    for pipe in (self.process.stdin, self.process.stdout):
                        if pipe:
                            pipe.close()
        finally:
            for device in self.devices:
                try:
                    device.ungrab()
                except OSError:
                    pass
            try:
                if self.paused and self.game is not None:
                    try:
                        os.killpg(self.game.pid, signal.SIGCONT)
                    except ProcessLookupError:
                        pass
            finally:
                self.game = self.process = None
                self.devices = []
                self.settled_at = self.choice = None
                self.paused = self.ready = False
                self.opened_at = None

    @staticmethod
    def neutral(devices):
        return all(
            not device.active_keys()
            and all(
                device.absinfo(code).value == 0
                for code in device.capabilities(absinfo=False).get(3, [])
                if isinstance(code, int) and code in (16, 17)
            )
            for device in devices
        )

    def tick(self, game, devices, now):
        if self.game is None:
            return None
        if game != self.game or game.poll() is not None:
            self.close()
            return None
        if self.process is None:
            if not devices or not self.neutral(devices):
                self.settled_at = None
                return None
            if self.settled_at is None:
                self.settled_at = now
                return None
            # Let the emulator consume shortcut releases before taking input ownership.
            if now - self.settled_at < 0.15:
                return None
            try:
                for device in devices:
                    device.grab()
                    self.devices.append(device)
                os.killpg(game.pid, signal.SIGSTOP)
                self.paused = True
                self.opened_at = now
                self.process = self.spawn(
                    [
                        "/usr/bin/python3",
                        "/opt/emulators/session_menu.py",
                        str(game.pid),
                    ],
                    user=True,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
            except Exception:
                self.close()
                raise
        elif self.choice or self.process.poll() is not None:
            if self.neutral(devices):
                choice = self.choice or "resume"
                self.close()
                return choice
        else:
            if not self.ready and select.select([self.process.stdout], [], [], 0)[0]:
                self.ready = self.process.stdout.readline().strip() == "ready"
            if not self.ready and now - self.opened_at > 5:
                self.close()
                raise TimeoutError("Session menu did not become ready")
            try:
                for device in devices:
                    if device not in self.devices:
                        device.grab()
                        self.devices.append(device)
            except OSError:
                self.close()
                raise
        return None

    def input(self, event):
        action = menu_model.input_action(event)
        if (
            action
            and self.ready
            and not self.choice
            and self.process is not None
            and self.process.poll() is None
        ):
            try:
                self.process.stdin.write(json.dumps(action) + "\n")
                self.process.stdin.flush()
            except BrokenPipeError:
                self.choice = "resume"
