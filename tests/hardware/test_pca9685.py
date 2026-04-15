"""Hardware test — PCA9685 servo range sweep and calibration.

Smoothly sweeps pan and tilt servos through their full range,
degree by degree, so you can visually verify movement and find
mechanical limits.

Usage:
    uv run python tests/hardware/test_pca9685.py                  # full sweep
    uv run python tests/hardware/test_pca9685.py --pan-only       # pan only
    uv run python tests/hardware/test_pca9685.py --tilt-only      # tilt only
    uv run python tests/hardware/test_pca9685.py --step 5         # 5° steps
    uv run python tests/hardware/test_pca9685.py --calibrate      # interactive calibration
    uv run python tests/hardware/test_pca9685.py --calibrate pan  # calibrate pan only
    uv run python tests/hardware/test_pca9685.py --calibrate tilt # calibrate tilt only
    uv run pytest tests/hardware/test_pca9685.py -v -s            # pytest mode
"""

import argparse
import sys
import termios
import time
import tty

from smbus2 import SMBus

import config

# ---------------------------------------------------------------------------
# PCA9685 register map
# ---------------------------------------------------------------------------

_MODE1 = 0x00
_PRESCALE = 0xFE
_LED0_ON_L = 0x06

I2C_BUS = 1


# ---------------------------------------------------------------------------
# PCA9685 low-level helpers
# ---------------------------------------------------------------------------


def _prescale_value(freq_hz: int) -> int:
    """Calculate PCA9685 prescale for a given frequency."""
    return round(25_000_000 / (4096 * freq_hz)) - 1


def _init_pca9685(bus: SMBus) -> None:
    """Reset PCA9685 and set PWM frequency."""
    addr = config.PCA9685_I2C_ADDRESS
    bus.write_byte_data(addr, _MODE1, 0x10)  # sleep
    time.sleep(0.005)
    prescale = _prescale_value(config.SERVO_PWM_FREQ)
    bus.write_byte_data(addr, _PRESCALE, prescale)
    bus.write_byte_data(addr, _MODE1, 0x20)  # wake + auto-increment
    time.sleep(0.005)


def _set_pwm(bus: SMBus, channel: int, on: int, off: int, retries: int = 5) -> None:
    """Set ON/OFF tick values for a PCA9685 channel, with retry on I/O error."""
    addr = config.PCA9685_I2C_ADDRESS
    reg = _LED0_ON_L + 4 * channel
    for attempt in range(retries):
        try:
            bus.write_byte_data(addr, reg, on & 0xFF)
            bus.write_byte_data(addr, reg + 1, (on >> 8) & 0xFF)
            bus.write_byte_data(addr, reg + 2, off & 0xFF)
            bus.write_byte_data(addr, reg + 3, (off >> 8) & 0xFF)
            return
        except OSError:
            if attempt == retries - 1:
                print(
                    f"\n  [WARN] I2C error on ch {channel} after {retries} retries — skipping"
                )
                return
            # Exponential backoff: 10ms, 20ms, 40ms, 80ms
            time.sleep(0.01 * (2**attempt))


def _angle_to_ticks(angle: int) -> int:
    """Convert angle (0-180) to PCA9685 OFF ticks.

    SG90: 0.5ms (0°) → 2.5ms (180°) at 50Hz.
    """
    min_ticks = 102  # 0.5ms
    max_ticks = 512  # 2.5ms
    return min_ticks + int((angle / 180.0) * (max_ticks - min_ticks))


def _set_servo_angle(bus: SMBus, channel: int, angle: int) -> None:
    """Set a servo channel to the given angle."""
    _set_pwm(bus, channel, 0, _angle_to_ticks(angle))


def _kill_channel(bus: SMBus, channel: int) -> None:
    """Turn off PWM on a single channel (full-off bit) — servo holds mechanically."""
    addr = config.PCA9685_I2C_ADDRESS
    reg = _LED0_ON_L + 4 * channel
    for _ in range(3):
        try:
            bus.write_byte_data(addr, reg, 0)
            bus.write_byte_data(addr, reg + 1, 0)
            bus.write_byte_data(addr, reg + 2, 0)
            bus.write_byte_data(addr, reg + 3, 0x10)  # bit 4 = full off
            return
        except OSError:
            time.sleep(0.01)


def _move_and_kill(bus: SMBus, channel: int, angle: int) -> None:
    """Send PWM pulse, wait for servo to settle, then kill signal."""
    _set_servo_angle(bus, channel, angle)
    time.sleep(0.3)
    _kill_channel(bus, channel)


def _stop_all(bus: SMBus) -> None:
    """Turn off all PWM outputs (sleep mode), retry-safe."""
    for _ in range(3):
        try:
            bus.write_byte_data(config.PCA9685_I2C_ADDRESS, _MODE1, 0x10)
            return
        except OSError:
            time.sleep(0.05)


# ---------------------------------------------------------------------------
# Sweep logic
# ---------------------------------------------------------------------------


def _sweep(
    bus: SMBus,
    channel: int,
    label: str,
    angle_min: int,
    angle_center: int,
    angle_max: int,
    step: int = 1,
    delay: float = 0.03,
) -> None:
    """Sweep a servo: center → min → max → center. Kills PWM when done."""
    print(f"\n{'='*50}")
    print(f"  {label} servo  (ch {channel})")
    print(f"  Range: {angle_min}° → {angle_max}°  Center: {angle_center}°")
    print(f"  Step: {step}°   Delay: {delay:.3f}s")
    print(f"{'='*50}")

    _set_servo_angle(bus, channel, angle_center)
    print(f"  [{label}] → center {angle_center}°")
    time.sleep(0.5)

    for start, end in [
        (angle_center, angle_min),
        (angle_min, angle_max),
        (angle_max, angle_center),
    ]:
        direction = step if start < end else -step
        print(f"\n  Sweeping {start}° → {end}° ...")
        for angle in range(start, end + direction, direction):
            _set_servo_angle(bus, channel, angle)
            print(f"\r  {label} = {angle:>3}°", end="", flush=True)
            time.sleep(delay)
        print()

    # Kill PWM after full sweep — servo holds mechanically
    _kill_channel(bus, channel)
    print(f"  [{label}] done — parked at {angle_center}° (PWM off)")


def sweep_pan(bus: SMBus, step: int = 1, delay: float = 0.02) -> None:
    _sweep(
        bus,
        config.SERVO_PAN_CHANNEL,
        "PAN",
        config.PAN_MIN,
        config.PAN_CENTER,
        config.PAN_MAX,
        step=step,
        delay=delay,
    )


def sweep_tilt(bus: SMBus, step: int = 5) -> None:
    """Tilt sweep — continuous PWM, 5° steps, kill only at end."""
    _sweep(
        bus,
        config.SERVO_TILT_CHANNEL,
        "TILT",
        config.TILT_MIN,
        config.TILT_CENTER,
        config.TILT_MAX,
        step=step,
        delay=0.10,
    )


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------


class TestPCA9685Detection:
    """Verify PCA9685 is reachable on I2C bus."""

    def test_i2c_device_detected(self) -> None:
        with SMBus(I2C_BUS) as bus:
            mode1 = bus.read_byte_data(config.PCA9685_I2C_ADDRESS, _MODE1)
            print(f"\n  PCA9685 MODE1 = {hex(mode1)}")
            assert isinstance(mode1, int)

    def test_prescale_50hz(self) -> None:
        with SMBus(I2C_BUS) as bus:
            _init_pca9685(bus)
            prescale = bus.read_byte_data(config.PCA9685_I2C_ADDRESS, _PRESCALE)
            expected = _prescale_value(config.SERVO_PWM_FREQ)
            print(f"\n  Prescale: {prescale} (expected {expected})")
            assert prescale == expected


class TestPanSweep:
    """Full range sweep of pan servo."""

    def test_pan_sweep(self) -> None:
        with SMBus(I2C_BUS) as bus:
            _init_pca9685(bus)
            sweep_pan(bus, step=5, delay=0.03)
            _stop_all(bus)


class TestTiltSweep:
    """Full range sweep of tilt servo."""

    def test_tilt_sweep(self) -> None:
        with SMBus(I2C_BUS) as bus:
            _init_pca9685(bus)
            sweep_tilt(bus, step=5)
            _stop_all(bus)


class TestCombinedSweep:
    """Sweep both servos sequentially."""

    def test_pan_then_tilt(self) -> None:
        with SMBus(I2C_BUS) as bus:
            _init_pca9685(bus)
            sweep_pan(bus, step=5, delay=0.03)
            sweep_tilt(bus, step=5)
            _stop_all(bus)


# ---------------------------------------------------------------------------
# Interactive calibration
# ---------------------------------------------------------------------------


def _getch() -> str:
    """Read a single keypress (raw terminal mode)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _calibrate(
    bus: SMBus,
    channel: int,
    label: str,
    angle_min: int,
    angle_center: int,
    angle_max: int,
) -> int:
    """Interactive calibration: nudge servo with keys, return chosen angle."""
    angle = angle_center

    print(f"\n{'='*50}")
    print(f"  {label} calibration  (ch {channel})")
    print(f"  Config center: {angle_center}°  Range: {angle_min}°–{angle_max}°")
    print(f"{'='*50}")
    print(f"  a / d  : -1° / +1°")
    print(f"  A / D  : -5° / +5°")
    print(f"  c      : jump to config center ({angle_center}°)")
    print(f"  q      : accept and move on")
    print()

    _set_servo_angle(bus, channel, angle)
    print(f"  {label} = {angle:>3}°", end="", flush=True)

    while True:
        key = _getch()

        if key == "q":
            break
        elif key == "a":
            angle = max(angle_min, angle - 1)
        elif key == "d":
            angle = min(angle_max, angle + 1)
        elif key == "A":
            angle = max(angle_min, angle - 5)
        elif key == "D":
            angle = min(angle_max, angle + 5)
        elif key == "c":
            angle = angle_center
        else:
            continue

        _set_servo_angle(bus, channel, angle)
        print(f"\r  {label} = {angle:>3}°   ", end="", flush=True)

    print(f"\n  Accepted: {angle}°")
    if angle != angle_center:
        print(f"  >>> Update config/__init__.py:")
        name = "PAN_CENTER" if label == "PAN" else "TILT_CENTER"
        print(f"      {name}: Final[int] = {angle}  # was {angle_center}")
    return angle


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PCA9685 servo range sweep test")
    parser.add_argument("--pan-only", action="store_true", help="Sweep pan servo only")
    parser.add_argument(
        "--tilt-only", action="store_true", help="Sweep tilt servo only"
    )
    parser.add_argument(
        "--step", type=int, default=1, help="Degrees per step (default: 1)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.03,
        help="Seconds between steps (default: 0.03)",
    )
    parser.add_argument(
        "--calibrate",
        nargs="?",
        const="both",
        choices=["pan", "tilt", "both"],
        help="Interactive center calibration (pan, tilt, or both)",
    )
    args = parser.parse_args()

    with SMBus(I2C_BUS) as bus:
        # Retry I2C init — breadboard connections can be flaky
        for attempt in range(10):
            try:
                mode1 = bus.read_byte_data(config.PCA9685_I2C_ADDRESS, _MODE1)
                print(
                    f"[OK] PCA9685 at {hex(config.PCA9685_I2C_ADDRESS)}, MODE1={hex(mode1)}"
                )
                break
            except OSError:
                if attempt == 9:
                    print(
                        "[FAIL] PCA9685 not responding after 10 retries. Check wiring."
                    )
                    sys.exit(1)
                print(f"  I2C retry {attempt + 1}/10 ...")
                time.sleep(0.5)

        _init_pca9685(bus)
        prescale = bus.read_byte_data(config.PCA9685_I2C_ADDRESS, _PRESCALE)
        print(f"[OK] Prescale={prescale} ({config.SERVO_PWM_FREQ}Hz)")

        try:
            if args.calibrate:
                # Interactive calibration mode
                if args.calibrate in ("pan", "both"):
                    _calibrate(
                        bus,
                        config.SERVO_PAN_CHANNEL,
                        "PAN",
                        config.PAN_MIN,
                        config.PAN_CENTER,
                        config.PAN_MAX,
                    )
                if args.calibrate in ("tilt", "both"):
                    _calibrate(
                        bus,
                        config.SERVO_TILT_CHANNEL,
                        "TILT",
                        config.TILT_MIN,
                        config.TILT_CENTER,
                        config.TILT_MAX,
                    )
            else:
                # Sweep mode
                do_pan = not args.tilt_only
                do_tilt = not args.pan_only
                print("\n=== PCA9685 Servo Range Sweep ===")
                if do_pan:
                    sweep_pan(bus, step=args.step, delay=args.delay)
                if do_tilt:
                    sweep_tilt(bus, step=max(args.step, 5))
        except KeyboardInterrupt:
            print("\n\n  Interrupted — stopping servos...")
        finally:
            _kill_channel(bus, config.SERVO_PAN_CHANNEL)
            _kill_channel(bus, config.SERVO_TILT_CHANNEL)
            print("\n[OK] PWM killed — servos silent.")
