#!/usr/bin/env python3
"""Verbose wake word + speech recognition test.

Shows real-time feedback:
- Wake word confidence scores (live)
- Audio energy levels during recording (visual bar)
- Whisper transcription result with timing

Press Ctrl+C to stop.
"""

import io
import time
import wave
from datetime import datetime

import numpy as np
import pyaudio
from faster_whisper import WhisperModel
from openwakeword.model import Model as WakeWordModel

# ── Config ────────────────────────────────────────────────────────────────
DEVICE_INDEX = 1
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1280  # 80ms at 16kHz = one OWW frame
WAKEWORD_MODEL = "hey_jarvis"
WAKEWORD_THRESHOLD = 0.5
ENERGY_THRESHOLD = 300
MAX_SILENCE_SEC = 1.5
MAX_UTTERANCE_SEC = 5.0


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _energy_bar(energy: float, width: int = 40) -> str:
    """Visual bar for audio energy level."""
    clamped = min(energy / 2000, 1.0)
    filled = int(clamped * width)
    if energy > ENERGY_THRESHOLD:
        return f"\033[92m{'█' * filled}{'░' * (width - filled)}\033[0m"  # green
    return f"\033[90m{'█' * filled}{'░' * (width - filled)}\033[0m"  # grey


def record_utterance_verbose(stream: pyaudio.Stream) -> bytes | None:
    """Record until silence, showing live energy levels."""
    frames: list[bytes] = []
    silent_chunks = 0
    max_silent = int(SAMPLE_RATE / CHUNK_SIZE * MAX_SILENCE_SEC)
    max_frames = int(SAMPLE_RATE / CHUNK_SIZE * MAX_UTTERANCE_SEC)
    speaking = False
    chunk_count = 0

    print(
        f"  [{_ts()}] 🎙️  Recording... (speak your command, {MAX_UTTERANCE_SEC}s max)"
    )
    print(
        f"  {'':>14} Energy threshold: {ENERGY_THRESHOLD} | Silence timeout: {MAX_SILENCE_SEC}s"
    )
    print()

    for _ in range(max_frames):
        try:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        except Exception:
            return None

        energy = np.abs(np.frombuffer(data, dtype=np.int16)).mean()
        chunk_count += 1

        # Show energy bar every 2 chunks (~160ms) to avoid flooding
        if chunk_count % 2 == 0:
            status = "SPEECH" if energy > ENERGY_THRESHOLD else "silent"
            print(
                f"\r  energy: {energy:6.0f} {_energy_bar(energy)} [{status}]",
                end="",
                flush=True,
            )

        if energy > ENERGY_THRESHOLD:
            speaking = True
            silent_chunks = 0
            frames.append(data)
        elif speaking:
            silent_chunks += 1
            frames.append(data)
            if silent_chunks >= max_silent:
                print(f"\n  [{_ts()}] Silence detected — stopping recording")
                break

    if not frames:
        return None

    duration_ms = len(frames) * CHUNK_SIZE / SAMPLE_RATE * 1000
    print(f"  [{_ts()}] Captured {len(frames)} chunks ({duration_ms:.0f}ms of audio)")
    return b"".join(frames)


def pcm_to_wav(pcm_data: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)
    buf.seek(0)
    return buf.read()


def main() -> None:
    print("=" * 60)
    print("  WAKE WORD + SPEECH RECOGNITION TEST (verbose)")
    print("=" * 60)
    print()

    print("Loading OpenWakeWord model ...")
    oww_model = WakeWordModel(
        wakeword_models=[WAKEWORD_MODEL],
        inference_framework="onnx",
    )
    print(f"  Model: {WAKEWORD_MODEL} | Threshold: {WAKEWORD_THRESHOLD}")

    print("Loading Whisper tiny model (CPU, int8) ...")
    whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    print("  Whisper loaded.")
    print()

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=DEVICE_INDEX,
        frames_per_buffer=CHUNK_SIZE,
    )

    print("-" * 60)
    print(f'  Say "hey jarvis" to activate, then speak a command.')
    print(f"  Press Ctrl+C to stop.")
    print("-" * 60)
    print()

    detection_count = 0
    frame_count = 0

    try:
        while True:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            chunk = np.frombuffer(data, dtype=np.int16)
            prediction = oww_model.predict(chunk)
            frame_count += 1

            score = prediction.get("hey_jarvis", 0.0)

            # Show periodic heartbeat + any notable scores
            if score > 0.1:
                bar = "#" * int(score * 30)
                print(
                    f"\r  [{_ts()}] wake score: {score:.3f} {bar}", end="", flush=True
                )
            elif frame_count % 75 == 0:
                # ~6 second heartbeat
                energy = np.abs(chunk).mean()
                print(
                    f"\r  [{_ts()}] listening... (energy={energy:.0f})",
                    end="",
                    flush=True,
                )

            if score < WAKEWORD_THRESHOLD:
                continue

            # Wake word detected
            detection_count += 1
            print(f"\n\n  {'='*50}")
            print(f"  [{_ts()}] WAKE WORD DETECTED! (confidence={score:.3f})")
            print(f"  {'='*50}")
            print()

            # Record utterance
            pcm_data = record_utterance_verbose(stream)
            if pcm_data is None:
                print(f"  [{_ts()}] No speech detected after wake word\n")
                oww_model.reset()
                continue

            # Transcribe
            print(f"\n  [{_ts()}] Transcribing with Whisper ...")
            t0 = time.monotonic()
            wav_bytes = pcm_to_wav(pcm_data)
            segments, info = whisper_model.transcribe(
                io.BytesIO(wav_bytes),
                language="en",
            )
            segment_list = list(segments)
            elapsed = (time.monotonic() - t0) * 1000

            text = " ".join(seg.text for seg in segment_list).strip()

            print(f"  [{_ts()}] Transcription done in {elapsed:.0f}ms")
            print()

            if segment_list:
                print(f"  ┌─────────────────────────────────────────────")
                print(f"  │ Segments:")
                for i, seg in enumerate(segment_list):
                    print(
                        f'  │   [{i}] ({seg.start:.1f}s-{seg.end:.1f}s) "{seg.text.strip()}"'
                    )
                print(f"  │")
                print(f'  │ Full text: "{text}"')
                print(f"  └─────────────────────────────────────────────")
            else:
                print(f"  (empty transcription — no segments returned)")

            print(f"\n  Detection #{detection_count} complete.")
            print(f"  Resuming wake word listening ...\n")

            oww_model.reset()

    except KeyboardInterrupt:
        print(f"\n\nStopped after {detection_count} detections, {frame_count} frames.")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
