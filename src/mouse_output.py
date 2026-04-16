"""Mouse simulation using Windows SendInput API.

Provides relative mouse movement and button click/release operations.
Used for mapping Joy-Con stick to mouse cursor control.
"""

import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger(__name__)

# SendInput structures
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [
            ("mi", _MOUSEINPUT),
        ]
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _U),
    ]

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

# Mouse button flags
_BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

# Currently held mouse buttons
_held_buttons: set[str] = set()


def _send_mouse_input(dx: int = 0, dy: int = 0, flags: int = 0) -> None:
    inp = _INPUT()
    inp.type = INPUT_MOUSE
    inp._input.mi.dx = dx
    inp._input.mi.dy = dy
    inp._input.mi.mouseData = 0
    inp._input.mi.dwFlags = flags
    inp._input.mi.time = 0
    inp._input.mi.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def move(dx: int, dy: int) -> None:
    """Move mouse cursor by relative offset."""
    if dx == 0 and dy == 0:
        return
    _send_mouse_input(dx=dx, dy=dy, flags=MOUSEEVENTF_MOVE)


def button_down(button: str = "left") -> None:
    """Press a mouse button."""
    if button in _held_buttons:
        return
    flags = _BUTTON_FLAGS.get(button)
    if flags:
        _send_mouse_input(flags=flags[0])
        _held_buttons.add(button)
        logger.debug("mouse down: %s", button)


def button_up(button: str = "left") -> None:
    """Release a mouse button."""
    if button not in _held_buttons:
        return
    flags = _BUTTON_FLAGS.get(button)
    if flags:
        _send_mouse_input(flags=flags[1])
        _held_buttons.discard(button)
        logger.debug("mouse up: %s", button)


def click(button: str = "left") -> None:
    """Click (press and release) a mouse button."""
    flags = _BUTTON_FLAGS.get(button)
    if flags:
        _send_mouse_input(flags=flags[0])
        _send_mouse_input(flags=flags[1])
        logger.debug("mouse click: %s", button)


def release_all() -> None:
    """Release all held mouse buttons."""
    for button in list(_held_buttons):
        button_up(button)
