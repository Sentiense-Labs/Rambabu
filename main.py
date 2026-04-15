#!/usr/bin/env python3
"""
Main entry point for AI RC Car
Initializes all hardware and starts autonomous navigation
"""

import signal
import sys
import time
import RPi.GPIO as GPIO
import threading
from utils.logger import log_info, log_error
from lib.motor import MotorController
from lib.pan_tilt import PanTilt
from lib.ultrasonic import Ultrasonic
from lib.speaker import Speaker
from lib.camera import Camera
from server.app import create_app
from server.mqtt.client import MqttClient
from server.mqtt.command_handler import CommandHandler
from agno.agents import GoalDrivenAgent, ExplorerAgent
from agno.types.context import HardwareContext
from brain.sonar_guard import SonarGuard
from brain.movement_manager import MovementManager
from lib.bluetooth_server import BluetoothServer
import config

# Global references for cleanup
motor = None
pan_tilt = None
ultrasonic = None
rear_ultrasonic = None
speaker = None
camera = None
flask_app = None
flask_thread = None
obstacle_monitor_thread = None
rear_monitor_thread = None
mqtt_client = None
ble_server = None

# Commented out for testing
# pan_tilt = None
# ultrasonic = None
# camera = None
# speaker = None
# microphone = None
# mode_manager = None


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) and SIGTERM for graceful shutdown"""
    log_info("Shutting down gracefully...")
    cleanup()
    sys.exit(0)


def obstacle_monitor():
    """
    Background thread: hard-stops the motor when driving forward and an
    obstacle is within OBSTACLE_DETECTION_DISTANCE.
    Runs at 20 Hz. Back, left, right are never interrupted.
    """
    log_info("Obstacle monitor started")
    while True:
        try:
            if ultrasonic and motor and motor.is_moving_forward:
                distance = ultrasonic.get_distance()
                log_info(f"Obstacle monitor: distance={distance:.1f}cm")
                if ultrasonic.is_obstacle_confirmed():
                    log_info(
                        f"Obstacle monitor: STOP at {distance:.1f}cm "
                        f"(confirmed obstacle <= {config.OBSTACLE_DETECTION_DISTANCE}cm)"
                    )
                    motor.latch_obstacle()
                    motor.stop()
        except Exception as e:
            log_error(f"Obstacle monitor error: {e}")

        time.sleep(config.ULTRASONIC_POLL_INTERVAL)  # 20 Hz


def rear_obstacle_monitor() -> None:
    """
    Background thread: hard-stops the motor when reversing and an obstacle
    is within REAR_OBSTACLE_DETECTION_DISTANCE.
    Runs at 20 Hz. Only active when car is moving backward.
    """
    log_info("Rear obstacle monitor started")
    _last_alert: float = 0.0
    while True:
        try:
            if rear_ultrasonic and motor and motor.is_moving_backward:
                dist = rear_ultrasonic.get_distance()
                if rear_ultrasonic.is_obstacle_confirmed():
                    log_info(
                        f"Rear obstacle monitor: STOP at {dist:.1f}cm "
                        f"(confirmed obstacle <= {config.REAR_OBSTACLE_DETECTION_DISTANCE}cm)"
                    )
                    motor.latch_rear_obstacle()
                    motor.stop()
                    now = time.time()
                    if now - _last_alert > config.OBSTACLE_ALERT_COOLDOWN:
                        _last_alert = now
                        try:
                            if speaker:
                                speaker.say("Obstacle behind")
                        except Exception:
                            pass
        except Exception as e:
            log_error(f"Rear obstacle monitor error: {e}")

        time.sleep(config.ULTRASONIC_POLL_INTERVAL)  # 20 Hz


def cleanup():
    """Clean up all hardware resources in reverse order"""
    log_info("=== Starting Shutdown Sequence ===")

    global \
        motor, \
        pan_tilt, \
        ultrasonic, \
        rear_ultrasonic, \
        speaker, \
        camera, \
        flask_thread, \
        mqtt_client, \
        ble_server

    # Stop camera
    if camera:
        log_info("Stopping camera...")
        camera.cleanup()

    # Stop BLE server
    if ble_server:
        log_info("Stopping BLE server...")
        ble_server.cleanup()

    # Stop MQTT first
    if mqtt_client:
        log_info("Disconnecting MQTT...")
        mqtt_client.cleanup()

    # Stop Flask thread
    if flask_thread and flask_thread.is_alive():
        log_info("Stopping web server...")
        # Flask thread is daemon, will exit automatically

    # Stop ultrasonic sensors
    if ultrasonic:
        log_info("Stopping front ultrasonic sensor...")
        ultrasonic.stop()
    if rear_ultrasonic:
        log_info("Stopping rear ultrasonic sensor...")
        rear_ultrasonic.stop()

    # Stop speaker
    if speaker:
        log_info("Stopping speaker...")
        speaker.cleanup()

    # Stop motor controller
    if motor:
        log_info("Stopping motor controller...")
        motor.stop()
        motor.cleanup()

    if pan_tilt:
        log_info("Stopping pan-tilt servos...")
        pan_tilt.cleanup()

    # Cleanup GPIO — wrapped because lgpio PWM.__del__ can race with cleanup
    try:
        GPIO.cleanup()
    except Exception:
        pass
    log_info("Shutdown complete")


def run_flask_server():
    """Run Flask server in daemon thread"""
    global flask_app
    try:
        flask_app.run(
            host=config.FLASK_HOST,
            port=config.FLASK_PORT,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    except Exception as e:
        log_error(f"Flask server error: {e}")


def main():
    """Main entry point"""
    global \
        motor, \
        pan_tilt, \
        ultrasonic, \
        rear_ultrasonic, \
        speaker, \
        camera, \
        flask_app, \
        flask_thread, \
        obstacle_monitor_thread, \
        rear_monitor_thread, \
        mqtt_client, \
        ble_server

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log_info("=== AI RC Car Boot Sequence ===")

    try:
        # 1. Initialize GPIO ONCE
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        log_info("GPIO initialized")

        # 2. Initialize motor controller
        log_info("Initializing motor controller...")
        motor = MotorController()
        log_info("Motor controller initialized")

        # 3. Initialize ultrasonic sensor for obstacle detection
        log_info("Initializing ultrasonic sensor...")
        ultrasonic = Ultrasonic()
        log_info("Waiting for ultrasonic sensor to get first reading...")
        if ultrasonic.wait_for_reading(timeout=2.0):
            log_info(
                f"Ultrasonic sensor ready (distance: {ultrasonic.get_distance():.1f}cm)"
            )
        else:
            log_error("Warning: Ultrasonic sensor not responding, continuing anyway...")
        log_info("Ultrasonic sensor initialized")

        # 3a. Wire obstacle check into motor (with hysteresis for latch release)
        motor.set_obstacle_check(
            check_fn=lambda: ultrasonic.is_obstacle_confirmed(),
            clear_fn=lambda: ultrasonic.get_distance() > config.OBSTACLE_CLEAR_DISTANCE,
        )
        log_info(
            f"Motor obstacle check wired (stop: {config.OBSTACLE_DETECTION_DISTANCE}cm, "
            f"clear: {config.OBSTACLE_CLEAR_DISTANCE}cm)"
        )

        # 3b. Initialize rear ultrasonic sensor
        log_info("Initializing rear ultrasonic sensor...")
        rear_ultrasonic = Ultrasonic(
            trig_pin=config.ULTRASONIC_REAR_TRIG,
            echo_pin=config.ULTRASONIC_REAR_ECHO,
            detection_distance=config.REAR_OBSTACLE_DETECTION_DISTANCE,
        )
        if rear_ultrasonic.wait_for_reading(timeout=2.0):
            log_info(
                f"Rear ultrasonic sensor ready (distance: {rear_ultrasonic.get_distance():.1f}cm)"
            )
        else:
            log_error(
                "Warning: Rear ultrasonic sensor not responding, continuing anyway..."
            )
        log_info(
            f"Rear ultrasonic sensor started (GPIO trig={config.ULTRASONIC_REAR_TRIG}, "
            f"echo={config.ULTRASONIC_REAR_ECHO})"
        )

        # 3c. Wire rear obstacle check into motor
        motor.set_rear_obstacle_check(
            check_fn=rear_ultrasonic.is_obstacle_confirmed,
            clear_fn=lambda: (
                rear_ultrasonic.get_distance() > config.REAR_OBSTACLE_CLEAR_DISTANCE
            ),
        )
        log_info(
            f"Rear obstacle check wired (stop: {config.REAR_OBSTACLE_DETECTION_DISTANCE}cm, "
            f"clear: {config.REAR_OBSTACLE_CLEAR_DISTANCE}cm)"
        )

        # 3d. Initialize speaker (optional)
        try:
            log_info("Initializing speaker...")
            speaker = Speaker()
            log_info(f"Speaker initialized (output: {config.SPEAKER_OUTPUT})")
        except Exception as e:
            log_error(f"Speaker init failed: {e} — continuing without speaker")
            speaker = None

        # 3e. Initialize pan-tilt servos (optional — requires I2C PCA9685)
        try:
            log_info("Initializing pan-tilt servos...")
            pan_tilt = PanTilt()
            pan_tilt.set_as_current_center()
            pan_tilt.pan_to(config.PAN_CENTER)
            pan_tilt.tilt_to(config.TILT_CENTER)
            log_info("Pan-tilt initialized at center")
        except Exception as e:
            log_error(f"Pan-tilt init failed: {e} — continuing without pan-tilt")
            pan_tilt = None

        # 4. Initialize camera (optional)
        try:
            log_info("Initializing camera...")
            camera = Camera()
            cam_result = camera.start()
            if cam_result["status"] == "ok":
                log_info(
                    f"Camera started at {cam_result['resolution'][0]}x{cam_result['resolution'][1]}"
                )
            else:
                log_error(
                    f"Camera failed to start: {cam_result} — continuing without camera"
                )
                camera = None
        except Exception as e:
            log_error(f"Camera init failed: {e} — continuing without camera")
            camera = None

        # 5. Create Flask app
        log_info("Creating Flask application...")
        flask_app = create_app(
            motor=motor,
            camera=camera,
            ultrasonic=ultrasonic,
            rear_ultrasonic=rear_ultrasonic,
            pan_tilt=pan_tilt,
            speaker=speaker,
            mode_manager=None,
        )

        # 6. Start obstacle monitor daemon threads
        obstacle_monitor_thread = threading.Thread(target=obstacle_monitor, daemon=True)
        obstacle_monitor_thread.start()
        log_info(
            f"Front obstacle monitor started (stop threshold: {config.OBSTACLE_DETECTION_DISTANCE}cm)"
        )

        rear_monitor_thread = threading.Thread(
            target=rear_obstacle_monitor, daemon=True, name="rear-obstacle-monitor"
        )
        rear_monitor_thread.start()
        log_info(
            f"Rear obstacle monitor started (stop threshold: {config.REAR_OBSTACLE_DETECTION_DISTANCE}cm)"
        )

        # 7. Start Flask server in daemon thread
        flask_thread = threading.Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        log_info(f"Web server started on {config.FLASK_HOST}:{config.FLASK_PORT}")

        # 8. Connect MQTT to AWS IoT Core (optional)
        try:
            log_info("Connecting to AWS IoT Core...")
            mqtt_client = MqttClient()
            sonar_guard = SonarGuard(ultrasonic=ultrasonic, motor=motor)
            sonar_guard.start()
            movement_manager = MovementManager(
                motor=motor,
                sonar_guard=sonar_guard,
            )
            log_info("SonarGuard + MovementManager initialized")
            hw = HardwareContext(
                motor=motor,
                ultrasonic=ultrasonic,
                pan_tilt=pan_tilt,
                camera=camera,
                speaker=speaker,
                sonar_guard=sonar_guard,
                movement_manager=movement_manager,
            )
            goal_agent = GoalDrivenAgent(
                hw=hw,
                publish_callback=lambda result: mqtt_client.publish(
                    config.MQTT_CONTROL_RESULT_TOPIC, result
                ),
            )
            explorer_agent = ExplorerAgent(
                hw=hw,
                publish_callback=lambda result: mqtt_client.publish(
                    config.MQTT_CONTROL_RESULT_TOPIC, result
                ),
            )
            command_handler = CommandHandler(
                motor=motor,
                pan_tilt=pan_tilt,
                speaker=speaker,
                goal_agent=goal_agent,
                rear_ultrasonic=rear_ultrasonic,
            )
            mqtt_client.set_command_callback(command_handler.handle)
            mqtt_result = mqtt_client.connect()
            if mqtt_result["status"] == "ok":
                log_info(
                    f"MQTT connected — subscribing to {config.MQTT_COMMANDS_TOPIC}"
                )
            else:
                log_error(f"MQTT connection failed: {mqtt_result}")
        except Exception as e:
            log_error(f"MQTT init failed: {e} — continuing without MQTT")
            mqtt_client = None

        # 9. Start BLE GATT server (optional)
        try:
            log_info("Starting BLE server...")
            ble_server = BluetoothServer(
                motor=motor,
                pan_tilt=pan_tilt,
                speaker=speaker,
                control_runner=goal_agent,
            )
            ble_result = ble_server.start()
            if ble_result["status"] == "ok":
                log_info("BLE server started — phone can now connect to 'RC-Car'")
            else:
                log_error(f"BLE server failed: {ble_result}")
        except Exception as e:
            log_error(f"BLE init failed: {e} — continuing without BLE")
            ble_server = None

        # 10. Keep main thread alive
        log_info("System running - press Ctrl+C to stop")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        log_info("Interrupted by user")
    except Exception as e:
        log_error(f"Fatal error: {e}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
