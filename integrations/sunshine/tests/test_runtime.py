import importlib.util
import io
import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "integrations/sunshine"))
spec = importlib.util.spec_from_file_location(
    "profiles", REPO / "backend/handler/emulation/profiles.py"
)
profiles = importlib.util.module_from_spec(spec)
sys.modules["profiles"] = profiles
spec.loader.exec_module(profiles)
profile_runtime = importlib.import_module("profile_runtime")
retropad = importlib.import_module("retropad")
shortcuts = importlib.import_module("shortcuts")
menu_model = importlib.import_module("menu_model")
session_overlay = importlib.import_module("session_overlay")


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tracker = shortcuts.HeldShortcuts()
        self.profile = profiles.effective_profile({}, "ps2")

    def test_physical_view_y_uses_sunshine_sparse_xbox_codes(self):
        self.profile["menu_shortcut"] = "view_y"
        self.assertEqual(shortcuts.physical_buttons({307}), {"x"})
        self.assertEqual(shortcuts.physical_buttons({308}), {"y"})
        self.assertEqual(
            self.tracker.update(
                "pad", shortcuts.physical_buttons({314, 307}), self.profile, 0
            ),
            [],
        )
        self.assertEqual(
            self.tracker.update(
                "pad", shortcuts.physical_buttons({314, 308}), self.profile, 1
            ),
            ["menu"],
        )

    def test_menu_fires_once_until_the_chord_is_released(self):
        buttons = {"l3", "r3"}
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 0), ["menu"])
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 10), [])
        self.tracker.update("pad", {"l3"}, self.profile, 11)
        self.assertEqual(
            self.tracker.update("pad", buttons, self.profile, 12), ["menu"]
        )

    def test_quit_needs_two_continuous_seconds_and_does_not_repeat(self):
        buttons = {"l3", "menu"}
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 0), [])
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 1.999), [])
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 2), ["quit"])
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 5), [])
        self.tracker.update("pad", set(), self.profile, 6)
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 7), [])
        self.tracker.update("pad", {"l3"}, self.profile, 8)
        self.assertEqual(self.tracker.update("pad", buttons, self.profile, 9), [])
        self.assertEqual(
            self.tracker.update("pad", buttons, self.profile, 11), ["quit"]
        )

    def test_pads_do_not_combine_chords_and_disconnect_clears_the_hold(self):
        self.assertEqual(self.tracker.update("one", {"l3"}, self.profile, 0), [])
        self.assertEqual(self.tracker.update("two", {"menu"}, self.profile, 3), [])
        self.tracker.update("one", {"l3", "menu"}, self.profile, 4)
        self.tracker.forget("one")
        self.assertEqual(
            self.tracker.update("one", {"l3", "menu"}, self.profile, 6), []
        )

    def test_share_guide_and_unknown_keys_are_decoded_separately(self):
        self.assertEqual(shortcuts.physical_buttons({167, 316, 30}), {"share", "guide"})
        self.profile["menu_shortcut"] = "share"
        self.assertEqual(self.tracker.update("pad", {"guide"}, self.profile, 0), [])
        self.assertEqual(
            self.tracker.update("pad", {"share"}, self.profile, 1), ["menu"]
        )

    def test_native_menu_keys_and_common_gamecube_session_menu(self):
        expected = {"ps2": "Escape", "xbox": "F2", "dreamcast": "Tab", "gc": None}
        for system in profiles.PLATFORMS:
            self.assertEqual(shortcuts.menu_key(system), expected.get(system, "F1"))
        profile = profiles.effective_profile({}, "gc")
        self.assertEqual(self.tracker.update("pad", {"l3", "r3"}, profile, 0), ["menu"])

    def test_fast_share_taps_preserve_transitions_within_one_read_batch(self):
        self.profile["menu_shortcut"] = "share"
        actions = []
        for code, value in [(167, 1), (167, 0), (167, 1), (167, 0)]:
            actions.extend(self.tracker.event("pad", code, value, self.profile, 0))
        self.assertEqual(actions, ["menu", "menu"])
        self.assertEqual(self.tracker.tick("pad", self.profile, 0.1), [])

    def test_event_stream_preserves_holds_and_ignores_autorepeat(self):
        self.assertEqual(self.tracker.event("pad", 317, 1, self.profile, 0), [])
        self.assertEqual(self.tracker.event("pad", 315, 1, self.profile, 0), [])
        self.assertEqual(self.tracker.event("pad", 315, 2, self.profile, 1), [])
        self.assertEqual(self.tracker.tick("pad", self.profile, 1.999), [])
        self.assertEqual(self.tracker.tick("pad", self.profile, 2), ["quit"])
        self.assertEqual(self.tracker.tick("pad", self.profile, 3), [])
        self.tracker.forget("pad")
        self.assertEqual(self.tracker.tick("pad", self.profile, 4), [])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        patcher = patch.object(profile_runtime, "ROOT", self.root / "integration")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(profile_runtime, "CONFIG", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(profile_runtime.os, "chown")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ini_update_preserves_bios_saves_and_other_sections(self):
        path = self.root / "PCSX2.ini"
        path.write_text(
            "[Filenames]\nBIOS = owned.bin\n[Hotkeys]\nOpenPauseMenu = Keyboard/Escape\nOpenPauseMenu = old\nOther = keep\n[MemoryCards]\nSlot1_Filename = /saves/card.ps2\n"
        )
        profile_runtime.update_ini(
            path,
            {
                "Hotkeys": {
                    "OpenPauseMenu": [
                        "Keyboard/Escape",
                        "SDL-0/LeftStick & SDL-0/RightStick",
                    ]
                },
                "EmuCore/GS": {"OsdScale": "200"},
            },
        )
        result = path.read_text()
        self.assertIn("BIOS = owned.bin", result)
        self.assertIn("Slot1_Filename = /saves/card.ps2", result)
        self.assertIn("Other = keep", result)
        self.assertEqual(result.count("OpenPauseMenu = "), 2)
        self.assertIn("[EmuCore/GS]\nOsdScale = 200", result)

    def test_ps2_game_override_is_replaced_on_next_platform_launch(self):
        path = self.root / "pcsx2/PCSX2/inis/PCSX2.ini"
        path.parent.mkdir(parents=True)
        path.write_text(
            "[Filenames]\nBIOS = owned.bin\n[EmuCore/GS]\nupscale_multiplier = 1\n"
        )
        document = {
            "platforms": {"ps2": {"resolution": "720p"}},
            "games": {
                "a" * 20: {"resolution": "1080p", "bindings": {"b": "x", "x": "b"}}
            },
        }
        profiles.atomic_json(profile_runtime.ROOT / "profiles.json", document)
        with patch.object(profile_runtime, "game_identity", return_value="a" * 20):
            profile_runtime.prepare("ps2", Path("/library/roms/ps2/test.iso"))
        self.assertIn("Circle = SDL-0/FaceWest", path.read_text())
        self.assertIn("upscale_multiplier = 3", path.read_text())
        with patch.object(profile_runtime, "game_identity", return_value="b" * 20):
            profile_runtime.prepare("ps2", Path("/library/roms/ps2/other.iso"))
        self.assertIn("Circle = SDL-0/FaceEast", path.read_text())
        self.assertIn("upscale_multiplier = 2", path.read_text())
        self.assertIn("BIOS = owned.bin", path.read_text())

    def test_dreamcast_resolution_and_original_aspect(self):
        with patch.object(profile_runtime, "game_identity", return_value=None):
            profiles.atomic_json(
                profile_runtime.ROOT / "profiles.json",
                {"platforms": {"dreamcast": {"resolution": "1080p"}}},
            )
            profile_runtime.prepare("dreamcast", Path("/library/roms/dc/game.chd"))
        result = (self.root / "user/flycast/emu.cfg").read_text()
        self.assertIn("rend.Resolution = 1080", result)
        self.assertIn("rend.WideScreen = no", result)

    def test_xbox_video_profile_preserves_bios_and_controller_toml(self):
        path = self.root / "xemu/xemu.toml"
        path.parent.mkdir(parents=True)
        path.write_text(
            "[input]\ngamepad_mappings = [\n { gamepad_id = 'controller-guid'}\n]\n[sys.files]\nflashrom_path = '/owned/bios.bin'\nhdd_path = '/saves/owned.qcow2'\n[display]\nrenderer = 'VULKAN'\n"
        )
        for settings, expected in [
            ({"resolution": "720p", "aspect": "16:9"}, (2, "16x9")),
            ({}, (1, "auto")),
        ]:
            profiles.atomic_json(
                profile_runtime.ROOT / "profiles.json",
                {"platforms": {"xbox": settings}},
            )
            with patch.object(profile_runtime, "game_identity", return_value=None):
                profile_runtime.prepare("xbox", Path("/library/roms/xbox/game.iso"))
            result = tomllib.loads(path.read_text())
            self.assertEqual(
                (
                    result["display"]["quality"]["surface_scale"],
                    result["display"]["ui"]["aspect_ratio"],
                ),
                expected,
            )
            self.assertEqual(result["display"]["renderer"], "VULKAN")
            self.assertEqual(result["sys"]["files"]["hdd_path"], "/saves/owned.qcow2")
            self.assertEqual(result["sys"]["files"]["flashrom_path"], "/owned/bios.bin")
            self.assertEqual(
                result["input"]["gamepad_mappings"][0]["gamepad_id"], "controller-guid"
            )

    def test_gamecube_follows_native_widescreen_without_enabling_a_hack(self):
        for aspect, expected in [("original", "0"), ("16:9", "1")]:
            profiles.atomic_json(
                profile_runtime.ROOT / "profiles.json",
                {"platforms": {"gc": {"aspect": aspect}}},
            )
            with patch.object(profile_runtime, "game_identity", return_value=None):
                profile_runtime.prepare("gc", Path("/library/roms/ngc/game.iso"))
            result = (self.root / "dolphin/Config/GFX.ini").read_text()
            self.assertIn("AspectRatio = " + expected, result)
            self.assertIn("wideScreenHack = False", result)

    def test_gamecube_dpad_override_is_written_and_then_reset(self):
        path = self.root / "dolphin/Config/GCPadNew.ini"
        profiles.atomic_json(
            profile_runtime.ROOT / "profiles.json",
            {
                "games": {
                    "a"
                    * 20: {
                        "resolution": "1080p",
                        "bindings": {
                            "up": "down",
                            "down": "up",
                            "lt": "rt",
                            "rt": "lt",
                        },
                    }
                }
            },
        )
        with patch.object(profile_runtime, "game_identity", return_value="a" * 20):
            profile_runtime.prepare("gc", Path("/library/roms/gc/test.iso"))
        self.assertIn("D-Pad/Up = `Pad S`", path.read_text())
        self.assertIn("Triggers/L-Analog = `Trigger R`", path.read_text())
        self.assertIn("Triggers/L = `Trigger R` > 0.9", path.read_text())
        graphics = self.root / "dolphin/Config/GFX.ini"
        self.assertIn("InternalResolution = 3", graphics.read_text())
        with patch.object(profile_runtime, "game_identity", return_value=None):
            profile_runtime.prepare("gc", Path("/library/roms/gc/other.iso"))
        self.assertIn("D-Pad/Up = `Pad N`", path.read_text())
        self.assertIn("Triggers/L-Analog = `Trigger L`", path.read_text())
        self.assertIn("InternalResolution = 1", graphics.read_text())

    def test_sdl_remaps_known_baseline_without_changing_axes(self):
        database = self.root / "pcsx2/PCSX2/game_controller_db.txt"
        database.parent.mkdir(parents=True)
        database.write_text(
            "050017945e0400008e02000014010000,Xbox 360 via Sunshine,a:b0,b:b1,x:b3,y:b4,back:b10,start:b11,leftstick:b13,rightstick:b14,leftshoulder:b6,rightshoulder:b7,dpup:h0.1,dpdown:h0.4,dpleft:h0.8,dpright:h0.2,leftx:a0,lefty:a1,rightx:a3,righty:a4,lefttrigger:a2,righttrigger:a5,platform:Linux,\n"
        )
        profile = profiles.effective_profile(
            {"platforms": {"xbox": {"bindings": {"b": "x", "x": "b"}}}}, "xbox"
        )
        mapping = profile_runtime.controller_environment(profile)[
            "SDL_GAMECONTROLLERCONFIG"
        ]
        self.assertIn("b:b3,", mapping)
        self.assertIn("a:b0,", mapping)
        self.assertIn("lefttrigger:a2,", mapping)
        self.assertEqual(
            profile_runtime.controller_environment(
                profiles.effective_profile({}, "xbox")
            ),
            {},
        )

    def test_messages_are_bounded_deduplicated_and_redacted(self):
        session = profile_runtime.start_session("ps2", "SSX.iso")
        profile_runtime.append_message(
            session, "\x1b[31mWarning: blending too low\x1b[0m"
        )
        profile_runtime.append_message(session, "Warning: blending too low")
        profile_runtime.append_message(session, "Error: token=private-value failed")
        sessions = profiles.read_json(profile_runtime.ROOT / "sessions.json", [])
        self.assertEqual(len(sessions[0]["messages"]), 2)
        self.assertNotIn("private-value", json.dumps(sessions))
        for index in range(profiles.MAX_MESSAGES + 5):
            profile_runtime.append_message(session, f"Warning {index}: " + "x" * 2000)
        sessions = profiles.read_json(profile_runtime.ROOT / "sessions.json", [])
        self.assertEqual(len(sessions[0]["messages"]), profiles.MAX_MESSAGES)
        self.assertLessEqual(len(sessions[0]["messages"][0]["text"]), 1500)
        for _ in range(profiles.MAX_SESSIONS + 3):
            profile_runtime.start_session("ps2", "game.iso")
        self.assertEqual(
            len(profiles.read_json(profile_runtime.ROOT / "sessions.json", [])),
            profiles.MAX_SESSIONS,
        )

    def test_capture_keeps_warning_after_game_exit(self):
        session = profile_runtime.start_session("ps2", "SSX.iso")
        process = SimpleNamespace(
            stdout=io.StringIO(
                "ordinary line\nOSD [HWBlendingWarning]: Current Blending Accuracy is Basic.\n"
            )
        )
        profile_runtime.capture(process, session)
        sessions = profiles.read_json(profile_runtime.ROOT / "sessions.json", [])
        self.assertIsNotNone(sessions[0]["ended"])
        self.assertEqual(len(sessions[0]["messages"]), 1)
        self.assertIn("Blending", sessions[0]["messages"][0]["text"])

    def test_full_multibyte_history_does_not_block_new_sessions(self):
        for character in ("界", "\U0001f3ae", "\x01"):
            with self.subTest(character=repr(character)):
                sessions = [
                    {
                        "id": str(index),
                        "system": "xbox",
                        "game": "game.iso",
                        "started": 1,
                        "ended": 2,
                        "messages": [
                            {
                                "timestamp": 1,
                                "source": "xemu",
                                "level": "warning",
                                "text": character * 1500,
                            }
                            for _ in range(profiles.MAX_MESSAGES)
                        ],
                    }
                    for index in range(profiles.MAX_SESSIONS)
                ]
                path = profile_runtime.ROOT / "sessions.json"
                profiles.atomic_json(path, sessions)
                self.assertGreater(path.stat().st_size, 4 * 1024 * 1024)
                session = profile_runtime.start_session("xbox", "next.iso")
                profile_runtime.append_message(session, "Warning: capture still works")
                profile_runtime.capture(
                    SimpleNamespace(stdout=io.StringIO("")), session
                )
                stored = json.loads(path.read_text())
                self.assertEqual(len(stored), profiles.MAX_SESSIONS)
                self.assertIsNotNone(stored[-1]["ended"])
                self.assertEqual(
                    stored[-1]["messages"][0]["text"], "Warning: capture still works"
                )

    def test_core_remaps_leave_menu_and_quit_inputs_unchanged(self):
        script = importlib.util.spec_from_file_location(
            "retroarch_launch", REPO / "integrations/sunshine/retroarch-launch.py"
        )
        launcher = importlib.util.module_from_spec(script)
        script.loader.exec_module(launcher)
        user = self.root / "user"
        user.mkdir()
        profile = profiles.effective_profile({}, "snes")
        with patch.object(retropad, "core_name", return_value="Snes9x"), patch.object(
            launcher.os, "execv"
        ) as execute, patch.dict(
            launcher.os.environ, {"ROMM_EMULATION_PROFILE": json.dumps(profile)}
        ):
            launcher.launch("snes", "/core.so", "/game.sfc", self.root / "saves", user)
        config = (user / "retroarch-snes.cfg").read_text()
        remap = (user / "remaps-snes/Snes9x/Snes9x.rmp").read_text()
        self.assertIn('input_player1_b_btn = "0"', config)
        self.assertIn('input_player1_a_btn = "1"', config)
        self.assertIn('menu_swap_ok_cancel_buttons = "true"', config)
        self.assertIn('input_player1_btn_b = "8"', remap)
        self.assertIn('input_player1_start_btn = "6"', config)
        execute.assert_called_once()

    def test_session_and_general_json_size_limits_remain_enforced(self):
        root = profile_runtime.ROOT
        root.mkdir()
        with (root / "sessions.json").open("wb") as output:
            output.truncate(profiles.MAX_SESSION_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "size limit"):
            profiles.read_sessions(root)
        with (root / "profiles.json").open("wb") as output:
            output.truncate(profiles.MAX_JSON_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "size limit"):
            profiles.read_json(root / "profiles.json", {})


if __name__ == "__main__":
    unittest.main()


class SessionMenuTests(unittest.TestCase):
    def setUp(self):
        readable = patch.object(
            session_overlay.select, "select", return_value=([], [], [])
        )
        readable.start()
        self.addCleanup(readable.stop)

    def test_swapping_preserves_unique_inputs_and_does_not_mutate_the_profile(self):
        profile = profiles.effective_profile({}, "ps2")
        result = menu_model.swap_binding(profile, "a", "b")
        self.assertEqual((result["a"], result["b"]), ("b", "a"))
        self.assertEqual(len(set(result.values())), len(result))
        self.assertEqual(profile["bindings"]["a"], "a")

    def test_menu_confirmation_is_physical_and_independent_of_console_mapping(self):
        for event, expected in [
            ((1, 304, 1), "confirm"),
            ((1, 305, 1), "back"),
            ((1, 304, 0), None),
            ((1, 304, 2), None),
            ((3, 17, -1), "up"),
            ((3, 16, 1), "right"),
            ((3, 0, -100), None),
        ]:
            self.assertEqual(
                menu_model.input_action(
                    SimpleNamespace(type=event[0], code=event[1], value=event[2])
                ),
                expected,
            )

    def test_menu_writes_use_the_same_revision_lock_as_romm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profiles.save_profile(root, "gc", None, {"resolution": "720p"}, 0)
            snapshot = menu_model.settings(root, "gc", "a" * 20)
            profiles.save_profile(
                root, "gc", "a" * 20, {"aspect": "16:9"}, snapshot["revision"]
            )
            with self.assertRaises(FileExistsError):
                profiles.save_profile(root, "gc", "a" * 20, {}, snapshot["revision"])
            result = menu_model.settings(root, "gc", "a" * 20)
            self.assertEqual(result["effective"]["resolution"], "720p")
            self.assertEqual(result["effective"]["aspect"], "16:9")

    def test_save_response_keeps_its_revision_despite_an_intervening_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved = profiles.save_profile(root, "gc", None, {"resolution": "720p"}, 0)
            profiles.save_profile(root, "gc", None, {"resolution": "1080p"}, 1)
            result = menu_model.settings(root, "gc", None, saved)
            self.assertEqual(result["revision"], 1)
            self.assertEqual(result["saved"]["resolution"], "720p")
            with self.assertRaises(FileExistsError):
                profiles.save_profile(
                    root, "gc", None, {"aspect": "16:9"}, result["revision"]
                )

    def test_input_drains_multiple_lines_and_retains_partial_actions(self):
        read_fd, write_fd = os.pipe()
        try:
            reader = menu_model.InputReader(read_fd)
            os.write(write_fd, b'"down"\n"confirm"\n"ba')
            self.assertEqual(reader.read_lines(), [b'"down"', b'"confirm"'])
            self.assertEqual(reader.read_lines(), [])
            os.write(write_fd, b'ck"\n')
            os.close(write_fd)
            write_fd = None
            self.assertEqual(reader.read_lines(), [b'"back"'])
            self.assertTrue(reader.closed)
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)

    def fixture(self):
        child = Mock(pid=41)
        child.poll.return_value = None
        game = Mock(pid=42)
        game.poll.return_value = None
        device = Mock()
        device.active_keys.return_value = []
        device.capabilities.return_value = {3: [16, 17]}
        device.absinfo.return_value = SimpleNamespace(value=0)
        overlay = session_overlay.SessionOverlay(Mock(return_value=child))
        overlay.open(game)
        return overlay, game, child, device

    @patch.object(session_overlay.os, "killpg")
    def test_waits_for_shortcut_release_then_resumes_after_menu_button_release(
        self, killpg
    ):
        overlay, game, child, device = self.fixture()
        device.active_keys.return_value = [317, 318]
        overlay.tick(game, [device], 0)
        killpg.assert_not_called()
        device.active_keys.return_value = []
        overlay.tick(game, [device], 1)
        overlay.tick(game, [device], 1.2)
        device.grab.assert_called_once()
        killpg.assert_called_once_with(game.pid, session_overlay.signal.SIGSTOP)
        overlay.finish("resume")
        device.active_keys.return_value = [305]
        self.assertIsNone(overlay.tick(game, [device], 2))
        device.active_keys.return_value = []
        self.assertEqual(overlay.tick(game, [device], 3), "resume")
        device.ungrab.assert_called_once()
        self.assertEqual(
            killpg.call_args.args, (game.pid, session_overlay.signal.SIGCONT)
        )

    @patch.object(session_overlay.os, "killpg")
    def test_failed_menu_launch_releases_inputs_and_resumes_game(self, killpg):
        overlay, game, child, device = self.fixture()
        overlay.spawn.side_effect = OSError("missing GTK")
        overlay.tick(game, [device], 0)
        with self.assertRaises(OSError):
            overlay.tick(game, [device], 1)
        device.ungrab.assert_called_once()
        self.assertEqual(
            killpg.call_args.args, (game.pid, session_overlay.signal.SIGCONT)
        )
        self.assertIsNone(overlay.game)

    @patch.object(session_overlay.os, "killpg")
    def test_menu_exit_race_cannot_leave_the_game_stopped(self, killpg):
        overlay, game, child, device = self.fixture()
        overlay.tick(game, [device], 0)
        overlay.tick(game, [device], 1)
        child.terminate.side_effect = ProcessLookupError()
        overlay.close()
        device.ungrab.assert_called_once()
        self.assertEqual(
            killpg.call_args.args, (game.pid, session_overlay.signal.SIGCONT)
        )
        self.assertIsNone(overlay.game)

    @patch.object(session_overlay.os, "killpg")
    def test_unresponsive_menu_startup_resumes_the_game(self, killpg):
        overlay, game, child, device = self.fixture()
        overlay.tick(game, [device], 0)
        overlay.tick(game, [device], 1)
        with self.assertRaises(TimeoutError):
            overlay.tick(game, [device], 7)
        device.ungrab.assert_called_once()
        self.assertEqual(
            killpg.call_args.args, (game.pid, session_overlay.signal.SIGCONT)
        )

    @patch.object(session_overlay.os, "killpg")
    def test_crashed_menu_resumes_and_new_controller_is_grabbed(self, killpg):
        overlay, game, child, device = self.fixture()
        overlay.tick(game, [device], 0)
        overlay.tick(game, [device], 1)
        second = Mock()
        second.active_keys.return_value = []
        second.capabilities.return_value = {}
        overlay.tick(game, [device, second], 2)
        second.grab.assert_called_once()
        child.poll.return_value = 1
        self.assertEqual(overlay.tick(game, [device, second], 3), "resume")
        second.ungrab.assert_called_once()
        self.assertEqual(
            killpg.call_args.args, (game.pid, session_overlay.signal.SIGCONT)
        )
