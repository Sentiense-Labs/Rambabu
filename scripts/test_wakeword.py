#!/usr/bin/env python3
"""Test wake word detection with OpenWakeWord + Whisper STT.

Captures at 16kHz natively (same rate OWW and Whisper need — no resampling).
Listens for "hey jarvis" with OpenWakeWord, then records and transcribes the
following command with faster-whisper.

Press Ctrl+C to stop.
"""

import io
import wave
from datetime import datetime

import numpy as np
import pyaudio
from faster_whisper import WhisperModel
from openwakeword.model import Model as WakeWordModel

# ── Config ────────────────────────────────────────────────────────────────
DEVICE_INDEX = 1
SAMPLE_RATE = 16000       # 16kHz — native for OWW + Whisper, no resampling
CHANNELS = 1
CHUNK_SIZE = 1280         # 80ms at 16kHz = exactly one OWW frame
WAKEWORD_MODEL = "hey_jarvis"
WAKEWORD_THRESHOLD = 0.5
ENERGY_THRESHOLD = 300
MAX_SILENCE_SEC = 1.5
MAX_UTTERANCE_SEC = 5.0


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def record_utterance(stream: pyaudio.Stream) -> bytes | None:
    """Record until silence after speech. Returns raw 16kHz PCM bytes or None."""
    frames: list[bytes] = []
    silent_chunks = 0
    max_silent = int(SAMPLE_RATE / CHUNK_SIZE * MAX_SILENCE_SEC)
    max_frames = int(SAMPLE_RATE / CHUNK_SIZE * MAX_UTTERANCE_SEC)
    speaking = False

    for _ in range(max_frames):
        try:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        except Exception:
            return None

        energy = np.abs(np.frombuffer(data, dtype=np.int16)).mean()

        if energy > ENERGY_THRESHOLD:
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


def pcm_to_wav(pcm_data: bytes) -> bytes:
    """Wrap raw 16kHz PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)
    buf.seek(0)
    return buf.read()


def main() -> None:
    print("Loading OpenWakeWord model ...")
    oww_model = WakeWordModel(
        wakeword_models=[WAKEWORD_MODEL],
        inference_framework="onnx",
    )
    print(f"  Wake word model: {WAKEWORD_MODEL} (threshold={WAKEWORD_THRESHOLD})")

    print("Loading Whisper tiny model (CPU, int8) ...")
    whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    print("  Models loaded.\n")

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=DEVICE_INDEX,
        frames_per_buffer=CHUNK_SIZE,   # matches read size — no spin-loop on ALSA
    )

    print(f'Listening for wake word: "hey jarvis"')
    print("Speak into the USB mic. Press Ctrl+C to stop.\n")

    try:
        while True:
            # Stage 1: Wake word detection (80ms per iteration, blocking)
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            chunk = np.frombuffer(data, dtype=np.int16)
            prediction = oww_model.predict(chunk)

            for model_name, score in prediction.items():
                if score < WAKEWORD_THRESHOLD:
                    continue

                print(f"  [{_timestamp()}] WAKE WORD DETECTED (confidence={score:.3f})")

                # Stage 2: Record + transcribe
                pcm_data = record_utterance(stream)
                if pcm_data is None:
                    print(f"  [{_timestamp()}] No speech detected after wake word")
                    break

                wav_bytes = pcm_to_wav(pcm_data)
                segments, _ = whisper_model.transcribe(
                    io.BytesIO(wav_bytes),
                    language="en",
                )
                text = " ".join(seg.text for seg in segments).strip()

                if text:
                    print(f"  [{_timestamp()}] Command: \"{text}\"")
                else:
                    print(f"  [{_timestamp()}] (empty transcription)")

                oww_model.reset()
                break

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
