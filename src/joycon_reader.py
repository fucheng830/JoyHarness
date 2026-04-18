"""pygame-based Joy-Con R detection and polling loop.

Handles controller discovery, button state polling, axis reading,
disconnection detection, and automatic reconnection.
"""

from __future__ import annotations

import threading
import time
import logging

import pygame

from .constants import (
    AXIS_RSTICK_X,
    AXIS_RSTICK_Y,
    BUTTON_NAMES,
    BUTTON_NAMES_LEFT,
    BUTTON_INDICES_LEFT,
    BUTTON_INDICES,
    DUAL_RIGHT_OFFSET,
    LEFT_TO_DUAL_NAMES,
    RIGHT_TO_DUAL_NAMES,
    SNAPBACK_FRAMES,
)
from .joystick_handler import apply_deadzone, get_direction
from .key_mapper import KeyMapper

logger = logging.getLogger(__name__)

# Reconnection scan interval in seconds
RECONNECT_INTERVAL = 2.0


def find_joycon(joystick_index: int | None = None) -> pygame.joystick.Joystick | None:
    """Find and return a Joy-Con joystick instance.

    Args:
        joystick_index: Specific device index to use. None for auto-detection.

    Returns:
        pygame Joystick instance, or None if not found.
    """
    pygame.joystick.init()
    count = pygame.joystick.get_count()

    if count == 0:
        return None

    logger.info("Found %d joystick(s)", count)

    if joystick_index is not None:
        if 0 <= joystick_index < count:
            js = pygame.joystick.Joystick(joystick_index)
            logger.info("Using joystick #%d: %s", joystick_index, js.get_name())
            return js
        logger.error("Joystick index %d out of range (0-%d)", joystick_index, count - 1)
        return None

    # Auto-detect: look for Joy-Con in device names (accept both L and R)
    for i in range(count):
        js = pygame.joystick.Joystick(i)
        name = js.get_name().lower()
        logger.info("  [%d] %s (buttons=%d, axes=%d)",
                     i, js.get_name(), js.get_numbuttons(), js.get_numaxes())

        if "joy-con" in name or "joy con" in name or "switch" in name or "pro controller" in name:
            logger.info("Auto-selected joystick [%d]: %s", i, js.get_name())
            return js

    # Fallback: if only one joystick, use it
    if count == 1:
        js = pygame.joystick.Joystick(0)
        logger.info("Single joystick found, using: %s", js.get_name())
        return js

    logger.warning("No Joy-Con detected among %d joysticks", count)
    return None


def find_both_joycons() -> tuple[pygame.joystick.Joystick | None, pygame.joystick.Joystick | None]:
    """Find and return left and right Joy-Con joystick instances.

    Returns:
        (left_js, right_js) tuple. Either may be None if not found.
    """
    pygame.joystick.init()
    count = pygame.joystick.get_count()

    left_js = None
    right_js = None

    for i in range(count):
        js = pygame.joystick.Joystick(i)
        name = js.get_name().lower()

        if not any(kw in name for kw in ("joy-con", "joy con", "switch", "pro controller")):
            continue

        if "l" in name and "r" not in name:
            left_js = js
            logger.info("Left Joy-Con [%d]: %s (buttons=%d, axes=%d)",
                        i, js.get_name(), js.get_numbuttons(), js.get_numaxes())
        elif "r" in name and "l" not in name:
            right_js = js
            logger.info("Right Joy-Con [%d]: %s (buttons=%d, axes=%d)",
                        i, js.get_name(), js.get_numbuttons(), js.get_numaxes())

    return left_js, right_js


def detect_connection_mode() -> str:
    """Detect the Joy-Con connection mode from connected joysticks.

    Scans all connected pygame joysticks and determines whether only a
    left Joy-Con, only a right Joy-Con, or both (dual/combined) are connected.

    Returns:
        One of "single_left", "single_right", or "dual".
    """
    count = pygame.joystick.get_count()

    if count == 0:
        return "single_right"

    has_left = False
    has_right = False

    for i in range(count):
        try:
            js = pygame.joystick.Joystick(i)
        except Exception:
            continue
        name = js.get_name().lower()

        # Skip non-Joy-Con devices
        if not any(kw in name for kw in ("joy-con", "joy con", "switch", "pro controller")):
            continue

        # Check for combined device (contains both "l" and "r")
        if "l" in name and "r" in name:
            logger.debug("Detected combined Joy-Con device: %s", js.get_name())
            return "dual"

        if "l" in name:
            has_left = True
        elif "r" in name:
            has_right = True
        else:
            # Unidentified side — check number of buttons as heuristic
            # Combined devices typically have 20+ buttons
            if js.get_numbuttons() >= 18:
                logger.debug("Detected combined Joy-Con device (high button count): %s", js.get_name())
                return "dual"
            # Default to right if single device
            has_right = True

    if has_left and has_right:
        logger.debug("Detected both L and R Joy-Cons (separate devices)")
        return "dual"
    elif has_left:
        logger.debug("Detected single left Joy-Con")
        return "single_left"
    else:
        logger.debug("Detected single right Joy-Con")
        return "single_right"


def run_discover_mode(joystick_index: int | None = None) -> None:
    """Run discovery mode: print raw button/axis values for calibration.

    Press Ctrl+C to exit. Use this to determine correct button indices
    for your specific controller/driver combination.
    """
    pygame.init()
    js = find_joycon(joystick_index)

    if js is None:
        print("No joystick found. Make sure your Joy-Con R is connected via Bluetooth.")
        print("Tip: Windows Settings → Bluetooth → Add device → hold the small pairing")
        print("     button on the Joy-Con rail for 3 seconds until lights flash.")
        pygame.quit()
        return

    print(f"\n=== Discovery Mode ===")
    print(f"Controller: {js.get_name()}")
    print(f"GUID: {js.get_guid()}")
    print(f"Buttons: {js.get_numbuttons()}")
    print(f"Axes: {js.get_numaxes()}")
    print(f"\nPress buttons and move sticks to see their indices.")
    print(f"Press Ctrl+C to exit.\n")

    clock = pygame.time.Clock()
    prev_buttons: set[int] = set()

    try:
        while True:
            pygame.event.pump()

            # Button state
            current_buttons: set[int] = set()
            for i in range(js.get_numbuttons()):
                if js.get_button(i):
                    current_buttons.add(i)

            pressed = current_buttons - prev_buttons
            released = prev_buttons - current_buttons

            for i in sorted(pressed):
                name = BUTTON_NAMES.get(i, "???")
                print(f"  BTN {i:2d} ({name:8s}) PRESSED")

            for i in sorted(released):
                name = BUTTON_NAMES.get(i, "???")
                print(f"  BTN {i:2d} ({name:8s}) released")

            prev_buttons = current_buttons

            # Axis state (only print if changed significantly)
            for i in range(js.get_numaxes()):
                val = js.get_axis(i)
                if abs(val) > 0.1:
                    print(f"  AXIS {i}: {val:+.3f}", end="\r")

            clock.tick(60)

    except KeyboardInterrupt:
        print("\nDiscovery mode ended.")
    finally:
        pygame.quit()


def _calibrate_baseline(
    joystick: pygame.joystick.Joystick,
    axis_x: int,
    axis_y: int,
    samples: int = 20,
) -> tuple[float, float]:
    """Read stick resting position and return average as baseline.

    Should be called at startup with the stick at rest.
    """
    num_axes = joystick.get_numaxes()
    if axis_x >= num_axes or axis_y >= num_axes:
        logger.warning("Axis index out of range (axes=%d, x=%d, y=%d), using (0,0) baseline",
                       num_axes, axis_x, axis_y)
        return (0.0, 0.0)

    clock = pygame.time.Clock()
    total_x = 0.0
    total_y = 0.0

    for _ in range(samples):
        pygame.event.pump()
        total_x += joystick.get_axis(axis_x)
        total_y += joystick.get_axis(axis_y)
        clock.tick(100)

    return (total_x / samples, total_y / samples)


def run_polling_loop(
    joystick: pygame.joystick.Joystick,
    key_mapper: KeyMapper,
    config: dict,
    stop_event: threading.Event | None = None,
    on_mode_change: callable = None,
    joystick2: pygame.joystick.Joystick | None = None,
    gyro_mouse=None,
) -> None:
    """Main polling loop: read controller state and dispatch to key_mapper.

    Args:
        joystick: Primary pygame Joystick instance (left in dual mode).
        key_mapper: KeyMapper instance for action dispatch.
        config: Complete configuration dict.
        stop_event: Threading event to signal loop exit. None = run until Ctrl+C.
        joystick2: Optional second Joystick for dual mode (right Joy-Con).
        gyro_mouse: Optional GyroMouseReader to restart on reconnection.
    """
    from .config_loader import get_profile

    def _restart_gyro():
        """Restart gyro mouse after reconnection if it was enabled."""
        if gyro_mouse is None:
            return
        gyro_mouse.join(timeout=1.0)
        if config.get("gyro_mouse_enabled", False):
            gyro_mouse.start()
            logger.info("Gyro mouse restarted after reconnection")

    deadzone = config.get("deadzone", 0.2)
    poll_interval = max(config.get("poll_interval", 0.01), 0.001)
    stick_mode = config.get("stick_mode", "4dir")
    axis_x = config.get("axis_x", AXIS_RSTICK_X)
    axis_y = config.get("axis_y", AXIS_RSTICK_Y)

    is_dual = joystick2 is not None
    right_stick_mouse_mode = config.get("right_stick_mouse", False) and is_dual
    mouse_sensitivity = config.get("mouse_sensitivity", 15)

    clock = pygame.time.Clock()
    prev_buttons: set[int] = set()
    prev_buttons2: set[int] = set()
    prev_direction: str | None = None
    prev_direction2: str | None = None
    prev_mouse_active: bool = False
    last_stick_fire: float = 0.0
    last_stick_fire2: float = 0.0
    stick_cooldown: float = 0.15  # Minimum seconds between same-direction triggers
    center_count: int = 0
    center_count2: int = 0

    # Connection mode tracking — check every 5 seconds
    current_mode = config.get("active_profile", "single_right")
    mode_check_interval = 5.0  # seconds

    # Disconnect detection: count consecutive idle frames (all buttons zero + stick centered)
    idle_frame_count: int = 0
    idle_disconnect_threshold: int = 500  # ~5 seconds at 100Hz polling
    last_mode_check = time.monotonic()

    logger.info("Polling started (deadzone=%.2f, interval=%.0fms, mode=%s, dual=%s, mouse=%s, sens=%d)",
                deadzone, poll_interval * 1000, stick_mode, is_dual, right_stick_mouse_mode, mouse_sensitivity)

    # Calibrate baseline for primary joystick
    baseline_x, baseline_y = _calibrate_baseline(joystick, axis_x, axis_y)
    logger.info("Stick1 baseline: x=%.4f, y=%.4f", baseline_x, baseline_y)

    # Calibrate baseline for second joystick
    baseline2_x, baseline2_y = 0.0, 0.0
    if is_dual:
        baseline2_x, baseline2_y = _calibrate_baseline(joystick2, axis_x, axis_y)
        logger.info("Stick2 baseline: x=%.4f, y=%.4f", baseline2_x, baseline2_y)

    try:
        while not (stop_event and stop_event.is_set()):
            try:
                pygame.event.pump()
            except pygame.error:
                # Joystick was disconnected
                logger.warning("Joystick disconnected, attempting reconnection...")
                key_mapper.release_all()
                from . import keyboard_output
                keyboard_output.release_all()

                js = wait_for_reconnection()
                if js is None or (stop_event and stop_event.is_set()):
                    break

                # Re-initialize with the new joystick
                joystick = js
                prev_buttons = set()
                prev_direction = None
                center_count = 0
                baseline_x, baseline_y = _calibrate_baseline(joystick, axis_x, axis_y)
                logger.info("Reconnected: %s, baseline=(%.4f, %.4f)",
                            js.get_name(), baseline_x, baseline_y)

                _restart_gyro()

                # Re-detect connection mode after reconnection
                try:
                    detected_mode = detect_connection_mode()
                    if detected_mode != current_mode:
                        logger.info("Connection mode changed after reconnect: %s → %s",
                                    current_mode, detected_mode)
                        profile = get_profile(config, detected_mode)
                        profile_mappings = profile.get("mappings", config.get("mappings", {}))
                        config["mappings"] = profile_mappings
                        config["active_profile"] = detected_mode
                        key_mapper.switch_profile(config, detected_mode)
                        current_mode = detected_mode
                        if on_mode_change:
                            on_mode_change(detected_mode)
                except Exception:
                    logger.debug("Mode check after reconnect failed", exc_info=True)

                continue

            # --- Button polling (primary joystick) ---
            current_buttons: set[int] = set()
            for i in range(joystick.get_numbuttons()):
                if joystick.get_button(i):
                    current_buttons.add(i)

            pressed = current_buttons - prev_buttons
            released = prev_buttons - current_buttons

            for btn_idx in sorted(pressed):
                key_mapper.button_down(btn_idx)

            for btn_idx in sorted(released):
                key_mapper.button_up(btn_idx)

            prev_buttons = current_buttons

            # --- Disconnect detection ---
            # pygame may not throw an error when Bluetooth Joy-Con disconnects.
            # Detect by checking if device count drops or if input is completely idle.
            if pygame.joystick.get_count() == 0:
                logger.warning("No joysticks found, device likely disconnected")
                key_mapper.release_all()
                from . import keyboard_output
                keyboard_output.release_all()
                js = wait_for_reconnection()
                if js is None or (stop_event and stop_event.is_set()):
                    break
                joystick = js
                prev_buttons = set()
                prev_direction = None
                center_count = 0
                idle_frame_count = 0
                baseline_x, baseline_y = _calibrate_baseline(joystick, axis_x, axis_y)
                logger.info("Reconnected: %s, baseline=(%.4f, %.4f)", js.get_name(), baseline_x, baseline_y)
                _restart_gyro()
                try:
                    detected_mode = detect_connection_mode()
                    if detected_mode != current_mode:
                        logger.info("Connection mode changed: %s → %s", current_mode, detected_mode)
                        profile = get_profile(config, detected_mode)
                        profile_mappings = profile.get("mappings", config.get("mappings", {}))
                        config["mappings"] = profile_mappings
                        config["active_profile"] = detected_mode
                        key_mapper.switch_profile(config, detected_mode)
                        current_mode = detected_mode
                        if on_mode_change:
                            on_mode_change(detected_mode)
                except Exception:
                    logger.debug("Mode check after reconnect failed", exc_info=True)
                continue

            # --- Button polling (second joystick, dual mode) ---
            if is_dual:
                try:
                    pygame.event.pump()
                except pygame.error:
                    pass
                current_buttons2: set[int] = set()
                for i in range(joystick2.get_numbuttons()):
                    if joystick2.get_button(i):
                        current_buttons2.add(i + DUAL_RIGHT_OFFSET)

                pressed2 = current_buttons2 - prev_buttons2
                released2 = prev_buttons2 - current_buttons2

                for btn_idx in sorted(pressed2):
                    key_mapper.button_down(btn_idx)

                for btn_idx in sorted(released2):
                    key_mapper.button_up(btn_idx)

                prev_buttons2 = current_buttons2

            # --- Stick polling (primary joystick) ---
            if config.get("stick_enabled", True):
                raw_x = joystick.get_axis(axis_x) - baseline_x
                raw_y = joystick.get_axis(axis_y) - baseline_y
                filt_x, filt_y = apply_deadzone(raw_x, raw_y, deadzone)
                direction = get_direction(filt_x, filt_y, stick_mode)

                if direction is not None:
                    center_count = 0
                    if prev_direction == direction:
                        now_stick = time.monotonic()
                        if now_stick - last_stick_fire > 3.0:
                            logger.debug("stick held: dir=%s filt=%.3f,%.3f",
                                         direction, filt_x, filt_y)
                            last_stick_fire = now_stick
                    else:
                        now_stick = time.monotonic()
                        if now_stick - last_stick_fire >= stick_cooldown:
                            key_mapper.stick_direction(direction)
                            last_stick_fire = now_stick
                        prev_direction = direction
                else:
                    if prev_direction is not None:
                        key_mapper.stick_centered()
                    prev_direction = None
                    center_count = 0
            else:
                if prev_direction is not None:
                    key_mapper.stick_centered()
                    prev_direction = None

            # --- Stick polling (second joystick, dual mode) ---
            if is_dual:
                raw2_x = joystick2.get_axis(axis_x) - baseline2_x
                raw2_y = joystick2.get_axis(axis_y) - baseline2_y
                filt2_x, filt2_y = apply_deadzone(raw2_x, raw2_y, deadzone)

                if right_stick_mouse_mode:
                    # Mouse mode: analog stick → relative mouse movement
                    # Use high deadzone to prevent drift from noisy resting position
                    mouse_deadzone = max(deadzone, 0.5)
                    filt2_x, filt2_y = apply_deadzone(raw2_x, raw2_y, mouse_deadzone)
                    if abs(filt2_x) > 0.1 or abs(filt2_y) > 0.1:
                        dx = int(filt2_x * mouse_sensitivity)
                        dy = int(-filt2_y * mouse_sensitivity)
                        if dx != 0 or dy != 0:
                            from . import mouse_output
                            mouse_output.move(dx, dy)
                            logger.debug("mouse move: dx=%d, dy=%d (raw=%.3f,%.3f filt=%.3f,%.3f)",
                                         dx, dy, raw2_x, raw2_y, filt2_x, filt2_y)
                    elif prev_mouse_active:
                        pass  # Stick returned to center
                    prev_mouse_active = True
                else:
                    prev_mouse_active = False
                    direction2 = get_direction(filt2_x, filt2_y, stick_mode)

                    if direction2 != prev_direction2:
                        if direction2 is None:
                            key_mapper.stick_centered()
                            prev_direction2 = None
                            center_count2 = 0
                        else:
                            center_count2 = 0
                            now_stick2 = time.monotonic()
                            if now_stick2 - last_stick_fire2 >= stick_cooldown:
                                key_mapper.stick_direction(direction2)
                                last_stick_fire2 = now_stick2
                            prev_direction2 = direction2

            # Periodic connection mode check (detect Joy-Con hot-plug changes)
            now = time.monotonic()
            if now - last_mode_check >= mode_check_interval:
                last_mode_check = now
                try:
                    detected_mode = detect_connection_mode()
                    if detected_mode != current_mode:
                        logger.info("Connection mode changed: %s → %s", current_mode, detected_mode)
                        profile = get_profile(config, detected_mode)
                        profile_mappings = profile.get("mappings", config.get("mappings", {}))
                        config["mappings"] = profile_mappings
                        config["active_profile"] = detected_mode
                        key_mapper.switch_profile(config, detected_mode)
                        current_mode = detected_mode
                        if on_mode_change:
                            on_mode_change(detected_mode)
                except Exception:
                    logger.debug("Connection mode check failed", exc_info=True)

            # Process auto-action long press detection
            key_mapper.poll()

            clock.tick(1 / poll_interval)

    except KeyboardInterrupt:
        logger.info("Polling interrupted by user")
    finally:
        key_mapper.release_all()
        from . import keyboard_output
        keyboard_output.release_all()


def wait_for_reconnection(joystick_index: int | None = None) -> pygame.joystick.Joystick | None:
    """Scan for Joy-Con reconnection every RECONNECT_INTERVAL seconds.

    Returns a new Joystick instance when found, or None if interrupted.
    """
    logger.info("Controller disconnected. Waiting for reconnection...")

    try:
        while True:
            time.sleep(RECONNECT_INTERVAL)
            # Re-init joystick subsystem to scan for new devices
            pygame.joystick.quit()
            pygame.joystick.init()
            js = find_joycon(joystick_index)
            if js is not None:
                logger.info("Controller reconnected: %s", js.get_name())
                return js
    except KeyboardInterrupt:
        return None
