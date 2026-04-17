"""Joy-Con gyroscope mouse control — based on JoyShockMapper / GyroMouse algorithm.

Core formula per frame:
    delta_degrees = gyro_velocity_dps × sensitivity × dt
    delta_pixels  = delta_degrees × real_world_calibration

Features from proven implementations:
  - Sub-pixel accumulator: prevents cursor stutter from integer truncation
  - Moving average smoothing (125ms window): reduces jitter
  - Soft deadzone (cutoff_recovery): linear ramp near threshold, no hard cut
  - Calibration at startup: median of gyro readings when stationary

Does NOT send any HID subcommands.
"""

import collections
import logging
import struct
import threading
import time

import hid

from . import mouse_output

logger = logging.getLogger(__name__)

_VID = 0x057E
_PID_L = 0x2006
_PID_R = 0x2007

_GYRO_SENSITIVITY = 0.06103  # dps per LSB (±2000 dps)

# Calibration
_CAL_SAMPLES = 200
_CAL_WARMUP = 30

_IMU_SAMPLE_OFFSETS = (13, 25, 37)


class GyroMouseReader:
    """Gyro angular velocity → relative mouse movement (JoyShockMapper-style)."""

    def __init__(
        self,
        stop_event: threading.Event,
        sensitivity: float = 0.4,
        side: str = "R",
        real_world_calibration: float = 40.0,
        cutoff_recovery: float = 5.0,
        smooth_time: float = 0.125,
    ) -> None:
        self._stop_event = stop_event
        self._gyro_stop = threading.Event()  # Independent stop signal for gyro thread
        self._sensitivity = sensitivity
        self._side = side
        self._real_world_calibration = real_world_calibration
        self._cutoff_recovery = cutoff_recovery
        self._smooth_time = smooth_time
        self._dev: hid.device | None = None
        self._thread: threading.Thread | None = None

        # Calibration offsets (dps)
        self._offset_h = 0.0
        self._offset_v = 0.0

        # Sub-pixel accumulator (pixels, float)
        self._accum_x = 0.0
        self._accum_y = 0.0

        # Moving average buffers: list of (timestamp, h_dps, v_dps)
        self._smooth_buf: collections.deque[tuple[float, float, float]] = collections.deque()

        self._last_time: float | None = None

    @property
    def sensitivity(self) -> float:
        return self._sensitivity

    @sensitivity.setter
    def sensitivity(self, value: float) -> None:
        self._sensitivity = value

    @staticmethod
    def _to_bytes(data) -> bytes:
        if isinstance(data, list):
            return bytes(data)
        return data

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True  # Already running

        self._gyro_stop.clear()

        pid = _PID_R if self._side == "R" else _PID_L
        devices = hid.enumerate(_VID, pid)
        if not devices:
            logger.warning("Gyro: no Joy-Con %s found", self._side)
            return False

        self._dev = hid.device()
        try:
            self._dev.open_path(devices[0]["path"])
        except OSError as e:
            logger.error("Gyro: cannot open Joy-Con %s: %s", self._side, e)
            self._dev = None
            return False

        logger.info("Gyro: opened Joy-Con %s", self._side)

        for _ in range(20):
            try:
                self._dev.read(64, timeout_ms=0)
            except OSError:
                break

        try:
            self._calibrate()
        except Exception as e:
            logger.warning("Gyro: calibration failed: %s", e)

        self._last_time = time.monotonic()

        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("Gyro mouse started (side=%s, sens=%.1f)", self._side, self._sensitivity)
        return True

    def join(self, timeout: float = 1.0) -> None:
        self._gyro_stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        if self._dev:
            try:
                self._dev.close()
            except OSError:
                pass
            self._dev = None

    def _parse_gyro(self, data: bytes, sample_offset: int) -> tuple[float, float]:
        """Parse gyro → (horizontal_dps, vertical_dps).

        Calibrated axis mapping for right Joy-Con (tested):
          gyro_roll  → horizontal (negated)
          gyro_yaw   → vertical   (negated)
        """
        offset = sample_offset + 6
        gyro_roll = struct.unpack_from("<h", data, offset)[0] * _GYRO_SENSITIVITY
        gyro_yaw = struct.unpack_from("<h", data, offset + 2)[0] * _GYRO_SENSITIVITY
        return gyro_roll, -gyro_yaw

    def _calibrate(self) -> None:
        logger.info("Gyro: calibrating (%d samples)...", _CAL_SAMPLES)
        h_list: list[float] = []
        v_list: list[float] = []
        warmup = _CAL_WARMUP

        for _ in range((_CAL_SAMPLES + warmup) * 3):
            data = self._dev.read(64, timeout_ms=100)
            if not data or len(data) < 49:
                continue
            data = self._to_bytes(data)
            if data[0] != 0x30:
                continue

            if warmup > 0:
                warmup -= 1
                continue

            h, v = self._parse_gyro(data, _IMU_SAMPLE_OFFSETS[2])
            h_list.append(h)
            v_list.append(v)
            if len(h_list) >= _CAL_SAMPLES:
                break

        if len(h_list) < 20:
            logger.warning("Gyro: only %d calibration samples", len(h_list))
            return

        h_list.sort()
        v_list.sort()
        mid = len(h_list) // 2
        self._offset_h = h_list[mid]
        self._offset_v = v_list[mid]
        logger.info("Gyro: calibrated (h=%.2f, v=%.2f dps)", self._offset_h, self._offset_v)

    def _soft_deadzone(self, value: float) -> float:
        """Soft deadzone: linearly scale toward zero below cutoff threshold.

        Below cutoff_recovery dps, the output ramps linearly from 0 to value.
        Above cutoff_recovery, output equals input.
        This avoids the hard edge of a normal deadzone.
        """
        mag = abs(value)
        if mag < self._cutoff_recovery:
            return value * (mag / self._cutoff_recovery)
        return value

    def _smooth(self, now: float, h: float, v: float) -> tuple[float, float]:
        """Moving average over the last _SMOOTH_TIME seconds."""
        # Add current sample
        self._smooth_buf.append((now, h, v))

        # Remove old entries outside the window
        cutoff = now - self._smooth_time
        while self._smooth_buf and self._smooth_buf[0][0] < cutoff:
            self._smooth_buf.popleft()

        # Average
        n = len(self._smooth_buf)
        if n == 0:
            return h, v

        sum_h = sum(s[1] for s in self._smooth_buf)
        sum_v = sum(s[2] for s in self._smooth_buf)
        return sum_h / n, sum_v / n

    def _read_loop(self) -> None:
        logger.debug("Gyro: read loop started")

        while not self._stop_event.is_set() and not self._gyro_stop.is_set():
            try:
                data = self._dev.read(64, timeout_ms=10)
            except OSError:
                logger.warning("Gyro: HID read error, stopping")
                break

            if not data or len(data) < 49:
                continue
            data = self._to_bytes(data)
            if data[0] != 0x30:
                continue

            now = time.monotonic()
            dt = now - self._last_time if self._last_time else 0.01
            self._last_time = now

            # --- 1. Parse gyro ---
            h_dps, v_dps = self._parse_gyro(data, _IMU_SAMPLE_OFFSETS[2])

            # --- 2. Subtract calibration offset ---
            h_dps -= self._offset_h
            v_dps -= self._offset_v

            # --- 3. Soft deadzone ---
            h_dps = self._soft_deadzone(h_dps)
            v_dps = self._soft_deadzone(v_dps)

            # --- 4. Moving average smoothing ---
            h_dps, v_dps = self._smooth(now, h_dps, v_dps)

            # --- 5. Sensitivity: dps → degrees of mouse movement ---
            delta_deg_h = h_dps * self._sensitivity * dt
            delta_deg_v = v_dps * self._sensitivity * dt

            # --- 6. Degrees → pixels ---
            dx = delta_deg_h * self._real_world_calibration
            dy = delta_deg_v * self._real_world_calibration

            # --- 7. Sub-pixel accumulation ---
            self._accum_x += dx
            self._accum_y += dy

            px = int(self._accum_x)
            py = int(self._accum_y)

            if px != 0 or py != 0:
                self._accum_x -= px
                self._accum_y -= py
                mouse_output.move(px, py)

        logger.debug("Gyro: read loop ended")
