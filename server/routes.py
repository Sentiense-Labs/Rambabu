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


def set_hardware_dependencies(m, c, u, pt, s, mm):
    """Set hardware module references"""
    global motor, camera, ultrasonic, pan_tilt, speaker, mode_manager
    motor = m
    camera = c
    ultrasonic = u
    pan_tilt = pt
    speaker = s
    mode_manager = mm


@routes.route("/")
def index():
    """Serve the main dashboard page"""
    return render_template("index.html")


@routes.route("/motor/<action>", methods=["POST"])
def motor_action(action):
    """Control motor: front, back, left, right, stop"""
    valid_actions = ["front", "back", "left", "right", "stop"]

    if action not in valid_actions:
        return jsonify({"error": f"Invalid action. Valid: {valid_actions}"}), 400

    if not motor:
        return jsonify({"error": "Motor not initialized"}), 500

    try:
        speed = request.json.get("speed") if request.json else None
        log_info(f"API: POST /motor/{action} - speed: {speed}")

        # ── Obstacle safety guard ─────────────────────────────────────────────
        # Before driving forward, check that no obstacle is within STOP_DISTANCE.
        # This mirrors the logic in tests/test_obstacle_detection.py so that the
        # Flask server enforces the same safety threshold as the standalone test.
        if action == "front" and ultrasonic:
            distance = ultrasonic.get_distance()
            if distance <= config.OBSTACLE_DETECTION_DISTANCE:
                log_info(
                    f"API: /motor/front BLOCKED — obstacle at {distance:.1f}cm "
                    f"(<= {config.OBSTACLE_DETECTION_DISTANCE}cm)"
                )
                return jsonify(
                    {
                        "status": "blocked",
                        "reason": "obstacle_detected",
                        "distance_cm": round(distance, 1),
                        "stop_distance_cm": config.OBSTACLE_DETECTION_DISTANCE,
                        "message": "Object ahead",
                        "detailed_message": (
                            f"Obstacle detected at {distance:.1f}cm. "
                            f"Cannot move forward (threshold: {config.OBSTACLE_DETECTION_DISTANCE}cm)."
                        ),
                    }
                ), 409
        # ─────────────────────────────────────────────────────────────────────

        if action == "front":
            motor.front(speed or 70)
        elif action == "back":
            motor.back(speed or 50)
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
        return jsonify({"error": str(e)}), 500


@routes.route("/steering/<action>", methods=["POST"])
def steering_action(action):
    """Control steering: steer_left_hold, steer_right_hold, steer_center"""
    valid_actions = ["steer_left_hold", "steer_right_hold", "steer_center"]

    if action not in valid_actions:
        return jsonify({"error": f"Invalid action. Valid: {valid_actions}"}), 400

    if not motor:
        return jsonify({"error": "Motor not initialized"}), 500

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
        return jsonify({"error": str(e)}), 500


@routes.route("/servo/pan", methods=["POST"])
def servo_pan():
    """Control pan servo: angle or direction"""
    if not pan_tilt:
        return jsonify({"error": "Pan-tilt not initialized"}), 500

    try:
        data = request.json
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
        return jsonify({"error": str(e)}), 500


@routes.route("/servo/tilt", methods=["POST"])
def servo_tilt():
    """Control tilt servo: angle or direction"""
    if not pan_tilt:
        return jsonify({"error": "Pan-tilt not initialized"}), 500

    try:
        data = request.json
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
        return jsonify({"error": str(e)}), 500


@routes.route("/servo/center", methods=["POST"])
def servo_center():
    """Center both servos to 90°"""
    if not pan_tilt:
        return jsonify({"error": "Pan-tilt not initialized"}), 500

    try:
        log_info("API: POST /servo/center")
        pan_tilt.center()
        angles = pan_tilt.get_angles()
        log_info("API: Servos centered to 90°")
        return jsonify(
            {"status": "success", "pan": angles["pan"], "tilt": angles["tilt"]}
        )

    except Exception as e:
        log_error(f"API: Center servos failed - {str(e)}")
        return jsonify({"error": str(e)}), 500


@routes.route("/mode/<mode>", methods=["POST"])
def set_mode(mode):
    """Set operation mode: AUTONOMOUS, MANUAL, STOPPED"""
    valid_modes = ["AUTONOMOUS", "MANUAL", "STOPPED"]

    if mode not in valid_modes:
        return jsonify({"error": f"Invalid mode. Valid: {valid_modes}"}), 400

    if not mode_manager:
        return jsonify({"error": "Mode manager not initialized"}), 500

    try:
        log_info(f"API: POST /mode/{mode}")
        mode_manager.set_mode(mode)
        log_info(f"API: Mode set to {mode} successfully")
        return jsonify({"status": "success", "mode": mode})

    except Exception as e:
        log_error(f"API: Set mode failed - {str(e)}")
        return jsonify({"error": str(e)}), 500


@routes.route("/speak", methods=["POST"])
def speak():
    """Text-to-speech"""
    if not speaker:
        return jsonify({"error": "Speaker not initialized"}), 500

    try:
        data = request.json
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "No text provided"}), 400

        log_info(f"API: POST /speak - text: '{text}'")
        speaker.speak(text)
        log_info(f"API: Speaking '{text}' completed successfully")
        return jsonify({"status": "success", "text": text})

    except Exception as e:
        log_error(f"API: Speak failed - {str(e)}")
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@routes.route("/sensor/distance")
def get_distance():
    """Get current ultrasonic distance reading and obstacle status"""
    if not ultrasonic:
        return jsonify({"error": "Ultrasonic sensor not initialized"}), 500

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
        return jsonify({"error": str(e)}), 500


@routes.route("/video_feed")
def video_feed():
    """MJPEG video stream"""
    if not camera:
        return "Camera not available", 500

    log_info("API: Video stream started")

    def generate():
        try:
            while True:
                frame = camera.get_frame()
                if frame is not None:
                    # Encode frame as JPEG
                    import cv2

                    ret, jpeg = cv2.imencode(".jpg", frame)
                    if ret:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + jpeg.tobytes()
                            + b"\r\n"
                        )

                # ~15fps
                import time

                time.sleep(0.067)

        except Exception as e:
            log_error(f"API: Video feed error - {str(e)}")
        finally:
            log_info("API: Video stream stopped")

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@routes.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Not found"}), 404


@routes.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({"error": "Internal server error"}), 500
