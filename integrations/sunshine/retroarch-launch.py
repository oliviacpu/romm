#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

import retropad


def launch(
    platform,
    core,
    rom,
    save_root=Path("/saves/retroarch"),
    user_root=Path("/run/emulators/user"),
):
    if not platform.replace("-", "").isalnum():
        raise SystemExit("Invalid platform")
    root = save_root / platform
    saves, states = root / "saves", root / "states"
    for directory in (saves, states):
        directory.mkdir(parents=True, exist_ok=True)
    config = user_root / ("retroarch-" + platform + ".cfg")
    profile = json.loads(os.environ.get("ROMM_EMULATION_PROFILE", "{}"))
    remaps = user_root / ("remaps-" + platform)
    values = {
        "system_directory": "/library/bios/" + platform,
        "savefile_directory": str(saves),
        "savestate_directory": str(states),
        "input_joypad_driver": "sdl2",
        "video_fullscreen": "true",
        "config_save_on_exit": "false",
        "input_menu_toggle_gamepad_combo": "0",
        "input_menu_toggle": "f1",
        "input_menu_toggle_btn": "nul",
        "input_exit_emulator_gamepad_combo": "0",
        "input_exit_emulator_btn": "nul",
        "menu_swap_ok_cancel_buttons": "true",
        "input_remap_binds_enable": "true",
        "input_remapping_directory": str(remaps),
        "video_font_size": str(round(16 * profile.get("osd_scale", 200) / 100)),
    }
    buttons = {
        "b": "0",
        "y": "2",
        "select": "4",
        "start": "6",
        "up": "11",
        "down": "12",
        "left": "13",
        "right": "14",
        "a": "1",
        "x": "3",
        "l": "9",
        "r": "10",
        "l3": "7",
        "r3": "8",
    }
    axes = {
        "l2": "+4",
        "r2": "+5",
        "l_x_plus": "+0",
        "l_x_minus": "-0",
        "l_y_plus": "+1",
        "l_y_minus": "-1",
        "r_x_plus": "+2",
        "r_x_minus": "-2",
        "r_y_plus": "+3",
        "r_y_minus": "-3",
    }
    name = retropad.core_name(core)
    remap = remaps / name / (name + ".rmp")
    remap.parent.mkdir(parents=True, exist_ok=True)
    mapped = retropad.remap_values(profile.get("bindings", {}))
    remap.write_text(
        "".join(
            f'input_player{player}_btn_{key} = "{value}"\n'
            for player in range(1, 5)
            for key, value in mapped.items()
        )
    )
    for player in range(1, 5):
        for key, value in buttons.items():
            values[f"input_player{player}_{key}_btn"] = value
        for key, value in axes.items():
            values[f"input_player{player}_{key}_axis"] = value
    config.write_text("".join(f'{key} = "{value}"\n' for key, value in values.items()))
    # Fixed emulator path; content and core come from the pinned system table.
    # trunk-ignore(bandit/B606)
    os.execv(
        "/usr/bin/retroarch", ["/usr/bin/retroarch", "-c", str(config), "-L", core, rom]
    )


if __name__ == "__main__":
    launch(*sys.argv[1:])
