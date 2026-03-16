"""Unit tests for MotorController — GPIO is mocked, no hardware required."""

from unittest.mock import MagicMock

import pytest

# Ensure GPIO mock is loaded
from tests.conftest import _mock_gpio

import config
from lib.motor import MotorController


@pytest.fixture
def motor():
    """Create a MotorController with mocked GPIO."""
    _mock_gpio.reset_mock()
    # PWM mock instances
    pwm_fwd = MagicMock()
    pwm_bwd = MagicMock()
    _mock_gpio.PWM.side_effect = [pwm_fwd, pwm_bwd]

    mc = MotorController()
    mc.pwm_forward = pwm_fwd
    mc.pwm_backward = pwm_bwd
    return mc


class TestMotorInit:
    def test_initial_direction_is_stopped(self, motor):
        assert motor._direction == "stopped"

    def test_is_moving_forward_false_at_init(self, motor):
        assert motor.is_moving_forward is False


class TestMotorForward:
    def test_returns_structured_dict(self, motor):
        result = motor.front(70)
        assert result["status"] == "ok"
        assert result["direction"] == "forward"
        assert result["speed"] == 70

    def test_sets_direction_forward(self, motor):
        motor.front(60)
        assert motor._direction == "forward"
        assert motor.is_moving_forward is True

    def test_clamps_speed_to_100(self, motor):
        result = motor.front(150)
        assert result["speed"] == 100

    def test_clamps_speed_to_0(self, motor):
        result = motor.front(-10)
        assert result["speed"] == 0

    def test_default_speed_from_config(self, motor):
        result = motor.front()
        assert result["speed"] == config.DEFAULT_SPEED


class TestMotorBack:
    def test_returns_structured_dict(self, motor):
        result = motor.back(50)
        assert result["status"] == "ok"
        assert result["direction"] == "backward"

    def test_sets_direction_backward(self, motor):
        motor.back(50)
        assert motor._direction == "backward"
        assert motor.is_moving_forward is False


class TestMotorStop:
    def test_returns_structured_dict(self, motor):
        motor.front(70)
        result = motor.stop()
        assert result["status"] == "ok"
        assert result["direction"] == "stopped"

    def test_resets_direction(self, motor):
        motor.front(70)
        motor.stop()
        assert motor._direction == "stopped"
        assert motor.is_moving_forward is False


class TestMotorSteering:
    def test_left_returns_dict(self, motor):
        result = motor.left()
        assert result["status"] == "ok"
        assert result["direction"] == "left"

    def test_right_returns_dict(self, motor):
        result = motor.right()
        assert result["status"] == "ok"
        assert result["direction"] == "right"

    def test_steer_left_hold_returns_dict(self, motor):
        result = motor.steer_left_hold()
        assert result["status"] == "ok"
        assert result["direction"] == "left_hold"

    def test_steer_right_hold_returns_dict(self, motor):
        result = motor.steer_right_hold()
        assert result["status"] == "ok"
        assert result["direction"] == "right_hold"

    def test_steer_center_returns_dict(self, motor):
        result = motor.steer_center()
        assert result["status"] == "ok"
        assert result["direction"] == "center"

    def test_left_resets_to_stopped(self, motor):
        motor.left()
        assert motor._direction == "stopped"

    def test_right_resets_to_stopped(self, motor):
        motor.right()
        assert motor._direction == "stopped"
