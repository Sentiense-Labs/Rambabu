"""Unit test: Ultrasonic can be instantiated with custom pin numbers."""
import sys
from unittest.mock import MagicMock, patch

# Stub RPi.GPIO before importing the module under test
sys.modules["RPi"] = MagicMock()
sys.modules["RPi.GPIO"] = MagicMock()

import config
from lib.ultrasonic import Ultrasonic


def test_ultrasonic_uses_custom_pins():
    """Rear sensor instantiation must use supplied pins, not the front-sensor defaults."""
    with patch("lib.ultrasonic.GPIO") as mock_gpio:
        mock_gpio.BCM = 11
        mock_gpio.IN = 0
        mock_gpio.OUT = 1
        sensor = Ultrasonic(trig_pin=23, echo_pin=22)
        # GPIO.setup called for both custom pins
        setup_pins = {call.args[0] for call in mock_gpio.setup.call_args_list}
        assert 23 in setup_pins, "trig_pin 23 must be configured"
        assert 22 in setup_pins, "echo_pin 22 must be configured"
        # Front-sensor default pins must NOT appear
        assert config.ULTRASONIC_TRIG not in setup_pins
        assert config.ULTRASONIC_ECHO not in setup_pins
        sensor.stop()


def test_ultrasonic_default_pins_unchanged():
    """No-arg instantiation must still use the front-sensor config pins."""
    with patch("lib.ultrasonic.GPIO") as mock_gpio:
        mock_gpio.BCM = 11
        mock_gpio.IN = 0
        mock_gpio.OUT = 1
        sensor = Ultrasonic()
        setup_pins = {call.args[0] for call in mock_gpio.setup.call_args_list}
        assert config.ULTRASONIC_TRIG in setup_pins
        assert config.ULTRASONIC_ECHO in setup_pins
        sensor.stop()


def test_ultrasonic_custom_detection_distance():
    """Custom detection_distance must be stored and used instead of the global default."""
    with patch("lib.ultrasonic.GPIO"):
        sensor = Ultrasonic(
            trig_pin=23,
            echo_pin=22,
            detection_distance=config.REAR_OBSTACLE_DETECTION_DISTANCE,
        )
        assert sensor._detection_distance == config.REAR_OBSTACLE_DETECTION_DISTANCE
        sensor.stop()
