"""Unit tests for rear obstacle guard on POST /motor/back and sensor endpoints."""
import sys
from unittest.mock import MagicMock

sys.modules["RPi"] = MagicMock()
sys.modules["RPi.GPIO"] = MagicMock()

import pytest
from server.app import create_app


@pytest.fixture
def client():
    motor = MagicMock()
    ultrasonic = MagicMock()
    ultrasonic.get_distance.return_value = 120.0
    ultrasonic.is_obstacle_confirmed.return_value = False
    ultrasonic.get_zone.return_value = "safe"
    rear_ultrasonic = MagicMock()
    rear_ultrasonic.get_distance.return_value = 60.0
    rear_ultrasonic.is_obstacle_confirmed.return_value = False
    pan_tilt = MagicMock()
    pan_tilt.get_angles.return_value = {"pan": 90, "tilt": 90}
    speaker = MagicMock()

    app = create_app(
        motor=motor,
        camera=None,
        ultrasonic=ultrasonic,
        rear_ultrasonic=rear_ultrasonic,
        pan_tilt=pan_tilt,
        speaker=speaker,
        mode_manager=None,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, motor, ultrasonic, rear_ultrasonic


def test_back_blocked_by_rear_obstacle(client):
    test_client, motor, _, _ = client
    motor.back.return_value = {
        "status": "error",
        "error_code": "REAR_OBSTACLE_DETECTED",
        "message": "Rear obstacle detected — cannot move backward",
    }
    resp = test_client.post("/motor/back", json={"speed": 70})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["error_code"] == "REAR_OBSTACLE_DETECTED"


def test_back_succeeds_when_clear(client):
    test_client, motor, _, _ = client
    motor.back.return_value = {"status": "ok", "direction": "backward", "speed": 70}
    resp = test_client.post("/motor/back", json={"speed": 70})
    assert resp.status_code == 200


def test_sensor_distance_includes_rear(client):
    test_client, _, ultrasonic, rear_ultrasonic = client
    ultrasonic.get_distance.return_value = 120.0
    ultrasonic.is_obstacle_confirmed.return_value = False
    rear_ultrasonic.get_distance.return_value = 25.0
    rear_ultrasonic.is_obstacle_confirmed.return_value = True
    resp = test_client.get("/sensor/distance")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "front" in data
    assert "rear" in data
    assert data["rear"]["distance_cm"] == 25.0
    assert data["rear"]["obstacle_confirmed"] is True


def test_status_includes_rear_sensor(client):
    test_client, _, _, rear_ultrasonic = client
    rear_ultrasonic.get_distance.return_value = 40.0
    rear_ultrasonic.is_obstacle_confirmed.return_value = False
    resp = test_client.get("/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rear_sensor" in data
    assert data["rear_sensor"]["distance_cm"] == 40.0
