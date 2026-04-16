import time
import logging

from . import keyboard_output
from .constants import get_button_indices, get_button_names, DUAL_RIGHT_OFFSET
from .constants import BUTTON_INDICES_LEFT, BUTTON_INDICES, LEFT_TO_DUAL_NAMES, RIGHT_TO_DUAL_NAMES
from .switcher_overlay import SwitcherOverlay
from .window_switcher import WindowCycler, get_foreground_process_name, get_foreground_hwnd, find_windows

logger = logging.getLogger(__name__)

LONG_PRESS_THRESHOLD = 0.25


class KeyMapper:
    def __init__(self, config: dict, mode: str = "single_right") -> None:
        self._mode = mode
        self._button_indices = get_button_indices(mode)
        self._button_names = get_button_names(mode)

        mappings = config.get("mappings", {})
        long_threshold = config.get("long_press_threshold", LONG_PRESS_THRESHOLD)

        self._button_mappings: dict[int, dict] = {}

        if mode == "dual":
            self._build_dual_mappings(mappings)
        else:
            for btn_name, mapping in mappings.get("buttons", {}).items():
                if btn_name in self._button_indices:
                    self._button_mappings[self._button_indices[btn_name]] = mapping

        self._direction_mappings: dict[str, dict] = {}
        for direction, mapping in mappings.get("stick_directions", {}).items():
            self._direction_mappings[direction] = mapping

        self._active_holds: dict[int, str] = {}
        self._active_sequences: dict[int, list[str]] = {}
        self._sequence_repeat: dict[int, dict] = {}
        self._stick_repeat: dict[tuple, dict] = {}
        self._auto_pending: dict[int, tuple[str, float]] = {}

        self._long_threshold = long_threshold
        self._stick_enabled: bool = True
        self._window_cycler = WindowCycler()
        self._switcher_overlay: SwitcherOverlay | None = None
        self._ws_held: bool = False
        self._ws_press_time: float = 0.0
        self._ws_overlay_active: bool = False
        self._ws_last_move: float = 0.0
        self._ws_move_interval: float = config.get("switch_scroll_interval", 400) / 1000.0

        logger.info(
            "KeyMapper initialized: %d button mappings, %d direction mappings, "
            "long_press_threshold=%.2fs",
            len(self._button_mappings),
            len(self._direction_mappings),
            self._long_threshold,
        )

    def _on_overlay_select(self, window_info: "WindowInfo") -> None:
        from .window_switcher import switch_to_window
        switch_to_window(window_info.hwnd)

    def set_tk_root(self, root: "tk.Tk") -> None:
        import tkinter as tk
        if isinstance(root, tk.Tk) and self._switcher_overlay is None:
            self._switcher_overlay = SwitcherOverlay(root, on_select=self._on_overlay_select)

    def _find_current_window_index(self, windows: list["WindowInfo"]) -> int:
        hwnd = get_foreground_hwnd()
        for i, w in enumerate(windows):
            if w.hwnd == hwnd:
                return i
        return 0

    def button_down(self, button_index: int) -> None:
        mapping = self._button_mappings.get(button_index)
        if mapping is None:
            return

        action = mapping["action"]
        btn_name = _button_label(button_index, self._mode)

        if action == "hold":
            key = mapping["key"]
            keyboard_output.press(key)
            self._active_holds[button_index] = key
            logger.debug("hold DOWN [%s] → %s", btn_name, key)

        elif action == "tap":
            key = mapping["key"]
            keyboard_output.tap(key)
            logger.debug("tap [%s] → %s", btn_name, key)

        elif action == "auto":
            key = mapping["key"]
            self._auto_pending[button_index] = (key, time.monotonic())
            logger.debug("auto DOWN [%s] → %s (waiting)", btn_name, key)

        elif action == "combination":
            keys = mapping["keys"]
            keyboard_output.send_combination(keys)
            logger.debug("combination [%s] → %s", btn_name, "+".join(keys))

        elif action == "sequence":
            keys = mapping["keys"]
            repeat_ms = mapping.get("repeat", 0)
            keyboard_output.press(keys[0])
            time.sleep(0.02)
            for key in keys[1:]:
                keyboard_output.tap(key)
            self._active_holds[button_index] = "__sequence__"
            self._active_sequences[button_index] = keys
            if repeat_ms > 0 and len(keys) > 1:
                self._sequence_repeat[button_index] = {
                    "keys": keys[1:],
                    "interval": repeat_ms / 1000.0,
                    "last_time": time.monotonic(),
                }
            logger.debug("sequence DOWN [%s] → %s (held, repeat=%sms)",
                         btn_name, "+".join(keys), repeat_ms)

        elif action == "window_switch":
            self._ws_held = True
            self._ws_press_time = time.monotonic()
            self._ws_overlay_active = False
            logger.debug("window_switch DOWN [%s] (waiting)", btn_name)

        elif action == "macro":
            self._execute_macro(mapping, btn_name)

        elif action.startswith("mouse_") and action.endswith("_click"):
            from . import mouse_output
            button = action.replace("mouse_", "").replace("_click", "")
            mouse_output.click(button)
            logger.debug("mouse click [%s] → %s", btn_name, button)

    def button_up(self, button_index: int) -> None:
        btn_name = _button_label(button_index, self._mode)

        if button_index in self._active_sequences:
            self._sequence_repeat.pop(button_index, None)
            keys = self._active_sequences.pop(button_index)
            for key in reversed(keys):
                keyboard_output.release(key)
            logger.debug("sequence UP [%s] → %s released", btn_name, "+".join(keys))
            return

        if button_index in self._active_holds:
            key = self._active_holds.pop(button_index)
            keyboard_output.release(key)
            logger.debug("hold UP [%s] → %s released", btn_name, key)
            return

        if button_index in self._auto_pending:
            key, press_time = self._auto_pending.pop(button_index)
            elapsed = time.monotonic() - press_time

            if elapsed < self._long_threshold:
                keyboard_output.tap(key)
                logger.debug("auto UP [%s] → tap %s (%.0fms)", btn_name, key, elapsed * 1000)
            else:
                keyboard_output.release(key)
                if button_index in self._active_holds:
                    self._active_holds.pop(button_index, None)
                logger.debug("auto UP [%s] → release %s (%.0fms)", btn_name, key, elapsed * 1000)

        if self._ws_held:
            self._ws_held = False
            btn_name = _button_label(button_index, self._mode)

            if self._ws_overlay_active and self._switcher_overlay:
                selected = self._switcher_overlay.selected
                self._switcher_overlay.hide()
                self._ws_overlay_active = False
                if selected:
                    self._on_overlay_select(selected)
                    logger.info("window_switch UP [%s] → selected: %s", btn_name, selected.title)
            else:
                target = self._window_cycler.next()
                if target:
                    logger.info("window_switch UP [%s] → quick: %s", btn_name, target.title)
                else:
                    logger.warning("window_switch UP [%s] → no windows found", btn_name)

    def poll(self) -> None:
        now = time.monotonic()

        for btn_idx in list(self._auto_pending.keys()):
            key, press_time = self._auto_pending[btn_idx]
            if now - press_time >= self._long_threshold:
                keyboard_output.press(key)
                self._active_holds[btn_idx] = key
                btn_name = _button_label(btn_idx, self._mode)
                logger.debug("auto HOLD [%s] → %s (after %.0fms)",
                             btn_name, key, (now - press_time) * 1000)
                del self._auto_pending[btn_idx]

        for btn_idx in list(self._sequence_repeat.keys()):
            info = self._sequence_repeat[btn_idx]
            if now - info["last_time"] >= info["interval"]:
                for key in info["keys"]:
                    keyboard_output.tap(key)
                info["last_time"] = now
                btn_name = _button_label(btn_idx, self._mode)
                logger.debug("sequence repeat [%s] → %s", btn_name, "+".join(info["keys"]))

        for k in list(self._stick_repeat.keys()):
            info = self._stick_repeat[k]
            if now - info["last_time"] >= info["interval"]:
                keyboard_output.tap(info["key"])
                info["last_time"] = now
                logger.debug("stick repeat [%s] → %s", k[1], info["key"])

        if self._ws_held and not self._ws_overlay_active and self._switcher_overlay:
            if now - self._ws_press_time >= self._long_threshold:
                windows = find_windows(self._window_cycler.app_names)
                if windows:
                    initial = self._find_current_window_index(windows)
                    self._switcher_overlay.show(windows, initial_index=initial)
                    self._ws_overlay_active = True
                    self._ws_last_move = now
                    logger.info("window_switch overlay: %d windows", len(windows))

        if self._ws_held and self._ws_overlay_active and self._switcher_overlay:
            if now - self._ws_last_move >= self._ws_move_interval:
                self._switcher_overlay.move_next()
                self._ws_last_move = now

    def _build_dual_mappings(self, mappings: dict) -> None:
        buttons = mappings.get("buttons", {})

        for btn_name, btn_idx in BUTTON_INDICES_LEFT.items():
            dual_name = LEFT_TO_DUAL_NAMES.get(btn_name, btn_name)
            if dual_name in buttons:
                self._button_mappings[btn_idx] = buttons[dual_name]

        for btn_name, btn_idx in BUTTON_INDICES.items():
            dual_name = RIGHT_TO_DUAL_NAMES.get(btn_name, btn_name)
            if dual_name in buttons:
                self._button_mappings[btn_idx + DUAL_RIGHT_OFFSET] = buttons[dual_name]

    def _release_stick_auto(self) -> None:
        stick_keys = [k for k in self._active_holds if isinstance(k, tuple) and k[0] == "stick"]
        for k in stick_keys:
            key = self._active_holds.pop(k)
            keyboard_output.release(key)
            self._stick_repeat.pop(k, None)
            logger.debug("stick release [%s] → %s", k[1], key)

    def stick_direction(self, direction: str) -> None:
        if not self._stick_enabled:
            return

        self._release_stick_auto()

        mapping = self._direction_mappings.get(direction)
        if mapping is None:
            return

        action = mapping["action"]
        if action == "tap":
            keyboard_output.tap(mapping["key"])
            logger.debug("stick [%s] → %s", direction, mapping["key"])
        elif action == "auto":
            key = mapping["key"]
            repeat_ms = mapping.get("repeat", 100)
            keyboard_output.tap(key)
            self._active_holds[("stick", direction)] = key
            self._stick_repeat[("stick", direction)] = {
                "key": key,
                "interval": repeat_ms / 1000.0,
                "last_time": time.monotonic(),
            }
            logger.debug("stick auto [%s] → %s (repeat=%dms)", direction, key, repeat_ms)
        elif action == "combination":
            keyboard_output.send_combination(mapping["keys"])
            logger.debug("stick [%s] → %s", direction, "+".join(mapping["keys"]))

    def stick_centered(self) -> None:
        if not self._stick_enabled:
            return
        self._release_stick_auto()
        logger.debug("stick centered")

    def switch_profile(self, config: dict, mode: str) -> None:
        self.release_all()
        self._mode = mode
        self._button_indices = get_button_indices(mode)
        self._button_names = get_button_names(mode)

        mappings = config.get("mappings", {})

        self._button_mappings.clear()
        if mode == "dual":
            self._build_dual_mappings(mappings)
        else:
            for btn_name, mapping in mappings.get("buttons", {}).items():
                if btn_name in self._button_indices:
                    self._button_mappings[self._button_indices[btn_name]] = mapping

        self._direction_mappings.clear()
        for direction, mapping in mappings.get("stick_directions", {}).items():
            self._direction_mappings[direction] = mapping

        logger.info(
            "Switched to profile '%s': %d button mappings, %d direction mappings",
            mode, len(self._button_mappings), len(self._direction_mappings),
        )

    def release_all(self) -> None:
        self._ws_held = False
        self._ws_overlay_active = False
        if self._switcher_overlay:
            self._switcher_overlay.hide()
        for keys in self._active_sequences.values():
            for key in reversed(keys):
                keyboard_output.release(key)
        self._active_sequences.clear()
        self._sequence_repeat.clear()
        self._stick_repeat.clear()
        for key in self._active_holds.values():
            keyboard_output.release(key)
        self._active_holds.clear()
        self._auto_pending.clear()


    def _execute_macro(self, mapping: dict, btn_name: str) -> None:
        if_window = mapping.get("if_window")
        if if_window:
            fg = get_foreground_process_name()
            if fg != if_window:
                logger.debug("macro [%s] skipped: foreground is '%s', need '%s'",
                             btn_name, fg, if_window)
                return

        steps = mapping.get("steps", [])
        logger.info("macro [%s] executing %d steps", btn_name, len(steps))

        for i, step in enumerate(steps):
            step_type = step.get("type")

            if step_type == "combination":
                keyboard_output.send_combination(step["keys"])
            elif step_type == "tap":
                keyboard_output.tap(step["key"])
            elif step_type == "hold":
                keyboard_output.press(step["key"])
            elif step_type == "release":
                keyboard_output.release(step["key"])
            elif step_type == "type":
                keyboard_output.type_text(step["text"])
            elif step_type == "delay":
                time.sleep(step.get("ms", 100) / 1000.0)
            else:
                logger.warning("macro [%s] unknown step type '%s' at step %d",
                               btn_name, step_type, i)


def _button_label(button_index: int, mode: str = "single_right") -> str:
    if mode == "dual" and button_index >= DUAL_RIGHT_OFFSET:
        real_idx = button_index - DUAL_RIGHT_OFFSET
        name = BUTTON_INDICES.get(real_idx)
        return f"{name}(R)" if name else f"BTN_{real_idx}(R)"
    if mode == "dual":
        name = BUTTON_INDICES_LEFT.get(button_index)
        return f"{name}(L)" if name else f"BTN_{button_index}(L)"
    return get_button_names(mode).get(button_index, f"BTN_{button_index}")
