#!/usr/bin/env python3
"""Debug wake word detection — prints live scores to find the right threshold.

Captures at 16kHz natively (same rate OWW needs — no resampling, no aliasing).
Say "hey jarvis" and watch the scores. Press Ctrl+C to stop.
"""

import numpy as np
import pyaudio
from openwakeword.model import Model as WakeWordModel

# ── Config ────────────────────────────────────────────────────────────────
DEVICE_INDEX = 1
SAMPLE_RATE = 16000  # 16kHz native — no resampling needed
CHANNELS = 1
CHUNK_SIZE = 1280  # 80ms at 16kHz = exactly one OWW frame
WAKEWORD_MODEL = "hey_jarvis"


def main() -> None:
    print(f"Loading OpenWakeWord model: {WAKEWORD_MODEL}")
    model = WakeWordModel(wakeword_models=[WAKEWORD_MODEL], inference_framework="onnx")
    print("Model loaded.\n")

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=DEVICE_INDEX,
        frames_per_buffer=CHUNK_SIZE,  # matches read size — no spin-loop on ALSA
    )

    print(f'Say "hey jarvis" and watch the scores.')
    print("Scores > 0.1 will be shown. Press Ctrl+C to stop.\n")

    peak_score = 0.0
    frame_count = 0

    try:
        while True:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            chunk = np.frombuffer(data, dtype=np.int16)
            prediction = model.predict(chunk)
            frame_count += 1

            score = prediction.get("hey_jarvis", 0.0)

            if score > peak_score:
                peak_score = score

            if score > 0.1:
                bar = "#" * int(score * 50)
                print(
                    f"  frame {frame_count:5d} | score: {score:.4f} | peak: {peak_score:.4f} | {bar}"
                )
            elif frame_count % 50 == 0:
                print(
                    f"  frame {frame_count:5d} | score: {score:.4f} | peak: {peak_score:.4f} | (listening...)"
                )

    except KeyboardInterrupt:
        print(f"\n\nPeak score observed: {peak_score:.4f}")
        if peak_score < 0.1:
            print("Very low scores — possible issues:")
            print("  - Mic not picking up audio (check DEVICE_INDEX)")
            print("  - Too far from mic")
        elif peak_score < 0.5:
            print(f"Scores detected but below 0.5 threshold.")
            print(f"Suggested threshold: {max(0.1, peak_score * 0.8):.2f}")
        else:
            print("Scores look good for threshold 0.5")
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
