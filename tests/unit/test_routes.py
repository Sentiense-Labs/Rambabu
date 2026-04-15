"""Unit tests for Flask routes — all hardware is mocked."""

from unittest.mock import MagicMock
import json

import pytest

from server.app import create_app


@pytest.fixture
def mock_motor():
    m = MagicMock()
    m.is_moving_forward = False
    m.front.return_value = {"status": "ok", "direction": "forward", "speed": 70}
    m.back.return_value = {"status": "ok", "direction": "backward", "speed": 50}
    m.left.return_value = {"status": "ok", "direction": "left"}
    m.right.return_value = {"status": "ok", "direction": "right"}
    m.stop.return_value = {"status": "ok", "direction": "stopped"}
    m.steer_left_hold.return_value = {"status": "ok", "direction": "left_hold"}
    m.steer_right_hold.return_value = {"status": "ok", "direction": "right_hold"}
    m.steer_center.return_value = {"status": "ok", "direction": "center"}
    return m


@pytest.fixture
def mock_ultrasonic():
    u = MagicMock()
    u.get_distance.return_value = 100.0
    u.get_zone.return_value = "safe"
    u.is_obstacle_confirmed.return_value = False
    return u


@pytest.fixture
def mock_pan_tilt():
    pt = MagicMock()
    pt.get_angles.return_value = {"pan": 90, "tilt": 90}
    return pt


@pytest.fixture
def client(mock_motor, mock_ultrasonic, mock_pan_tilt):
    app = create_app(
        motor=mock_motor,
        camera=None,
        ultrasonic=mock_ultrasonic,
        pan_tilt=mock_pan_tilt,
        speaker=None,
        mode_manager=None,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestMotorRoutes:
    def test_motor_front_success(self, client, mock_motor):
        resp = client.post(
            "/motor/front",
            json={"speed": 70},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        mock_motor.front.assert_called_once()

    def test_motor_stop_success(self, client, mock_motor):
        resp = client.post("/motor/stop", json={})
        assert resp.status_code == 200
        mock_motor.stop.assert_called_once()

    def test_motor_invalid_action(self, client):
        resp = client.post("/motor/fly", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "INVALID_ACTION"

    def test_motor_front_blocked_by_obstacle(self, client, mock_ultrasonic):
        mock_ultrasonic.get_distance.return_value = 10.0
        resp = client.post("/motor/front", json={"speed": 70})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error_code"] == "OBSTACLE_DETECTED"

    def test_motor_back_not_blocked_by_obstacle(self, client, mock_ultrasonic):
        mock_ultrasonic.get_distance.return_value = 10.0
        resp = client.post("/motor/back", json={"speed": 50})
        assert resp.status_code == 200


class TestSteeringRoutes:
    def test_steer_left_hold(self, client, mock_motor):
        resp = client.post("/steering/steer_left_hold", json={})
        assert resp.status_code == 200
        mock_motor.steer_left_hold.assert_called_once()

    def test_invalid_steering(self, client):
        resp = client.post("/steering/spin", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "INVALID_ACTION"


class TestServoRoutes:
    def test_servo_pan_by_angle(self, client, mock_pan_tilt):
        resp = client.post("/servo/pan", json={"angle": 100})
        assert resp.status_code == 200
        mock_pan_tilt.pan_to.assert_called_once_with(100)

    def test_servo_tilt_by_angle(self, client, mock_pan_tilt):
        resp = client.post("/servo/tilt", json={"angle": 80})
        assert resp.status_code == 200
        mock_pan_tilt.tilt_to.assert_called_once_with(80)

    def test_servo_center(self, client, mock_pan_tilt):
        resp = client.post("/servo/center", json={})
        assert resp.status_code == 200
        mock_pan_tilt.center.assert_called_once()

    def test_servo_pan_null_json_returns_400(self, client):
        resp = client.post(
            "/servo/pan",
            data=json.dumps(None),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error_code"] == "INVALID_ACTION"


class TestSensorRoutes:
    def test_get_distance(self, client, mock_ultrasonic):
        resp = client.get("/sensor/distance")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "distance_cm" in data
        assert "zone" in data


class TestStatusRoute:
    def test_get_status(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "distance" in data
        assert "uptime" in data
        assert "timestamp" in data


class TestErrorFormat:
    """Verify all error responses use structured error codes."""

    def test_404_has_error_code(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error_code" in data
        assert "message" in data

    def test_motor_not_initialized(self):
        """When motor is None, error uses structured format."""
        app = create_app(
            motor=None,
            camera=None,
            ultrasonic=None,
            pan_tilt=None,
            speaker=None,
            mode_manager=None,
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            resp = c.post("/motor/front", json={"speed": 70})
            assert resp.status_code == 500
            data = resp.get_json()
            assert data["error_code"] == "MOTOR_STALL"
