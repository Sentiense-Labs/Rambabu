#!/usr/bin/env python3
"""
Speaker class for AI RC Car
Text-to-speech using pyttsx3
"""

import pyttsx3
import threading
import queue
from utils.logger import log_info
import config


class Speaker:
    """Text-to-speech with background thread for non-blocking speech"""

    def __init__(self):
        """Initialize speaker with background speech thread"""
        self.engine = None
        self.running = False
        self.thread = None
        self.speech_queue = queue.Queue()
        self.lock = threading.Lock()

        # Speech settings
        self.rate = 150  # Words per minute
        self.volume = 0.8  # 0.0 to 1.0

        # Initialize engine
        self._init_engine()

        # Start background thread
        self.start()

    def _init_engine(self):
        """Initialize pyttsx3 engine"""
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", self.rate)
            self.engine.setProperty("volume", self.volume)
        except Exception as e:
            print(f"Speaker initialization error: {e}")

    def _speech_loop(self):
        """Background thread for processing speech queue"""
        while self.running:
            try:
                # Get text from queue (blocking with timeout)
                text = self.speech_queue.get(timeout=0.1)

                if text is None:
                    continue

                # Speak the text
                if self.engine:
                    self.engine.say(text)
                    self.engine.runAndWait()

                self.speech_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Speech error: {e}")

    def start(self):
        """Start background speech thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._speech_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop background speech thread"""
        self.running = False

        # Clear queue
        while not self.speech_queue.empty():
            try:
                self.speech_queue.get_nowait()
            except queue.Empty:
                break

        if self.thread:
            self.thread.join(timeout=1.0)

    def speak(self, text: str) -> None:
        """Queue text for speech (non-blocking)"""
        if text and self.running:
            log_info(f"Speech: '{text}'")
            self.speech_queue.put(text)

    def greet(self) -> None:
        """Speak greeting message"""
        self.speak("AI RC Car is online and ready")
        log_info("Speech: Boot greeting")

    def announce(self, label: str, confidence: float) -> None:
        """Announce detection with confidence"""
        if confidence > 0.8:
            self.speak(f"I see a {label}")
            log_info(f"Speech: Detected {label} ({confidence:.0%})")

    def beep(self, duration: float = 0.1) -> None:
        """Play a beep sound (simulated)"""
        # pyttsx3 doesn't support beeps directly
        # Could use system beep or audio file
        pass

    def say_distance(self, cm: float) -> None:
        """Speak distance in centimeters"""
        distance_cm = int(cm)
        if distance_cm < 100:
            self.speak(f"Obstacle detected at {distance_cm} centimeters")

    def set_rate(self, rate: int) -> None:
        """Set speech rate (words per minute)"""
        self.rate = rate
        if self.engine:
            self.engine.setProperty("rate", rate)

    def set_volume(self, volume: float) -> None:
        """Set speech volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(volume, 1.0))
        if self.engine:
            self.engine.setProperty("volume", self.volume)

    def cleanup(self):
        """Clean shutdown"""
        self.stop()
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
