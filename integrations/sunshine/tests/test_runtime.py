import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
