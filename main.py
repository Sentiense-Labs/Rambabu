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
from server.app import create_app
from server.mqtt.client import MqttClient
from server.mqtt.command_handler import CommandHandler
from lib.bluetooth_server import BluetoothServer
import config

# Global references for cleanup
motor = None
pan_tilt = None
ultrasonic = None
speaker = None
flask_app = None
flask_thread = None
obstacle_monitor_thread = None
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
    last_alert_time = 0.0
    while True:
        try:
            if ultrasonic and motor and motor.is_moving_forward:
                distance = ultrasonic.get_distance()
                if distance <= config.OBSTACLE_DETECTION_DISTANCE:
                    log_info(
                        f"Obstacle monitor: STOP at {distance:.1f}cm "
                        f"(<= {config.OBSTACLE_DETECTION_DISTANCE}cm)"
                    )
                    motor.latch_obstacle()
                    motor.stop()

                    now = time.time()
                    if speaker and (now - last_alert_time) >= config.OBSTACLE_ALERT_COOLDOWN:
                        speaker.play_mp3_async(config.OBSTACLE_ALERT_AUDIO)
                        last_alert_time = now
        except Exception as e:
            log_error(f"Obstacle monitor error: {e}")

        time.sleep(config.ULTRASONIC_POLL_INTERVAL)  # 20 Hz


def cleanup():
    """Clean up all hardware resources in reverse order"""
    log_info("=== Starting Shutdown Sequence ===")

    global motor, pan_tilt, ultrasonic, speaker, flask_thread, mqtt_client, ble_server

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

    # Stop ultrasonic sensor
    if ultrasonic:
        log_info("Stopping ultrasonic sensor...")
        ultrasonic.stop()

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

    # Cleanup GPIO
    GPIO.cleanup()
    log_info("Shutdown complete")


def run_flask_server():
    """Run Flask server in daemon thread"""
    global flask_app
    try:
        flask_app.run(
            host=config.FLASK_HOST,
            port=config.FLASK_PORT,
            debug=False,
            use_reloader=False,
        )
    except Exception as e:
        log_error(f"Flask server error: {e}")


def main():
    """Main entry point"""
    global motor, pan_tilt, ultrasonic, speaker, flask_app, flask_thread, obstacle_monitor_thread, mqtt_client, ble_server

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
            check_fn=lambda: ultrasonic.get_distance() <= config.OBSTACLE_DETECTION_DISTANCE,
            clear_fn=lambda: ultrasonic.get_distance() > config.OBSTACLE_CLEAR_DISTANCE,
        )
        log_info(
            f"Motor obstacle check wired (stop: {config.OBSTACLE_DETECTION_DISTANCE}cm, "
            f"clear: {config.OBSTACLE_CLEAR_DISTANCE}cm)"
        )

        # 3b. Initialize speaker
        log_info("Initializing speaker...")
        speaker = Speaker()
        log_info(f"Speaker initialized (output: {config.SPEAKER_OUTPUT})")

        log_info("Initializing pan-tilt servos...")
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()
        log_info("Pan-tilt initialized at center (90°/90°)")

        pan_tilt.pan_to(config.PAN_CENTER)
        pan_tilt.tilt_to(config.TILT_CENTER)

        # 4. Create Flask app (pass ultrasonic so routes can expose distance)
        log_info("Creating Flask application...")
        flask_app = create_app(
            motor=motor,
            camera=None,
            ultrasonic=ultrasonic,
            pan_tilt=pan_tilt,
            speaker=speaker,
            mode_manager=None,
        )

        # 5. Start obstacle monitor daemon thread
        obstacle_monitor_thread = threading.Thread(target=obstacle_monitor, daemon=True)
        obstacle_monitor_thread.start()
        log_info(
            f"Obstacle monitor started (stop threshold: {config.OBSTACLE_DETECTION_DISTANCE}cm)"
        )

        # 6. Start Flask server in daemon thread
        flask_thread = threading.Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        log_info(f"Web server started on {config.FLASK_HOST}:{config.FLASK_PORT}")

        # 7. Connect MQTT to AWS IoT Core
        log_info("Connecting to AWS IoT Core...")
        mqtt_client = MqttClient()
        command_handler = CommandHandler(
            motor=motor, pan_tilt=pan_tilt, speaker=speaker
        )
        mqtt_client.set_command_callback(command_handler.handle)
        mqtt_result = mqtt_client.connect()
        if mqtt_result["status"] == "ok":
            log_info(f"MQTT connected — subscribing to {config.MQTT_COMMANDS_TOPIC}")
        else:
            log_error(f"MQTT connection failed: {mqtt_result}")

        # 8. Start BLE GATT server
        log_info("Starting BLE server...")
        ble_server = BluetoothServer(motor=motor, pan_tilt=pan_tilt, speaker=speaker)
        ble_result = ble_server.start()
        if ble_result["status"] == "ok":
            log_info("BLE server started — phone can now connect to 'RC-Car'")
        else:
            log_error(f"BLE server failed: {ble_result}")

        # 9. Keep main thread alive
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
