"""Unit tests for PanTilt servo controller — GPIO is mocked, no hardware required."""

from unittest.mock import MagicMock

import pytest

from tests.conftest import _mock_gpio

import config
from lib.pan_tilt import PanTilt


@pytest.fixture
def pt():
    """Create a PanTilt with mocked GPIO."""
    _mock_gpio.reset_mock()
    pwm_pan = MagicMock()
    pwm_tilt = MagicMock()
    _mock_gpio.PWM.side_effect = [pwm_pan, pwm_tilt]

    servo = PanTilt()
    servo.pan_pwm = pwm_pan
    servo.tilt_pwm = pwm_tilt
    return servo


class TestPanTiltInit:
    def test_initial_angles_from_config(self, pt):
        assert pt.pan_angle == config.PAN_CENTER
        assert pt.tilt_angle == config.TILT_CENTER

    def test_get_angles_returns_dict(self, pt):
        angles = pt.get_angles()
        assert angles == {"pan": config.PAN_CENTER, "tilt": config.TILT_CENTER}


class TestPanTo:
    def test_returns_structured_dict(self, pt):
        result = pt.pan_to(100)
        assert result["status"] == "ok"
        assert "pan" in result

    def test_clamps_below_min(self, pt):
        result = pt.pan_to(0)
        assert result["pan"] == config.PAN_MIN
        assert result["clamped"] is True

    def test_clamps_above_max(self, pt):
        result = pt.pan_to(180)
        assert result["pan"] == config.PAN_MAX
        assert result["clamped"] is True

    def test_no_movement_when_same_angle(self, pt):
        pt.pan_angle = 100
        result = pt.pan_to(100)
        assert result["pan"] == 100
        # PWM should not have been called for move
        assert result["clamped"] is False


class TestTiltTo:
    def test_returns_structured_dict(self, pt):
        result = pt.tilt_to(80)
        assert result["status"] == "ok"
        assert "tilt" in result

    def test_clamps_below_min(self, pt):
        result = pt.tilt_to(0)
        assert result["tilt"] == config.TILT_MIN
        assert result["clamped"] is True

    def test_clamps_above_max(self, pt):
        result = pt.tilt_to(180)
        assert result["tilt"] == config.TILT_MAX
        assert result["clamped"] is True


class TestRelativeMoves:
    def test_pan_left(self, pt):
        pt.pan_angle = 90
        result = pt.pan_left(10)
        assert result["pan"] == 80

    def test_pan_right(self, pt):
        pt.pan_angle = 90
        result = pt.pan_right(10)
        assert result["pan"] == 100

    def test_tilt_up(self, pt):
        pt.tilt_angle = 90
        result = pt.tilt_up(10)
        assert result["tilt"] == 100

    def test_tilt_down(self, pt):
        pt.tilt_angle = 90
        result = pt.tilt_down(10)
        assert result["tilt"] == 80


class TestCenter:
    def test_center_returns_dict(self, pt):
        pt.pan_angle = 120
        pt.tilt_angle = 70
        result = pt.center()
        assert result["status"] == "ok"
        assert result["pan"] == config.PAN_CENTER
        assert result["tilt"] == config.TILT_CENTER


class TestAngleToDuty:
    def test_zero_degrees(self, pt):
        assert pt._angle_to_duty(0) == pytest.approx(2.5)

    def test_90_degrees(self, pt):
        assert pt._angle_to_duty(90) == pytest.approx(7.5)

    def test_180_degrees(self, pt):
        assert pt._angle_to_duty(180) == pytest.approx(12.5)
