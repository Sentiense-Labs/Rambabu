#!/usr/bin/env python3
"""
Microphone class for AI RC Car
Speech-to-text using faster-whisper
"""

import speech_recognition as sr
import threading
import queue
from typing import Optional
from faster_whisper import WhisperModel
from utils.logger import log_info, log_error


class Microphone:
    """Microphone with background listening for speech recognition"""

    def __init__(self):
        """Initialize microphone with background listening thread"""
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.running = False
        self.thread = None
        self.command_queue = queue.Queue()
        self.lock = threading.Lock()
        self.latest_command = None
        self.wake_word = "hey rover"

        # Initialize Whisper model
        self.model = None
        self._init_whisper()

        # Start background thread
        self.start()

    def _init_whisper(self):
        """Initialize faster-whisper model"""
        try:
            # Use tiny model for speed
            self.model = WhisperModel("tiny", device="cpu", compute_type="int8")
        except Exception as e:
            print(f"Whisper initialization error: {e}")
            # Fallback to online recognition

    def _listening_loop(self):
        """Background thread for continuous listening"""
        while self.running:
            try:
                with self.microphone as source:
                    # Adjust for ambient noise
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.1)

                    # Listen for audio
                    audio = self.recognizer.listen(
                        source, timeout=1.0, phrase_time_limit=5.0
                    )

                # Try to transcribe
                if self.model:
                    # Use faster-whisper
                    audio_data = audio.get_raw_data()
                    segments, _ = self.model.transcribe(audio_data, language="en")
                    text = " ".join(segment.text for segment in segments).strip()
                else:
                    # Fallback to online recognition
                    text = self.recognizer.recognize_google(audio).lower()

                if text:
                    # Check for wake word
                    if self.wake_word in text.lower():
                        log_info("Voice: Wake word detected")
                        # Extract command after wake word
                        command = text.lower().replace(self.wake_word, "").strip()
                        if command:
                            log_info(f"Voice: Command received - '{command}'")
                            # Thread-safe update
                            with self.lock:
                                self.latest_command = command
                            self.command_queue.put(command)

            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except Exception as e:
                log_error(f"Voice: Transcription failed - {e}")

    def start(self):
        """Start background listening thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._listening_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop background listening thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def listen(self) -> Optional[str]:
        """Listen for a single command (blocking)"""
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source)
                audio = self.recognizer.listen(
                    source, timeout=5.0, phrase_time_limit=5.0
                )

                if self.model:
                    audio_data = audio.get_raw_data()
                    segments, _ = self.model.transcribe(audio_data, language="en")
                    return " ".join(segment.text for segment in segments).strip()
                else:
                    return self.recognizer.recognize_google(audio)

        except Exception as e:
            print(f"Listen error: {e}")
            return None

    def get_command(self) -> Optional[str]:
        """Get latest transcribed command (thread-safe)"""
        with self.lock:
            return self.latest_command

    def is_saying(self, word: str) -> bool:
        """Check if latest command contains specific word"""
        command = self.get_command()
        if command:
            return word.lower() in command.lower()
        return False

    def clear(self) -> None:
        """Clear latest command"""
        with self.lock:
            self.latest_command = None

    def set_wake_word(self, word: str) -> None:
        """Set wake word for activation"""
        self.wake_word = word.lower()

    def cleanup(self) -> None:
        """Clean shutdown"""
        self.stop()
