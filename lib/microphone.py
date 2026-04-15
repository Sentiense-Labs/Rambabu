#!/usr/bin/env python3
"""
Microphone class for AI RC Car
Two-stage pipeline: OpenWakeWord detection → Whisper STT transcription

Captures at 16kHz natively — both OWW and Whisper require 16kHz, so no
resampling is needed. Each OWW frame is exactly 1280 samples (80ms).
"""

import io
import threading
import wave
from typing import Optional

import numpy as np
import pyaudio
from faster_whisper import WhisperModel
from openwakeword.model import Model as WakeWordModel

import config
from utils.logger import log_info, log_error


class Microphone:
    """USB mic with two-stage wake word + command pipeline.

    Stage 1: OpenWakeWord listens continuously at 16kHz, 1280-sample chunks (~10ms/inference)
    Stage 2: On wake word detection, records utterance and transcribes with Whisper

    Public API: start(), stop(), get_command(), clear(), is_listening(), cleanup()
    """

    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None
        self._whisper_model: Optional[WhisperModel] = None
        self._wakeword_model: Optional[WakeWordModel] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest_command: Optional[str] = None

        self._init_whisper()
        self._init_wakeword()
        self.start()

    # ── Model initialization ────────────────────────────────────────────

    def _init_whisper(self) -> None:
        """Load faster-whisper model (offline, CPU, int8)."""
        try:
            log_info(
                f"Microphone: Loading Whisper '{config.WHISPER_MODEL_SIZE}' model "
                f"(device={config.WHISPER_DEVICE}, compute={config.WHISPER_COMPUTE_TYPE})"
            )
            self._whisper_model = WhisperModel(
                config.WHISPER_MODEL_SIZE,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
            log_info("Microphone: Whisper model loaded")
        except Exception as e:
            log_error(f"Microphone: Whisper init failed — {e}")

    def _init_wakeword(self) -> None:
        """Load OpenWakeWord model for always-on detection."""
        try:
            log_info(
                f"Microphone: Loading OpenWakeWord model '{config.WAKEWORD_MODEL}' "
                f"(threshold={config.WAKEWORD_THRESHOLD})"
            )
            self._wakeword_model = WakeWordModel(
                wakeword_models=[config.WAKEWORD_MODEL],
                inference_framework="onnx",
            )
            log_info("Microphone: OpenWakeWord model loaded")
        except Exception as e:
            log_error(f"Microphone: OpenWakeWord init failed — {e}")

    # ── Audio capture helpers ───────────────────────────────────────────

    def _open_stream(self) -> pyaudio.Stream:
        """Open USB mic capture stream at 16kHz.

        frames_per_buffer matches MIC_CHUNK_SIZE (1280) exactly so PortAudio
        blocks for exactly 80ms per read — no spin-loop on ALSA.
        """
        return self._pa.open(
            format=pyaudio.paInt16,
            channels=config.MIC_CHANNELS,
            rate=config.MIC_SAMPLE_RATE,
            input=True,
            input_device_index=config.MIC_DEVICE_INDEX,
            frames_per_buffer=config.MIC_CHUNK_SIZE,
        )

    def _record_utterance(self, stream: pyaudio.Stream) -> Optional[bytes]:
        """Record until silence is detected. Returns raw PCM bytes or None.

        Energy-based VAD: collect frames while above threshold, stop after
        sustained silence. Reads in 1280-sample chunks at 16kHz.
        """
        frames: list[bytes] = []
        silent_chunks = 0
        # 1.5s silence window at 1280 samples/chunk @ 16kHz
        max_silent = int(config.MIC_SAMPLE_RATE / config.MIC_CHUNK_SIZE * 1.5)
        max_frames = int(
            config.MIC_SAMPLE_RATE
            / config.MIC_CHUNK_SIZE
            * config.MIC_PHRASE_TIME_LIMIT
        )
        speaking = False
        energy_threshold = (
            300  # lower for 16kHz (fewer total samples per chunk vs 44100)
        )

        for _ in range(max_frames):
            if not self._running:
                return None
            try:
                data = stream.read(config.MIC_CHUNK_SIZE, exception_on_overflow=False)
            except Exception:
                return None

            energy = np.abs(np.frombuffer(data, dtype=np.int16)).mean()

            if energy > energy_threshold:
                speaking = True
                silent_chunks = 0
                frames.append(data)
            elif speaking:
                silent_chunks += 1
                frames.append(data)
                if silent_chunks >= max_silent:
                    break

        if not frames:
            return None

        return b"".join(frames)

    def _pcm_to_wav_bytes(self, pcm_data: bytes) -> bytes:
        """Wrap raw 16kHz PCM in a WAV container (in-memory) for Whisper."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(config.MIC_CHANNELS)
            wf.setsampwidth(config.MIC_FORMAT_WIDTH)
            wf.setframerate(config.MIC_SAMPLE_RATE)
            wf.writeframes(pcm_data)
        buf.seek(0)
        return buf.read()

    # ── Transcription ───────────────────────────────────────────────────

    def _transcribe(self, pcm_data: bytes) -> Optional[str]:
        """Transcribe raw 16kHz PCM with faster-whisper."""
        if not self._whisper_model:
            return None
        try:
            wav_bytes = self._pcm_to_wav_bytes(pcm_data)
            segments, _ = self._whisper_model.transcribe(
                io.BytesIO(wav_bytes),
                language=config.WHISPER_LANGUAGE,
            )
            text = " ".join(seg.text for seg in segments).strip()
            return text if text else None
        except Exception as e:
            log_error(f"Microphone: Transcription failed — {e}")
            return None

    # ── Two-stage listening loop ────────────────────────────────────────

    def _listening_loop(self) -> None:
        """Background thread: wake word detection → record → transcribe → repeat.

        Captures at 16kHz. Each read() returns exactly 1280 samples (80ms),
        which is exactly one OpenWakeWord inference frame — no resampling needed.
        """
        log_info(
            "Microphone: Listening loop started (two-stage pipeline, 16kHz native)"
        )

        if not self._wakeword_model:
            log_error("Microphone: No wake word model — cannot start listening")
            return

        try:
            stream = self._open_stream()
        except Exception as e:
            log_error(f"Microphone: Cannot open audio stream — {e}")
            return

        try:
            while self._running:
                # ── Stage 1: Wake word detection ──
                try:
                    data = stream.read(
                        config.MIC_CHUNK_SIZE, exception_on_overflow=False
                    )
                except Exception:
                    continue

                chunk = np.frombuffer(data, dtype=np.int16)
                prediction = self._wakeword_model.predict(chunk)

                for model_name, score in prediction.items():
                    if score < config.WAKEWORD_THRESHOLD:
                        continue

                    log_info(
                        f"Microphone: Wake word '{config.WAKE_WORD}' detected "
                        f"(confidence={score:.2f})"
                    )

                    # ── Stage 2: Record + transcribe command ──
                    pcm_data = self._record_utterance(stream)
                    if pcm_data is None:
                        log_info("Microphone: No speech after wake word")
                        break

                    text = self._transcribe(pcm_data)
                    if not text:
                        log_info("Microphone: Transcription empty after wake word")
                        break

                    command = text.strip().lower()
                    log_info(f"Microphone: Command — '{command}'")
                    with self._lock:
                        self._latest_command = command

                    self._wakeword_model.reset()
                    break

        except Exception as e:
            log_error(f"Microphone: Listening loop error — {e}")
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            log_info("Microphone: Listening loop stopped")

    # ── Public API (LLM-callable) ───────────────────────────────────────

    def start(self) -> dict:
        """Start background listening thread."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._listening_loop, daemon=True)
            self._thread.start()
            log_info("Microphone: Started")
        return {"status": "ok", "action": "start"}

    def stop(self) -> dict:
        """Stop background listening thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        log_info("Microphone: Stopped")
        return {"status": "ok", "action": "stop"}

    def get_command(self) -> Optional[str]:
        """Get latest transcribed command (non-blocking, thread-safe).

        Returns None if no new command since last call.
        """
        with self._lock:
            cmd = self._latest_command
            self._latest_command = None
            return cmd

    def is_listening(self) -> bool:
        """True if background listening is active."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def clear(self) -> dict:
        """Clear the latest command buffer."""
        with self._lock:
            self._latest_command = None
        return {"status": "ok", "action": "clear"}

    def cleanup(self) -> None:
        """Clean shutdown — stop thread and release PyAudio."""
        self.stop()
        try:
            self._pa.terminate()
        except Exception:
            pass
