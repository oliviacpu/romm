"""Translate console profiles into core remaps while keeping menu inputs fixed."""

import ctypes

NAMES = {
    "a": "b",
    "b": "a",
    "x": "y",
    "y": "x",
    "view": "select",
    "menu": "start",
    "lb": "l",
    "rb": "r",
    "lt": "l2",
    "rt": "r2",
    "l3": "l3",
    "r3": "r3",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
}
IDS = {
    "b": 0,
    "y": 1,
    "select": 2,
    "start": 3,
    "up": 4,
    "down": 5,
    "left": 6,
    "right": 7,
    "a": 8,
    "x": 9,
    "l": 10,
    "r": 11,
    "l2": 12,
    "r2": 13,
    "l3": 14,
    "r3": 15,
}


def core_name(path):
    class SystemInfo(ctypes.Structure):
        _fields_ = [
            ("library_name", ctypes.c_char_p),
            ("library_version", ctypes.c_char_p),
            ("valid_extensions", ctypes.c_char_p),
            ("need_fullpath", ctypes.c_bool),
            ("block_extract", ctypes.c_bool),
        ]

    library = ctypes.CDLL(path)
    info = SystemInfo()
    library.retro_get_system_info.argtypes = [ctypes.POINTER(SystemInfo)]
    library.retro_get_system_info.restype = None
    library.retro_get_system_info(ctypes.byref(info))
    name = info.library_name.decode("utf-8")
    if "/" in name or name in (".", ".."):
        raise ValueError("Invalid core name")
    return name


def remap_values(bindings):
    if len(set(bindings.values())) != len(bindings):
        raise ValueError("Controller mappings must assign each physical input once")
    return {NAMES[source]: IDS[NAMES[target]] for target, source in bindings.items()}
