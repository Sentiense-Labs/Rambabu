"""Shared test fixtures for unit and hardware tests."""

import sys
from unittest.mock import MagicMock

# Mock RPi.GPIO before any lib/ import can pull it in
_mock_gpio = MagicMock()
_mock_gpio.BCM = 11
_mock_gpio.OUT = 0
_mock_gpio.IN = 1
_mock_gpio.HIGH = 1
_mock_gpio.LOW = 0
sys.modules["RPi"] = MagicMock()
sys.modules["RPi.GPIO"] = _mock_gpio

# Mock picamera2
sys.modules["picamera2"] = MagicMock()

# Mock pyttsx3
sys.modules["pyttsx3"] = MagicMock()

# Mock speech_recognition
sys.modules["speech_recognition"] = MagicMock()

# Mock faster_whisper
sys.modules["faster_whisper"] = MagicMock()

# Mock pyaudio
sys.modules["pyaudio"] = MagicMock()

# Mock cv2
sys.modules["cv2"] = MagicMock()
