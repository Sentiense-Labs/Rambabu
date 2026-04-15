"""Unit tests for rear obstacle latch in MotorController."""
import sys
from unittest.mock import MagicMock, patch

sys.modules["RPi"] = MagicMock()
sys.modules["RPi.GPIO"] = MagicMock()

from lib.motor import MotorController


def _make_motor() -> MotorController:
    with patch("lib.motor.GPIO"):
        return MotorController()


class TestIsMovingBackward:
    def test_false_when_stopped(self):
        m = _make_motor()
        assert m.is_moving_backward is False

    def test_true_after_back_call(self):
        m = _make_motor()
        with patch("lib.motor.GPIO"):
            m.back()
        assert m.is_moving_backward is True

    def test_false_after_stop(self):
        m = _make_motor()
        with patch("lib.motor.GPIO"):
            m.back()
            m.stop()
        assert m.is_moving_backward is False


class TestRearObstacleLatch:
    def test_back_blocked_when_rear_latched(self):
        m = _make_motor()
        m.latch_rear_obstacle()
        result = m.back()
        assert result["status"] == "error"
        assert result["error_code"] == "REAR_OBSTACLE_DETECTED"

    def test_latch_clears_when_moving_forward(self):
        m = _make_motor()
        m.latch_rear_obstacle()
        with patch("lib.motor.GPIO"):
            m.front()
        assert m._rear_obstacle_latched is False

    def test_rear_latch_does_not_block_forward(self):
        m = _make_motor()
        m.latch_rear_obstacle()
        with patch("lib.motor.GPIO"):
            result = m.front()
        assert result["status"] == "ok"

    def test_rear_check_fn_triggers_latch(self):
        m = _make_motor()
        m.set_rear_obstacle_check(lambda: True, lambda: False)
        with patch("lib.motor.GPIO"):
            result = m.back()
        assert result["status"] == "error"
        assert result["error_code"] == "REAR_OBSTACLE_DETECTED"

    def test_rear_check_clear_fn_releases_latch(self):
        m = _make_motor()
        m.latch_rear_obstacle()
        # clear_fn returns False — latch must stay
        m.set_rear_obstacle_check(lambda: True, lambda: False)
        result = m.back()
        assert result["status"] == "error"

    def test_rear_clear_fn_releases_latch(self):
        m = _make_motor()
        m.latch_rear_obstacle()
        # clear_fn returns True — latch must release and back() must succeed
        m.set_rear_obstacle_check(lambda: False, lambda: True)
        with patch("lib.motor.GPIO"):
            result = m.back()
        assert result["status"] == "ok"

    def test_front_clears_front_obstacle_latch_still_works(self):
        """Existing front latch behaviour must be unaffected."""
        m = _make_motor()
        m._obstacle_latched = True
        # Rear latch not set — front() should still clear front latch
        with patch("lib.motor.GPIO"):
            # Wiring clear_fn that says path is clear
            m.set_obstacle_check(lambda: False, lambda: True)
            result = m.front()
        assert result["status"] == "ok"
