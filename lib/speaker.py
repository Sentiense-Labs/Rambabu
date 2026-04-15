#!/usr/bin/env python3
"""
Speaker class for AI RC Car.
Manages Sony SRS-XB13 Bluetooth speaker: connection, WAV playback, and TTS.
"""

import subprocess
import threading
import queue
from pathlib import Path

import pyttsx3

import config
from utils.logger import log_info, log_error, log_warning


class Speaker:
    """Bluetooth speaker with WAV playback and TTS via pyttsx3.

    Connects to Sony SRS-XB13, sets it as the default PulseAudio sink,
    and provides both blocking and async (non-blocking) playback methods.
    """

    def __init__(self) -> None:
        self._engine: pyttsx3.Engine | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._speech_queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()

        self._rate = config.SPEAKER_RATE
        self._volume = config.SPEAKER_VOLUME

        self._use_bluetooth = config.SPEAKER_OUTPUT == "bluetooth"
        self._bt_mac: str = config.BT_SPEAKER_MAC
        self._bt_name: str = config.BT_SPEAKER_NAME

        if self._use_bluetooth:
            self._discover_bt_speaker()
            self._ensure_connected()
        self._init_engine()
        self.start()

    # ------------------------------------------------------------------
    # Bluetooth discovery
    # ------------------------------------------------------------------

    def _discover_bt_speaker(self) -> None:
        """Auto-detect the connected BT audio device.

        Tries `bluetoothctl devices Connected` first (fast path).
        Falls back to scanning all paired devices for an AudioSink UUID.
        If nothing is found, keeps the config defaults (BT_SPEAKER_MAC/NAME).
        """
        mac, name = self._find_connected_bt_device()
        if mac is None:
            mac, name = self._find_paired_audio_device()

        if mac is not None:
            self._bt_mac = mac
            self._bt_name = name
            log_info(f"Auto-discovered BT speaker: {name} ({mac})")
        else:
            log_warning(
                f"No BT audio device found — falling back to config: "
                f"{config.BT_SPEAKER_NAME} ({config.BT_SPEAKER_MAC})"
            )

    def _find_connected_bt_device(self) -> tuple[str | None, str]:
        """Return (mac, name) of the first currently-connected BT device."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices", "Connected"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                parts = line.strip().split(" ", 2)
                if len(parts) >= 3 and parts[0] == "Device":
                    return parts[1], parts[2]
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None, ""

    def _find_paired_audio_device(self) -> tuple[str | None, str]:
        """Return (mac, name) of the first paired device with an AudioSink UUID."""
        try:
            result = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                parts = line.strip().split(" ", 2)
                if len(parts) < 3 or parts[0] != "Device":
                    continue
                mac, name = parts[1], parts[2]
                try:
                    info = subprocess.run(
                        ["bluetoothctl", "info", mac],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if "0000110b" in info.stdout.lower():
                        return mac, name
                except (subprocess.TimeoutExpired, OSError):
                    continue
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None, ""

    # ------------------------------------------------------------------
    # Bluetooth connection
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Connect to the BT speaker if not already connected."""
        if self.is_connected():
            log_info(f"Speaker {self._bt_name} already connected")
            self._set_default_sink()
            return

        result = self.connect()
        if result["status"] != "ok":
            log_warning("Speaker not available — audio will use default sink")

    def is_connected(self) -> bool:
        """Check if the Bluetooth speaker is currently connected."""
        if not self._use_bluetooth:
            return False
        try:
            output = subprocess.run(
                ["bluetoothctl", "info", self._bt_mac],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "Connected: yes" in output.stdout
        except (subprocess.TimeoutExpired, OSError) as exc:
            log_error(f"Bluetooth check failed: {exc}")
            return False

    def connect(self) -> dict:
        """Connect to the Bluetooth speaker and set as default sink."""
        if not self._use_bluetooth:
            return {
                "status": "ok",
                "action": "connect",
                "message": "Bluetooth disabled — using hardware speaker",
            }
        try:
            result = subprocess.run(
                ["bluetoothctl", "connect", self._bt_mac],
                capture_output=True,
                text=True,
                timeout=config.BT_CONNECT_TIMEOUT,
            )

            if result.returncode != 0 or "Failed" in result.stdout:
                log_error(f"BT connect failed: {result.stdout.strip()}")
                return {
                    "status": "error",
                    "error_code": "BT_CONNECT_FAILED",
                    "message": f"Could not connect to {self._bt_name}",
                }

            self._set_default_sink()
            log_info(f"Connected to {self._bt_name}")
            return {"status": "ok", "action": "connect", "speaker": self._bt_name}

        except subprocess.TimeoutExpired:
            log_error("BT connect timed out")
            return {
                "status": "error",
                "error_code": "BT_CONNECT_FAILED",
                "message": "Connection timed out",
            }
        except OSError as exc:
            log_error(f"BT connect error: {exc}")
            return {
                "status": "error",
                "error_code": "BT_CONNECT_FAILED",
                "message": str(exc),
            }

    def reconnect(self) -> dict:
        """Disconnect then reconnect to the speaker."""
        if not self._use_bluetooth:
            return {
                "status": "ok",
                "action": "reconnect",
                "message": "Bluetooth disabled — using hardware speaker",
            }
        try:
            subprocess.run(
                ["bluetoothctl", "disconnect", self._bt_mac],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass  # Best-effort disconnect before reconnect

        return self.connect()

    def _set_default_sink(self) -> None:
        """Set the Bluetooth speaker as the default PulseAudio sink.

        Fast path: if a bluez sink is already the default, return
        immediately (common case when already connected).

        Slow path: poll for the bluez sink to appear (up to
        BT_SINK_WAIT seconds) in 100ms ticks, then set it as default.
        Replaces an older blind `time.sleep(BT_SINK_WAIT)` that paid
        the full wait on every init.
        """
        import time

        # Fast path — bluez already the default sink.
        try:
            current = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if "bluez" in current.stdout.lower():
                log_info(f"Default sink already bluez: {current.stdout.strip()}")
                return
        except (subprocess.TimeoutExpired, OSError):
            pass  # Fall through to slow path

        # Slow path — poll for the sink up to BT_SINK_WAIT seconds.
        deadline = time.time() + config.BT_SINK_WAIT
        bt_sink: str | None = None
        while time.time() < deadline:
            try:
                sinks_output = subprocess.run(
                    ["pactl", "list", "sinks", "short"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in sinks_output.stdout.splitlines():
                    if "bluez" in line.lower():
                        bt_sink = line.split()[1]
                        break
                if bt_sink is not None:
                    break
            except (subprocess.TimeoutExpired, OSError):
                pass
            time.sleep(0.1)

        if bt_sink is None:
            log_warning("No Bluetooth sink found in PulseAudio")
            return

        try:
            subprocess.run(
                ["pactl", "set-default-sink", bt_sink],
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                ["pactl", "suspend-sink", bt_sink, "0"],
                capture_output=True,
                timeout=5,
            )
            log_info(f"Default sink set to {bt_sink}")
        except (subprocess.TimeoutExpired, OSError) as exc:
            log_error(f"Failed to set default sink: {exc}")

    # ------------------------------------------------------------------
    # TTS engine
    # ------------------------------------------------------------------

    def _init_engine(self) -> None:
        """Initialize pyttsx3 engine."""
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            self._engine.setProperty("volume", self._volume)
        except Exception as exc:
            log_error(f"TTS engine init failed: {exc}")
            self._engine = None

    def _speech_loop(self) -> None:
        """Background thread that processes the speech queue."""
        while self._running:
            try:
                text = self._speech_queue.get(timeout=0.1)
                if text is None:
                    continue

                if self._engine:
                    self._engine.say(text)
                    self._engine.runAndWait()

                self._speech_queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                log_error(f"Speech error: {exc}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> dict:
        """Start background speech thread."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._speech_loop, daemon=True)
            self._thread.start()
        return {"status": "ok", "action": "start"}

    def stop(self) -> dict:
        """Stop background speech thread and drain queue."""
        self._running = False

        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
            except queue.Empty:
                break

        if self._thread:
            self._thread.join(timeout=1.0)

        return {"status": "ok", "action": "stop"}

    # ------------------------------------------------------------------
    # TTS — non-blocking (queued)
    # ------------------------------------------------------------------

    def speak(self, text: str) -> dict:
        """Queue text for speech (non-blocking)."""
        if text and self._running:
            log_info(f"Speech: '{text}'")
            self._speech_queue.put(text)
            return {"status": "ok", "action": "speak", "text": text}
        return {"status": "ok", "action": "speak", "text": "", "queued": False}

    def greet(self) -> dict:
        """Speak greeting message."""
        result = self.speak("AI RC Car is online and ready")
        log_info("Speech: Boot greeting")
        return result

    def announce(self, label: str, confidence: float) -> dict:
        """Announce detection if confidence exceeds threshold."""
        if confidence > config.ANNOUNCE_CONFIDENCE_THRESHOLD:
            self.speak(f"I see a {label}")
            log_info(f"Speech: Detected {label} ({confidence:.0%})")
            return {"status": "ok", "action": "announce", "label": label}
        return {"status": "ok", "action": "announce", "skipped": True}

    def say_distance(self, cm: float) -> dict:
        """Speak distance in centimeters if within threshold."""
        distance_cm = int(cm)
        if distance_cm < config.SAY_DISTANCE_THRESHOLD:
            self.speak(f"Obstacle detected at {distance_cm} centimeters")
            return {
                "status": "ok",
                "action": "say_distance",
                "distance_cm": distance_cm,
            }
        return {"status": "ok", "action": "say_distance", "skipped": True}

    # ------------------------------------------------------------------
    # WAV playback
    # ------------------------------------------------------------------

    def play_wav(self, file_path: str) -> dict:
        """Play a WAV file through the speaker (blocking)."""
        path = Path(file_path)
        if not path.exists():
            log_error(f"WAV file not found: {file_path}")
            return {
                "status": "error",
                "error_code": "FILE_NOT_FOUND",
                "message": f"WAV file not found: {file_path}",
            }

        try:
            subprocess.run(
                ["aplay", "-D", "default", str(path)],
                capture_output=True,
                timeout=60,
            )
            log_info(f"Played WAV: {path.name}")
            return {"status": "ok", "action": "play_wav", "file": path.name}
        except subprocess.TimeoutExpired:
            log_error(f"WAV playback timed out: {path.name}")
            return {
                "status": "error",
                "error_code": "PLAYBACK_TIMEOUT",
                "message": f"Playback timed out: {path.name}",
            }
        except OSError as exc:
            log_error(f"WAV playback error: {exc}")
            return {
                "status": "error",
                "error_code": "PLAYBACK_ERROR",
                "message": str(exc),
            }

    def play_wav_async(self, file_path: str) -> dict:
        """Play a WAV file in a background thread (non-blocking)."""
        thread = threading.Thread(target=self.play_wav, args=(file_path,), daemon=True)
        thread.start()
        return {
            "status": "ok",
            "action": "play_wav_async",
            "file": Path(file_path).name,
        }

    # ------------------------------------------------------------------
    # MP3 playback
    # ------------------------------------------------------------------

    def play_mp3(self, file_path: str) -> dict:
        """Play an MP3 file through the speaker (blocking)."""
        path = Path(file_path)
        if not path.exists():
            log_error(f"MP3 file not found: {file_path}")
            return {
                "status": "error",
                "error_code": "FILE_NOT_FOUND",
                "message": f"MP3 file not found: {file_path}",
            }

        try:
            subprocess.run(
                ["mpg123", "-q", str(path)],
                capture_output=True,
                timeout=60,
            )
            log_info(f"Played MP3: {path.name}")
            return {"status": "ok", "action": "play_mp3", "file": path.name}
        except subprocess.TimeoutExpired:
            log_error(f"MP3 playback timed out: {path.name}")
            return {
                "status": "error",
                "error_code": "PLAYBACK_TIMEOUT",
                "message": f"Playback timed out: {path.name}",
            }
        except OSError as exc:
            log_error(f"MP3 playback error: {exc}")
            return {
                "status": "error",
                "error_code": "PLAYBACK_ERROR",
                "message": str(exc),
            }

    def play_mp3_async(self, file_path: str) -> dict:
        """Play an MP3 file in a background thread (non-blocking)."""
        thread = threading.Thread(target=self.play_mp3, args=(file_path,), daemon=True)
        thread.start()
        return {
            "status": "ok",
            "action": "play_mp3_async",
            "file": Path(file_path).name,
        }

    # ------------------------------------------------------------------
    # MP3 playback — raw bytes (in-memory, no disk)
    # ------------------------------------------------------------------

    def play_mp3_bytes(self, mp3_data: bytes) -> dict:
        """Play mp3 bytes through the speaker via mpg123 stdin (blocking).

        Pipes `mp3_data` directly into `mpg123 -` without writing to
        disk. Use this when the mp3 is produced in-memory (e.g. from a
        TTS API) and there is no need to persist it.
        """
        if not mp3_data:
            return {
                "status": "error",
                "error_code": "EMPTY_AUDIO",
                "message": "No mp3 data provided",
            }

        try:
            subprocess.run(
                ["mpg123", "-q", "-"],
                input=mp3_data,
                capture_output=True,
                timeout=60,
            )
            log_info(f"Played MP3 bytes: {len(mp3_data)} bytes")
            return {"status": "ok", "action": "play_mp3_bytes", "bytes": len(mp3_data)}
        except subprocess.TimeoutExpired:
            log_error("MP3 bytes playback timed out")
            return {
                "status": "error",
                "error_code": "PLAYBACK_TIMEOUT",
                "message": "Playback timed out",
            }
        except OSError as exc:
            log_error(f"MP3 bytes playback error: {exc}")
            return {
                "status": "error",
                "error_code": "PLAYBACK_ERROR",
                "message": str(exc),
            }

    def play_mp3_bytes_async(self, mp3_data: bytes) -> dict:
        """Play mp3 bytes in a background thread (non-blocking)."""
        if not mp3_data:
            return {
                "status": "error",
                "error_code": "EMPTY_AUDIO",
                "message": "No mp3 data provided",
            }
        thread = threading.Thread(
            target=self.play_mp3_bytes, args=(mp3_data,), daemon=True
        )
        thread.start()
        return {
            "status": "ok",
            "action": "play_mp3_bytes_async",
            "bytes": len(mp3_data),
        }

    # ------------------------------------------------------------------
    # TTS — async variants
    # ------------------------------------------------------------------

    def speak_sync(self, text: str) -> dict:
        """Speak text synchronously (blocks until done)."""
        if not text:
            return {"status": "ok", "action": "speak_sync", "text": ""}

        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            engine.setProperty("volume", self._volume)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            log_info(f"Speech (sync): '{text}'")
            return {"status": "ok", "action": "speak_sync", "text": text}
        except Exception as exc:
            log_error(f"Sync speech error: {exc}")
            return {
                "status": "error",
                "error_code": "SPEECH_ERROR",
                "message": str(exc),
            }

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def set_rate(self, rate: int) -> dict:
        """Set speech rate (words per minute)."""
        self._rate = rate
        if self._engine:
            self._engine.setProperty("rate", rate)
        return {"status": "ok", "rate": rate}

    def set_volume(self, volume: float) -> dict:
        """Set speech volume (0.0 to 1.0)."""
        self._volume = max(0.0, min(volume, 1.0))
        if self._engine:
            self._engine.setProperty("volume", self._volume)
        return {"status": "ok", "volume": self._volume}

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Clean shutdown of speech thread and TTS engine."""
        self.stop()
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
