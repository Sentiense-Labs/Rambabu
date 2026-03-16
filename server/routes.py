#!/usr/bin/env python3
"""
REST API routes for AI RC Car web dashboard
"""

from flask import Blueprint, request, jsonify, Response, render_template
import time
from utils.logger import log_info, log_error
import config

# Create blueprint
routes = Blueprint("routes", __name__)

# Global references to hardware modules (will be set by app factory)
motor = None
camera = None
ultrasonic = None
pan_tilt = None
speaker = None
mode_manager = None
start_time = time.time()
_last_obstacle_alert_time = 0.0


def set_hardware_dependencies(m, c, u, pt, s, mm):
    """Set hardware module references"""
    global motor, camera, ultrasonic, pan_tilt, speaker, mode_manager
    motor = m
    camera = c
    ultrasonic = u
    pan_tilt = pt
    speaker = s
    mode_manager = mm


def _error_response(error_code: str, message: str, status: int = 500):
    """Return structured error response per engineering guidelines."""
    return jsonify({"error_code": error_code, "message": message}), status


@routes.route("/")
def index():
    """Serve the main dashboard page"""
    return render_template("index.html")


@routes.route("/motor/<action>", methods=["POST"])
def motor_action(action):
    """Control motor: front, back, left, right, stop"""
    valid_actions = ["front", "back", "left", "right", "stop"]

    if action not in valid_actions:
        return _error_response(
            "INVALID_ACTION",
            f"Invalid action. Valid: {valid_actions}",
            400,
        )

    if not motor:
        return _error_response("MOTOR_STALL", "Motor not initialized")

    try:
        data = request.json or {}
        speed = data.get("speed")
        log_info(f"API: POST /motor/{action} - speed: {speed}")

        if action == "front":
            result = motor.front(speed or config.DEFAULT_SPEED)
            if result.get("status") == "error":
                # Motor refused — obstacle detected or latched
                log_info(f"API: /motor/front BLOCKED — {result.get('message')}")

                # Play obstacle alert with cooldown
                global _last_obstacle_alert_time
                now = time.time()
                if speaker and (now - _last_obstacle_alert_time) >= config.OBSTACLE_ALERT_COOLDOWN:
                    speaker.play_mp3_async(config.OBSTACLE_ALERT_AUDIO)
                    _last_obstacle_alert_time = now

                distance = ultrasonic.get_distance() if ultrasonic else 0
                return (
                    jsonify(
                        {
                            "error_code": result.get("error_code", "OBSTACLE_DETECTED"),
                            "message": result.get("message"),
                            "distance_cm": round(distance, 1),
                            "stop_distance_cm": config.OBSTACLE_DETECTION_DISTANCE,
                        }
                    ),
                    409,
                )
        elif action == "back":
            motor.back(speed or config.DEFAULT_SPEED)
        elif action == "left":
            motor.left()
        elif action == "right":
            motor.right()
        elif action == "stop":
            motor.stop()

        log_info(f"API: Motor {action} completed successfully")
        return jsonify({"status": "success", "action": action})

    except Exception as e:
        log_error(f"API: Motor {action} failed - {str(e)}")
        return _error_response("MOTOR_STALL", f"Motor {action} failed: {e}")


@routes.route("/steering/<action>", methods=["POST"])
def steering_action(action):
    """Control steering: steer_left_hold, steer_right_hold, steer_center"""
    valid_actions = ["steer_left_hold", "steer_right_hold", "steer_center"]

    if action not in valid_actions:
        return _error_response(
            "INVALID_ACTION",
            f"Invalid action. Valid: {valid_actions}",
            400,
        )

    if not motor:
        return _error_response("MOTOR_STALL", "Motor not initialized")

    try:
        log_info(f"API: POST /steering/{action}")

        if action == "steer_left_hold":
            motor.steer_left_hold()
        elif action == "steer_right_hold":
            motor.steer_right_hold()
        elif action == "steer_center":
            motor.steer_center()

        log_info(f"API: Steering {action} completed successfully")
        return jsonify({"status": "success", "action": action})

    except Exception as e:
        log_error(f"API: Steering {action} failed - {str(e)}")
        return _error_response("MOTOR_STALL", f"Steering {action} failed: {e}")


@routes.route("/servo/pan", methods=["POST"])
def servo_pan():
    """Control pan servo: angle or direction"""
    if not pan_tilt:
        return _error_response("SERVO_LIMIT", "Pan-tilt not initialized")

    try:
        data = request.json
        if data is None:
            return _error_response("INVALID_ACTION", "Request body required", 400)

        log_info(f"API: POST /servo/pan - params: {data}")

        if "angle" in data:
            pan_tilt.pan_to(data["angle"])
        elif "direction" in data:
            if data["direction"] == "left":
                pan_tilt.pan_left(data.get("degrees", 10))
            elif data["direction"] == "right":
                pan_tilt.pan_right(data.get("degrees", 10))

        angles = pan_tilt.get_angles()
        log_info(f"API: Pan servo moved to {angles['pan']}°")
        return jsonify(
            {"status": "success", "pan": angles["pan"], "tilt": angles["tilt"]}
        )

    except Exception as e:
        log_error(f"API: Pan servo failed - {str(e)}")
        return _error_response("SERVO_LIMIT", f"Pan servo failed: {e}")


@routes.route("/servo/tilt", methods=["POST"])
def servo_tilt():
    """Control tilt servo: angle or direction"""
    if not pan_tilt:
        return _error_response("SERVO_LIMIT", "Pan-tilt not initialized")

    try:
        data = request.json
        if data is None:
            return _error_response("INVALID_ACTION", "Request body required", 400)

        log_info(f"API: POST /servo/tilt - params: {data}")

        if "angle" in data:
            pan_tilt.tilt_to(data["angle"])
        elif "direction" in data:
            if data["direction"] == "up":
                pan_tilt.tilt_up(data.get("degrees", 10))
            elif data["direction"] == "down":
                pan_tilt.tilt_down(data.get("degrees", 10))

        angles = pan_tilt.get_angles()
        log_info(f"API: Tilt servo moved to {angles['tilt']}°")
        return jsonify(
            {"status": "success", "pan": angles["pan"], "tilt": angles["tilt"]}
        )

    except Exception as e:
        log_error(f"API: Tilt servo failed - {str(e)}")
        return _error_response("SERVO_LIMIT", f"Tilt servo failed: {e}")


@routes.route("/servo/center", methods=["POST"])
def servo_center():
    """Center both servos to 90deg"""
    if not pan_tilt:
        return _error_response("SERVO_LIMIT", "Pan-tilt not initialized")

    try:
        log_info("API: POST /servo/center")
        pan_tilt.center()
        angles = pan_tilt.get_angles()
        log_info("API: Servos centered to 90deg")
        return jsonify(
            {"status": "success", "pan": angles["pan"], "tilt": angles["tilt"]}
        )

    except Exception as e:
        log_error(f"API: Center servos failed - {str(e)}")
        return _error_response("SERVO_LIMIT", f"Center servos failed: {e}")


@routes.route("/mode/<mode>", methods=["POST"])
def set_mode(mode):
    """Set operation mode: AUTONOMOUS, MANUAL, STOPPED"""
    valid_modes = ["AUTONOMOUS", "MANUAL", "STOPPED"]

    if mode not in valid_modes:
        return _error_response(
            "INVALID_ACTION",
            f"Invalid mode. Valid: {valid_modes}",
            400,
        )

    if not mode_manager:
        return _error_response("GPIO_FAILURE", "Mode manager not initialized")

    try:
        log_info(f"API: POST /mode/{mode}")
        mode_manager.set_mode(mode)
        log_info(f"API: Mode set to {mode} successfully")
        return jsonify({"status": "success", "mode": mode})

    except Exception as e:
        log_error(f"API: Set mode failed - {str(e)}")
        return _error_response("GPIO_FAILURE", f"Set mode failed: {e}")


@routes.route("/speak", methods=["POST"])
def speak():
    """Text-to-speech"""
    if not speaker:
        return _error_response("GPIO_FAILURE", "Speaker not initialized")

    try:
        data = request.json
        if data is None:
            return _error_response("INVALID_ACTION", "Request body required", 400)

        text = data.get("text", "")

        if not text:
            return _error_response("INVALID_ACTION", "No text provided", 400)

        log_info(f"API: POST /speak - text: '{text}'")
        speaker.speak(text)
        log_info(f"API: Speaking '{text}' completed successfully")
        return jsonify({"status": "success", "text": text})

    except Exception as e:
        log_error(f"API: Speak failed - {str(e)}")
        return _error_response("GPIO_FAILURE", f"Speak failed: {e}")


@routes.route("/status")
def get_status():
    """Get current system status"""
    try:
        status = {
            "mode": mode_manager.get_mode() if mode_manager else "UNKNOWN",
            "distance": ultrasonic.get_distance() if ultrasonic else 0,
            "obstacle_detected": (
                ultrasonic.get_distance() <= config.OBSTACLE_DETECTION_DISTANCE
                if ultrasonic
                else False
            ),
            "servo_angles": (
                pan_tilt.get_angles() if pan_tilt else {"pan": 90, "tilt": 90}
            ),
            "uptime": int(time.time() - start_time),
            "camera_active": camera is not None,
            "timestamp": int(time.time()),
        }
        return jsonify(status)

    except Exception as e:
        log_error(f"API: Get status failed - {str(e)}")
        return _error_response("GPIO_FAILURE", f"Get status failed: {e}")


@routes.route("/sensor/distance")
def get_distance():
    """Get current ultrasonic distance reading and obstacle status"""
    if not ultrasonic:
        return _error_response("SENSOR_TIMEOUT", "Ultrasonic sensor not initialized")

    try:
        distance = ultrasonic.get_distance()
        zone = ultrasonic.get_zone()
        obstacle_detected = distance <= config.OBSTACLE_DETECTION_DISTANCE

        log_info(f"API: GET /sensor/distance - {distance:.1f}cm ({zone})")
        return jsonify(
            {
                "distance_cm": round(distance, 1),
                "zone": zone,
                "obstacle_detected": obstacle_detected,
                "stop_distance_cm": config.OBSTACLE_DETECTION_DISTANCE,
                "warning_distance_cm": config.WARNING_DISTANCE,
                "safe_distance_cm": config.SAFE_DISTANCE,
            }
        )

    except Exception as e:
        log_error(f"API: Get distance failed - {str(e)}")
        return _error_response("SENSOR_TIMEOUT", f"Get distance failed: {e}")


@routes.route("/video_feed")
def video_feed():
    """MJPEG video stream"""
    if not camera:
        return _error_response("CAMERA_ERROR", "Camera not available")

    import cv2

    log_info("API: Video stream started")

    def generate():
        try:
            while True:
                frame = camera.get_frame()
                if frame is not None:
                    ret, jpeg = cv2.imencode(".jpg", frame)
                    if ret:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + jpeg.tobytes()
                            + b"\r\n"
                        )

                # ~15fps
                time.sleep(0.067)

        except Exception as e:
            log_error(f"API: Video feed error - {str(e)}")
        finally:
            log_info("API: Video stream stopped")

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@routes.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error_code": "NOT_FOUND", "message": "Not found"}), 404


@routes.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return (
        jsonify({"error_code": "INTERNAL_ERROR", "message": "Internal server error"}),
        500,
    )
