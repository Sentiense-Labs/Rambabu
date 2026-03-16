"""Unit tests for Ultrasonic sensor — GPIO is mocked, no hardware required."""

from unittest.mock import patch
import threading

import pytest

from tests.conftest import _mock_gpio

import config
from lib.ultrasonic import Ultrasonic


@pytest.fixture
def sensor():
    """Create an Ultrasonic sensor with mocked GPIO and no background thread."""
    _mock_gpio.reset_mock()

    with patch.object(Ultrasonic, "start"):
        s = Ultrasonic()
    return s


class TestUltrasonicInit:
    def test_initial_distance_is_safe_default(self, sensor):
        assert sensor.last_distance == 999.0

    def test_gpio_pins_from_config(self, sensor):
        assert sensor.trig_pin == config.ULTRASONIC_TRIG
        assert sensor.echo_pin == config.ULTRASONIC_ECHO


class TestGetDistance:
    def test_returns_last_distance(self, sensor):
        sensor.last_distance = 42.5
        assert sensor.get_distance() == 42.5

    def test_thread_safe(self, sensor):
        sensor.last_distance = 10.0
        distances = []

        def read():
            for _ in range(100):
                distances.append(sensor.get_distance())

        threads = [threading.Thread(target=read) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(d == 10.0 for d in distances)


class TestZones:
    def test_safe_zone(self, sensor):
        sensor.last_distance = config.SAFE_DISTANCE + 10
        assert sensor.get_zone() == "safe"

    def test_warning_zone(self, sensor):
        sensor.last_distance = config.STOP_DISTANCE + 5
        assert sensor.get_zone() == "warning"

    def test_danger_zone(self, sensor):
        sensor.last_distance = config.STOP_DISTANCE - 1
        assert sensor.get_zone() == "danger"


class TestIsClearBlocked:
    def test_is_clear_uses_config_default(self, sensor):
        sensor.last_distance = config.SAFE_DISTANCE + 1
        assert sensor.is_clear() is True

    def test_is_blocked_uses_config_default(self, sensor):
        sensor.last_distance = config.STOP_DISTANCE - 1
        assert sensor.is_blocked() is True

    def test_is_clear_with_custom_threshold(self, sensor):
        sensor.last_distance = 25
        assert sensor.is_clear(threshold=20) is True
        assert sensor.is_clear(threshold=30) is False

    def test_is_blocked_with_custom_threshold(self, sensor):
        sensor.last_distance = 25
        assert sensor.is_blocked(threshold=30) is True
        assert sensor.is_blocked(threshold=20) is False


class TestWaitForReading:
    def test_returns_true_when_valid(self, sensor):
        sensor.last_distance = 50.0
        assert sensor.wait_for_reading(timeout=0.1) is True

    def test_returns_false_on_timeout(self, sensor):
        sensor.last_distance = 999.0
        assert sensor.wait_for_reading(timeout=0.1) is False
