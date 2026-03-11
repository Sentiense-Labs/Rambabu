"""Configuration - GPIO pins, constants, credentials."""

from typing import Final

# ============================================================================
# GPIO PIN ASSIGNMENTS (BCM Numbering)
# ============================================================================

type GPIOPin = int

# Motor Control - L9110S Dual Motor Driver
# Channel A: Rear Drive Motor
MOTOR_REAR_FORWARD: Final[GPIOPin] = 25  # L9110S A-IA
MOTOR_REAR_BACKWARD: Final[GPIOPin] = 26  # L9110S A-IB

# Channel B: Front Steering Motor
MOTOR_STEER_LEFT: Final[GPIOPin] = 27  # L9110S B-IA
MOTOR_STEER_RIGHT: Final[GPIOPin] = 14  # L9110S B-IB

# Camera Pan-Tilt System - SG90 Servos
# Using hardware PWM pins (GPIO 12/13) for jitter-free operation on Pi 5
PAN_SERVO: Final[GPIOPin] = 12   # Hardware PWM0 (Pin 32)
TILT_SERVO: Final[GPIOPin] = 13  # Hardware PWM1 (Pin 33)

# Ultrasonic Sensor - HC-SR04 Obstacle Detection
ULTRASONIC_TRIG: Final[GPIOPin] = 17  # Trigger pin (sends 10us pulse)
ULTRASONIC_ECHO: Final[GPIOPin] = 24  # Echo pin (via voltage divider!)

# ⚠️ CRITICAL: GPIO 24 ECHO must use voltage divider
# HC-SR04 ECHO outputs 5V but Pi GPIO tolerates only 3.3V
# Wiring: ECHO → 1kΩ → GPIO 24 ┬─ 2kΩ → GND


# ============================================================================
# MOTOR SPEED SETTINGS
# ============================================================================

MIN_SPEED: Final[int] = 30  # Minimum PWM duty cycle (0-100)
MAX_SPEED: Final[int] = 100  # Maximum PWM duty cycle
DEFAULT_SPEED: Final[int] = 70  # Default driving speed

# Steering timing (prevent motor stall)
STEER_PULSE_DURATION: Final[float] = 0.5  # Max seconds to hold steering


# ============================================================================
# DISTANCE THRESHOLDS (centimeters)
# ============================================================================

SAFE_DISTANCE: Final[int] = 50  # No action needed
WARNING_DISTANCE: Final[int] = 30  # Slow down
STOP_DISTANCE: Final[int] = 20  # Emergency stop

# Obstacle detection threshold - car stops moving forward when an obstacle
# is detected within this distance (matches test_obstacle_detection.py)
OBSTACLE_DETECTION_DISTANCE: Final[int] = 50  # Stop if object within 100cm


# ============================================================================
# SERVO ANGLE LIMITS (degrees, 0-180)
# ============================================================================

# Pan Servo (left/right)
PAN_MIN: Final[int] = 45  # Leftmost safe angle
PAN_CENTER: Final[int] = 90  # Forward-facing
PAN_MAX: Final[int] = 135  # Rightmost safe angle

# Tilt Servo (up/down)
TILT_MIN: Final[int] = 60  # Looking down
TILT_CENTER: Final[int] = 90  # Level horizon
TILT_MAX: Final[int] = 120  # Looking up

PAN_OFFSET: Final[int] = 0
TILT_OFFSET: Final[int] = 0


# ============================================================================
# PWM FREQUENCIES (Hz)
# ============================================================================

MOTOR_PWM_FREQ: Final[int] = 1000  # L9110S motor driver PWM frequency
SERVO_PWM_FREQ: Final[int] = 50  # SG90 servo standard frequency

# Move and Kill timing
SERVO_MOVE_DELAY: Final[float] = 0.3  # Seconds to wait before killing PWM


# ============================================================================
# CAMERA SETTINGS
# ============================================================================

CAMERA_WIDTH: Final[int] = 640  # Frame width (pixels)
CAMERA_HEIGHT: Final[int] = 480  # Frame height (pixels)
CAMERA_FPS: Final[int] = 30  # Frames per second


# ============================================================================
# NAVIGATION LOOP TIMING
# ============================================================================

NAVIGATOR_LOOP_HZ: Final[int] = 10  # Main decision loop frequency
NAVIGATOR_LOOP_INTERVAL: Final[float] = 0.1  # 1/10 = 0.1 seconds

ULTRASONIC_POLL_HZ: Final[int] = 20  # Safety check frequency
ULTRASONIC_POLL_INTERVAL: Final[float] = 0.05  # 1/20 = 0.05 seconds


# ============================================================================
# AWS IoT MQTT SETTINGS
# ============================================================================

# TODO: Fill in your actual AWS IoT values after registration
AWS_IOT_ENDPOINT: Final[str] = "your-endpoint.iot.region.amazonaws.com"
AWS_IOT_CLIENT_ID: Final[str] = "ai-rc-car-001"
AWS_IOT_CERT_PATH: Final[str] = "certs/device.pem.crt"
AWS_IOT_KEY_PATH: Final[str] = "certs/private.pem.key"
AWS_IOT_ROOT_CA_PATH: Final[str] = "certs/root-CA.crt"


# ============================================================================
# MQTT TOPICS
# ============================================================================

MQTT_TELEMETRY_TOPIC: Final[str] = "car/telemetry"
MQTT_COMMANDS_TOPIC: Final[str] = "car/commands"
MQTT_DETECTIONS_TOPIC: Final[str] = "car/detections"
MQTT_ALERTS_TOPIC: Final[str] = "car/alerts"


# ============================================================================
# FLASK WEB SERVER
# ============================================================================

FLASK_HOST: Final[str] = "0.0.0.0"  # Listen on all interfaces
FLASK_PORT: Final[int] = 5000  # Web dashboard port


# ============================================================================
# LOGGING
# ============================================================================

LOG_FILE: Final[str] = "logs/runtime.log"
LOG_LEVEL: Final[str] = "INFO"  # DEBUG | INFO | WARNING | ERROR
