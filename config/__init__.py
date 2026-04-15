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

# Camera Pan-Tilt System - SG90 Servos via PCA9685 I2C PWM Driver
PCA9685_I2C_ADDRESS: Final[int] = 0x40  # Default I2C address
SERVO_PAN_CHANNEL: Final[int] = 1       # PCA9685 channel 1
SERVO_TILT_CHANNEL: Final[int] = 0      # PCA9685 channel 0

# Ultrasonic Sensor - HC-SR04 Obstacle Detection
ULTRASONIC_TRIG: Final[GPIOPin] = 17  # Trigger pin (sends 10us pulse)
ULTRASONIC_ECHO: Final[GPIOPin] = 24  # Echo pin (via voltage divider!)

# ⚠️ CRITICAL: GPIO 24 ECHO must use voltage divider
# HC-SR04 ECHO outputs 5V but Pi GPIO tolerates only 3.3V
# Wiring: ECHO → 1kΩ → GPIO 24 ┬─ 2kΩ → GND

# Rear ultrasonic sensor (HC-SR04) — GPIO BCM numbering
# ⚠️ Echo pin requires voltage divider: 1kΩ → GPIO 22 ┬ 2kΩ → GND
ULTRASONIC_REAR_TRIG: Final[GPIOPin] = 23
ULTRASONIC_REAR_ECHO: Final[GPIOPin] = 22


# ============================================================================
# MOTOR SPEED SETTINGS
# ============================================================================

MIN_SPEED: Final[int] = 30  # Minimum PWM duty cycle (0-100)
MAX_SPEED: Final[int] = 100  # Maximum PWM duty cycle
DEFAULT_SPEED: Final[int] = 70  # Default driving speed

# Steering timing (tuned via hardware test — 100% x 250ms)
STEER_PULSE_DURATION: Final[float] = 0.25   # Seconds to hold steering pulse
STEER_DEAD_TIME: Final[float] = 0.05        # Seconds to wait when cutting power
STEER_SETTLE_TIME: Final[float] = 0.10      # Seconds to settle at center before reversing


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

# Rear obstacle safety thresholds (tighter than front — less stopping room behind)
REAR_OBSTACLE_DETECTION_DISTANCE: Final[int] = 30  # cm — latch and stop
REAR_OBSTACLE_CLEAR_DISTANCE: Final[int] = 45       # cm — hysteresis release


# ============================================================================
# SERVO ANGLE LIMITS (degrees, 0-180)
# ============================================================================

# Pan Servo (left/right)
PAN_MIN: Final[int] = 55  # Leftmost safe angle
PAN_CENTER: Final[int] = 110  # Forward-facing
PAN_MAX: Final[int] = 165  # Rightmost safe angle

# Tilt Servo (up/down)
TILT_MIN: Final[int] = 15  # Looking down (mechanical limit ~10°)
TILT_CENTER: Final[int] = 80  # Level horizon
TILT_MAX: Final[int] = 145  # Looking up (mechanical limit ~150°)

PAN_OFFSET: Final[int] = 0
TILT_OFFSET: Final[int] = 0

# Direction multipliers — flip to -1 if servo is physically mounted in reverse
# +1 = standard (left decreases angle, right increases angle, up increases angle)
# -1 = reversed (flip if movement is opposite to expected)
PAN_DIRECTION: Final[int] = -1   # Reversed — pan servo mounted mirrored
TILT_DIRECTION: Final[int] = -1  # Reversed — tilt servo mounted inverted


# ============================================================================
# PWM FREQUENCIES (Hz)
# ============================================================================

MOTOR_PWM_FREQ: Final[int] = 1000   # L9110S rear motor PWM frequency
SERVO_PWM_FREQ: Final[int] = 50  # SG90 servo standard frequency

# Move and Kill timing
SERVO_MOVE_DELAY: Final[float] = 0.3  # Seconds to wait before killing PWM


# ============================================================================
# CAMERA SETTINGS
# ============================================================================

CAMERA_WIDTH: Final[int] = 1920  # Frame width (pixels)
CAMERA_HEIGHT: Final[int] = 1080  # Frame height (pixels)
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
MQTT_CONTROL_TOPIC: Final[str] = f"mqtt/device/{AWS_IOT_CLIENT_ID}/control"
MQTT_DETECTIONS_TOPIC: Final[str] = "car/detections"
MQTT_ALERTS_TOPIC: Final[str] = "car/alerts"
MQTT_CONTROL_RESULT_TOPIC: Final[str] = "car/control"


# ============================================================================
# FLASK WEB SERVER
# ============================================================================

FLASK_HOST: Final[str] = "0.0.0.0"  # Listen on all interfaces
FLASK_PORT: Final[int] = 5000  # Web dashboard port


# ============================================================================
# SPEAKER SETTINGS
# ============================================================================

# "bluetooth" = BT speaker | "hardware" = wired speaker (not yet set up)
SPEAKER_OUTPUT: Final[str] = "bluetooth"

BT_SPEAKER_MAC: Final[str] = "04:21:44:04:74:62"
BT_SPEAKER_NAME: Final[str] = "SRS-XB12"
BT_CONNECT_TIMEOUT: Final[int] = 10  # Seconds to wait for BT connection
BT_SINK_WAIT: Final[float] = 3.0  # Seconds to wait for PulseAudio sink

# TTS settings
SPEAKER_RATE: Final[int] = 150  # Words per minute
SPEAKER_VOLUME: Final[float] = 0.8  # 0.0 to 1.0
ANNOUNCE_CONFIDENCE_THRESHOLD: Final[float] = 0.8
SAY_DISTANCE_THRESHOLD: Final[int] = 100  # cm

# ElevenLabs TTS — expressive "opinions" speech.
# API key is read from the ELEVENLABS_API_KEY environment variable.
# Audio is returned as raw mp3 bytes and piped to the speaker — never
# written to disk. On failure, callers should fall back to pyttsx3.
ELEVENLABS_API_URL: Final[str] = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_VOICE_ID: Final[str] = "kmSVBPu7loj4ayNinwWM"
ELEVENLABS_MODEL_ID: Final[str] = "eleven_flash_v2_5"  # Cheapest + fastest
ELEVENLABS_TIMEOUT: Final[float] = 15.0  # Seconds for HTTP request
ELEVENLABS_STABILITY: Final[float] = 0.5
ELEVENLABS_SIMILARITY: Final[float] = 0.5
ELEVENLABS_SPEED: Final[float] = 1.14  # Slightly faster than default

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
