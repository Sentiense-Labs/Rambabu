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
PAN_SERVO: Final[GPIOPin] = 12  # Hardware PWM0 (Pin 32)
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

SAFE_DISTANCE: Final[int] = 100  # No action needed
WARNING_DISTANCE: Final[int] = 60  # Advisory only
STOP_DISTANCE: Final[int] = 50  # Zone label threshold

# Obstacle detection — hard stop when object is within this distance
OBSTACLE_DETECTION_DISTANCE: Final[int] = 50  # cm — hard stop
# Obstacle clear — latch releases only when distance exceeds this (hysteresis)
OBSTACLE_CLEAR_DISTANCE: Final[int] = 70  # cm — must be > OBSTACLE_DETECTION_DISTANCE


# ============================================================================
# SERVO ANGLE LIMITS (degrees, 0-180)
# ============================================================================

# Pan Servo (left/right)
PAN_MIN: Final[int] = 30  # Leftmost safe angle
PAN_CENTER: Final[int] = 85  # Forward-facing
PAN_MAX: Final[int] = 140  # Rightmost safe angle

# Tilt Servo (up/down)
TILT_MIN: Final[int] = 35  # Looking down
TILT_CENTER: Final[int] = 70  # Level horizon
TILT_MAX: Final[int] = 105  # Looking up

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

AWS_IOT_ENDPOINT: Final[str] = "a2yprvzun5rs6q-ats.iot.ap-south-1.amazonaws.com"
AWS_IOT_CLIENT_ID: Final[str] = "432870b4-0e36-4c7f-8756-87797aa684af"
AWS_IOT_PORT: Final[int] = 8883
AWS_IOT_CERT_PATH: Final[str] = "certs/device.pem.crt"
AWS_IOT_KEY_PATH: Final[str] = "certs/private.pem.key"
AWS_IOT_ROOT_CA_PATH: Final[str] = "certs/root-CA.crt"
AWS_IOT_KEEPALIVE: Final[int] = 60


# ============================================================================
# MQTT TOPICS
# ============================================================================

MQTT_TELEMETRY_TOPIC: Final[str] = "car/telemetry"
MQTT_COMMANDS_TOPIC: Final[str] = f"mqtt/device/{AWS_IOT_CLIENT_ID}/command"
MQTT_CAMERA_CONTROL_TOPIC: Final[str] = f"mqtt/device/{AWS_IOT_CLIENT_ID}/Cameracontrol"
MQTT_DETECTIONS_TOPIC: Final[str] = "car/detections"
MQTT_ALERTS_TOPIC: Final[str] = "car/alerts"


# ============================================================================
# FLASK WEB SERVER
# ============================================================================

FLASK_HOST: Final[str] = "0.0.0.0"  # Listen on all interfaces
FLASK_PORT: Final[int] = 5000  # Web dashboard port


# ============================================================================
# SPEAKER SETTINGS
# ============================================================================

# "bluetooth" = STONE 300 via BT | "hardware" = wired speaker (not yet set up)
SPEAKER_OUTPUT: Final[str] = "bluetooth"

BT_SPEAKER_MAC: Final[str] = "6E:8F:35:8A:8E:67"
BT_SPEAKER_NAME: Final[str] = "STONE 300"
BT_CONNECT_TIMEOUT: Final[int] = 10  # Seconds to wait for BT connection
BT_SINK_WAIT: Final[float] = 3.0  # Seconds to wait for PulseAudio sink

# TTS settings
SPEAKER_RATE: Final[int] = 150  # Words per minute
SPEAKER_VOLUME: Final[float] = 0.8  # 0.0 to 1.0
ANNOUNCE_CONFIDENCE_THRESHOLD: Final[float] = 0.8
SAY_DISTANCE_THRESHOLD: Final[int] = 100  # cm

# Audio library
AUDIO_DIR: Final[str] = "audio"
OBSTACLE_ALERT_AUDIO: Final[str] = "audio/Jaldi-waha-se-hato.mp3"
OBSTACLE_ALERT_COOLDOWN: Final[float] = 5.0  # Seconds between repeated alerts


# ============================================================================
# MICROPHONE SETTINGS — USB PnP Sound Device
# ============================================================================

MIC_DEVICE_INDEX: Final[int] = 1        # PyAudio index (USB PnP Sound Device, ALSA card 3)
MIC_SAMPLE_RATE: Final[int] = 16000     # 16kHz — native for OWW + Whisper
MIC_CHANNELS: Final[int] = 1            # Mono (L/R tied to GND)
MIC_CHUNK_SIZE: Final[int] = 1280       # 80ms at 16kHz — exactly one OWW frame
MIC_FORMAT_WIDTH: Final[int] = 2        # 16-bit (2 bytes) for pyaudio

# Whisper STT (offline, on-device)
WHISPER_MODEL_SIZE: Final[str] = "tiny"  # tiny | base | small (CPU-friendly)
WHISPER_DEVICE: Final[str] = "cpu"
WHISPER_COMPUTE_TYPE: Final[str] = "int8"
WHISPER_LANGUAGE: Final[str] = "en"

# Wake word detection (OpenWakeWord)
WAKEWORD_MODEL: Final[str] = "hey_jarvis"  # Pre-built model (swap to custom later)
WAKEWORD_THRESHOLD: Final[float] = 0.5     # Confidence threshold (0.0-1.0)
WAKE_WORD: Final[str] = "hey jarvis"       # Display name for logging

# Voice activation
MIC_LISTEN_TIMEOUT: Final[float] = 2.0       # Seconds to wait for speech start
MIC_PHRASE_TIME_LIMIT: Final[float] = 5.0    # Max seconds per utterance


# ============================================================================
# LOGGING
# ============================================================================

LOG_FILE: Final[str] = "logs/runtime.log"
LOG_LEVEL: Final[str] = "INFO"  # DEBUG | INFO | WARNING | ERROR
