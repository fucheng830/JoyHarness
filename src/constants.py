"""Joy-Con hardware constants for pygame button/axis mapping.

NOTE: Button and axis indices are based on SDL2's Switch controller mapping.
These MUST be verified using `python src/main.py --discover` mode,
as indices may vary across SDL2 versions and Windows driver updates.

Three connection modes are supported:
- single_right: Only right Joy-Con connected
- single_left:  Only left Joy-Con connected
- dual:         Both Joy-Cons connected (as a combined SDL2 device)
"""

# === Right Joy-Con Button Indices (calibrated 2026-04-09) ===
# Face buttons
BTN_X = 0       # X (上位)
BTN_A = 1       # A (右位)
BTN_Y = 2       # Y (左位)
BTN_B = 3       # B (下位)

# System / Home
BTN_HOME = 5    # Home (圆形)
BTN_PLUS = 6    # + 按钮
BTN_RSTICK = 7  # 摇杆按下

# Shoulder / trigger
BTN_SL = 9      # SL (侧边左)
BTN_R = 16      # R 肩键
BTN_SR = 10     # SR (侧边右)
BTN_ZR = 18     # ZR 扳机

# === Left Joy-Con Button Indices (calibrated 2026-04-16) ===
BTN_L_X = 0       # X
BTN_L_A = 1       # A
BTN_L_Y = 2       # Y
BTN_L_B = 3       # B
BTN_L_CAPTURE = 5 # Capture 按钮
BTN_L_MINUS = 6   # - 按钮
BTN_L_LSTICK = 7  # 左摇杆按下 (待确认)
BTN_L_SL = 9      # SL
BTN_L_SR = 10     # SR
BTN_L_L = 17      # L 肩键
BTN_L_ZL = 19     # ZL 扳机

# === Dual Mode: Separate Device Support ===
# With SDL_JOYSTICK_HIDAPI_COMBINE_JOY_CONS=0, L and R Joy-Cons are separate devices.
# Each device uses its own button indices (same as single_left/single_right).
# Right device buttons are offset by DUAL_RIGHT_OFFSET to avoid index conflicts.

DUAL_RIGHT_OFFSET = 100  # Offset for right device button indices

# Dual mode uses single_left and single_right button indices directly.
# No separate BTN_DUAL_* constants needed — mapping is done via name lookup.
# Left device: BUTTON_INDICES_LEFT → dual button names
# Right device: BUTTON_INDICES (right) → dual button names
# Right device buttons are stored with +DUAL_RIGHT_OFFSET in key_mapper.

# === Axis Indices (calibrated) ===
AXIS_RSTICK_Y = 0   # 垂直 (上=负, 下=正)
AXIS_RSTICK_X = 1   # 水平 (左=负, 右=正)

# === Default Values ===
DEFAULT_DEADZONE = 0.2
DIRECTION_THRESHOLD = 0.5
POLL_INTERVAL = 0.01       # 100Hz polling
SNAPBACK_FRAMES = 2        # Frames required at center before registering release

# === Right Joy-Con Button Name Lookup ===
BUTTON_NAMES: dict[int, str] = {
    BTN_A: "A",
    BTN_B: "B",
    BTN_X: "X",
    BTN_Y: "Y",
    BTN_R: "R",
    BTN_ZR: "ZR",
    BTN_PLUS: "Plus",
    BTN_RSTICK: "RStick",
    BTN_HOME: "Home",
    BTN_SL: "SL",
    BTN_SR: "SR",
}

# Reverse lookup: name → index
BUTTON_INDICES: dict[str, int] = {v: k for k, v in BUTTON_NAMES.items()}

# === Left Joy-Con Button Name Lookup ===
BUTTON_NAMES_LEFT: dict[int, str] = {
    BTN_L_A: "A",
    BTN_L_B: "B",
    BTN_L_X: "X",
    BTN_L_Y: "Y",
    BTN_L_L: "L",
    BTN_L_ZL: "ZL",
    BTN_L_MINUS: "Minus",
    BTN_L_CAPTURE: "Capture",
    BTN_L_LSTICK: "LStick",
    BTN_L_SL: "SL",
    BTN_L_SR: "SR",
}
BUTTON_INDICES_LEFT: dict[str, int] = {v: k for k, v in BUTTON_NAMES_LEFT.items()}

# === Dual Mode Button Name Lookup (for config validation / GUI only) ===
# In dual mode with separate devices, button mapping is built from
# LEFT_TO_DUAL_NAMES / RIGHT_TO_DUAL_NAMES in key_mapper.
DUAL_BUTTON_NAMES: tuple[str, ...] = (
    "A_L", "B_L", "X_L", "Y_L", "A_R", "B_R", "X_R", "Y_R",
    "R", "ZR", "L", "ZL", "Plus", "Minus",
    "Home", "Capture", "RStick", "LStick", "SL_L", "SR_L", "SL_R", "SR_R",
)
BUTTON_NAMES_DUAL: dict[int, str] = {i: name for i, name in enumerate(DUAL_BUTTON_NAMES)}
BUTTON_INDICES_DUAL: dict[str, int] = {name: i for i, name in enumerate(DUAL_BUTTON_NAMES)}

# Name translation: device button name → dual profile button name
LEFT_TO_DUAL_NAMES: dict[str, str] = {
    "A": "A_L", "B": "B_L", "X": "X_L", "Y": "Y_L",
    "L": "L", "ZL": "ZL", "Minus": "Minus", "Capture": "Capture",
    "LStick": "LStick", "SL": "SL_L", "SR": "SR_L",
}
RIGHT_TO_DUAL_NAMES: dict[str, str] = {
    "A": "A_R", "B": "B_R", "X": "X_R", "Y": "Y_R",
    "R": "R", "ZR": "ZR", "Plus": "Plus", "Home": "Home",
    "RStick": "RStick", "SL": "SL_R", "SR": "SR_R",
}

# === Mode-based lookup tables ===
BUTTON_NAMES_BY_MODE: dict[str, dict[int, str]] = {
    "single_right": BUTTON_NAMES,
    "single_left": BUTTON_NAMES_LEFT,
    "dual": BUTTON_NAMES_DUAL,
}

BUTTON_INDICES_BY_MODE: dict[str, dict[str, int]] = {
    "single_right": BUTTON_INDICES,
    "single_left": BUTTON_INDICES_LEFT,
    "dual": BUTTON_INDICES_DUAL,
}

MAPPABLE_BUTTONS_BY_MODE: dict[str, tuple[str, ...]] = {
    "single_right": ("A", "B", "X", "Y", "R", "ZR", "Plus", "Home", "RStick", "SL", "SR"),
    "single_left": ("A", "B", "X", "Y", "L", "ZL", "Minus", "Capture", "LStick", "SL", "SR"),
    "dual": ("A_L", "B_L", "X_L", "Y_L", "A_R", "B_R", "X_R", "Y_R",
             "R", "ZR", "L", "ZL", "Plus", "Minus", "Home",
             "RStick", "LStick", "Capture", "SL_L", "SR_L", "SL_R", "SR_R"),
}

MODE_LABELS: dict[str, str] = {
    "single_right": "右手柄",
    "single_left": "左手柄",
    "dual": "左右手柄",
}


def get_button_names(mode: str = "single_right") -> dict[int, str]:
    """Get button name lookup table for a connection mode."""
    return BUTTON_NAMES_BY_MODE.get(mode, BUTTON_NAMES)


def get_button_indices(mode: str = "single_right") -> dict[str, int]:
    """Get button index lookup table for a connection mode."""
    return BUTTON_INDICES_BY_MODE.get(mode, BUTTON_INDICES)


# === Stick Direction Names ===
STICK_DIRECTIONS = ("up", "down", "left", "right", "up-left", "up-right", "down-left", "down-right")

# === Default Key Mapping (used when no config file is loaded) ===
DEFAULT_MAPPINGS: dict = {
    "buttons": {
        "A":      {"action": "tap", "key": "enter"},
        "B":      {"action": "sequence", "keys": ["shift", "tab"]},
        "X":      {"action": "auto", "key": "f2"},
        "Y":      {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        "R":      {"action": "window_switch"},
        "ZR":     {
            "action": "macro",
            "if_window": "code.exe",
            "steps": [
                {"type": "combination", "keys": ["ctrl", "shift", "p"]},
                {"type": "delay", "ms": 100},
                {"type": "type", "text": "Claude Code: Focus input"},
                {"type": "delay", "ms": 100},
                {"type": "tap", "key": "enter"},
            ],
        },
        "Plus":   {"action": "combination", "keys": ["ctrl", "s"]},
        "Home":   {"action": "combination", "keys": ["ctrl", "c"]},
        "RStick": {"action": "combination", "keys": ["ctrl", "v"]},
        "SL":     {"action": "hold", "key": "alt"},
        "SR":     {"action": "window_switch"},
    },
    "stick_directions": {
        "up":    {"action": "scroll_up"},
        "down":  {"action": "scroll_down"},
        "left":  {"action": "auto", "key": "up", "repeat": 100},
        "right": {"action": "auto", "key": "down", "repeat": 100},
    },
}

DEFAULT_MAPPINGS_LEFT: dict = {
    "buttons": {
        "A":       {"action": "tap", "key": "enter"},
        "B":       {"action": "tap", "key": "escape"},
        "X":       {"action": "tap", "key": "backspace"},
        "Y":       {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        "L":       {"action": "window_switch"},
        "ZL":      {"action": "hold", "key": "ctrl"},
        "Minus":   {"action": "combination", "keys": ["ctrl", "s"]},
        "Capture": {"action": "tap", "key": "print_screen"},
        "LStick":  {"action": "tap", "key": "tab"},
        "SL":      {"action": "hold", "key": "shift"},
        "SR":      {"action": "window_switch"},
    },
    "stick_directions": {
        "up":    {"action": "tap", "key": "up"},
        "down":  {"action": "tap", "key": "down"},
        "left":  {"action": "tap", "key": "left"},
        "right": {"action": "tap", "key": "right"},
    },
}

DEFAULT_MAPPINGS_DUAL: dict = {
    "buttons": {
        "A_L":     {"action": "tap", "key": "enter"},
        "B_L":     {"action": "sequence", "keys": ["shift", "tab"]},
        "X_L":     {"action": "auto", "key": "f2"},
        "Y_L":     {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        "A_R":     {"action": "mouse_left_click"},
        "B_R":     {"action": "mouse_right_click"},
        "X_R":     {"action": "auto", "key": "f2"},
        "Y_R":     {"action": "sequence", "keys": ["alt", "tab"], "repeat": 500},
        "R":       {"action": "window_switch"},
        "ZR":     {
            "action": "macro",
            "if_window": "code.exe",
            "steps": [
                {"type": "combination", "keys": ["ctrl", "shift", "p"]},
                {"type": "delay", "ms": 100},
                {"type": "type", "text": "Claude Code: Focus input"},
                {"type": "delay", "ms": 100},
                {"type": "tap", "key": "enter"},
            ],
        },
        "L":       {"action": "hold", "key": "ctrl"},
        "ZL":      {"action": "hold", "key": "shift"},
        "Plus":    {"action": "combination", "keys": ["ctrl", "s"]},
        "Minus":   {"action": "tap", "key": "escape"},
        "Home":    {"action": "combination", "keys": ["ctrl", "c"]},
        "Capture": {"action": "tap", "key": "print_screen"},
        "RStick":  {"action": "combination", "keys": ["ctrl", "v"]},
        "LStick":  {"action": "tap", "key": "enter"},
        "SL_L":    {"action": "hold", "key": "alt"},
        "SR_L":    {"action": "window_switch"},
        "SL_R":    {"action": "hold", "key": "alt"},
        "SR_R":    {"action": "window_switch"},
    },
    "stick_directions": {
        "up":    {"action": "scroll_up"},
        "down":  {"action": "scroll_down"},
        "left":  {"action": "tap", "key": "left"},
        "right": {"action": "tap", "key": "right"},
    },
}

DEFAULT_CONFIG: dict = {
    "version": "1.0",
    "description": "Default Joy-Con R to keyboard mapping",
    "deadzone": DEFAULT_DEADZONE,
    "poll_interval": POLL_INTERVAL,
    "stick_mode": "4dir",
    "stick_enabled": False,
    "keep_alive_enabled": True,
    "gyro_mouse_enabled": False,
    "gyro_mouse_sensitivity": 0.7,
    "gyro_mouse_side": "R",
    "gyro_mouse_calibration": 40.0,
    "gyro_mouse_cutoff": 5.0,
    "gyro_mouse_smooth": 0.125,
    "mappings": DEFAULT_MAPPINGS,
}

DEFAULT_CONFIG_LEFT: dict = {
    "version": "1.0",
    "description": "Default Joy-Con L to keyboard mapping",
    "deadzone": DEFAULT_DEADZONE,
    "poll_interval": POLL_INTERVAL,
    "stick_mode": "4dir",
    "stick_enabled": True,
    "keep_alive_enabled": True,
    "mappings": DEFAULT_MAPPINGS_LEFT,
}

DEFAULT_CONFIG_DUAL: dict = {
    "version": "1.0",
    "description": "Default Joy-Con L+R to keyboard mapping",
    "deadzone": DEFAULT_DEADZONE,
    "poll_interval": POLL_INTERVAL,
    "stick_mode": "4dir",
    "stick_enabled": True,
    "keep_alive_enabled": True,
    "mappings": DEFAULT_MAPPINGS_DUAL,
}

DEFAULT_CONFIGS: dict[str, dict] = {
    "single_right": DEFAULT_CONFIG,
    "single_left": DEFAULT_CONFIG_LEFT,
    "dual": DEFAULT_CONFIG_DUAL,
}

VALID_ACTIONS = ("tap", "hold", "auto", "combination", "sequence", "window_switch", "window_switch_next", "window_switch_prev", "macro",
                  "mouse_left_click", "mouse_right_click", "mouse_middle_click",
                  "scroll_up", "scroll_down")

__version__ = "1.0.0"
