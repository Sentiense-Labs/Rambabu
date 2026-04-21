#!/usr/bin/env python3
"""
Hardware test for fast monocular depth estimation using MiDaS Small (ONNX).

Downloads midas_v21_small_256.onnx from HuggingFace on first run (~82 MB),
captures live frames from the Pi Camera, runs depth inference on-device, and
saves a colourised depth visualisation.

Run on Pi:
    uv run python tests/hardware/test_depth_estimation.py

Output files (project root):
    depth_map_latest.jpg   — colourised depth (INFERNO: bright/warm = close)
    depth_raw_latest.jpg   — original frame | depth map side by side

Model convention:
    MiDaS outputs RELATIVE depth: HIGHER value → object is CLOSER to camera.
    Zone analysis splits the frame into LEFT / CENTRE / RIGHT thirds and
    classifies each by 95th-percentile depth (NEAR / MEDIUM / FAR).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── Model config ───────────────────────────────────────────────────────────────

MODEL_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "midas_v21_small_256.onnx"
INPUT_SIZE = 256

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Zone thresholds — normalised depth [0–1], higher = closer
_ZONE_NEAR   = 0.65
_ZONE_MEDIUM = 0.35

OUTPUT_DIR            = Path(__file__).parent.parent.parent
DEPTH_COLOUR_PATH     = OUTPUT_DIR / "depth_map_latest.jpg"
DEPTH_SIDE_BY_SIDE_PATH = OUTPUT_DIR / "depth_raw_latest.jpg"

NUM_WARMUP_FRAMES    = 3
NUM_BENCHMARK_FRAMES = 10


# ── Model download ─────────────────────────────────────────────────────────────

_MODEL_URL = (
    "https://github.com/isl-org/MiDaS/releases/download/v3_1/midas_v21_small_256.onnx"
)


def _ensure_model() -> None:
    if MODEL_PATH.exists():
        print(f"Model found: {MODEL_PATH}  ({MODEL_PATH.stat().st_size / 1e6:.1f} MB)")
        return

    import urllib.request

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading MiDaS Small  (~82 MB, one-time) …")

    def _progress(count: int, block_size: int, total: int) -> None:
        if total > 0:
            pct = min(count * block_size / total * 100, 100)
            print(f"\r  {pct:.1f}%", end="", flush=True)

    try:
        # opener that follows GitHub's redirect to the CDN
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
        req = urllib.request.Request(_MODEL_URL, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req) as resp, open(MODEL_PATH, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while chunk := resp.read(65536):
                f.write(chunk)
                downloaded += len(chunk)
                _progress(downloaded, 1, total)
        print(f"\n  Saved → {MODEL_PATH}  ({MODEL_PATH.stat().st_size / 1e6:.1f} MB)")
    except Exception as exc:
        MODEL_PATH.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed: {exc}") from exc


# ── Pre / post processing ──────────────────────────────────────────────────────

def _preprocess(frame_rgb: np.ndarray) -> np.ndarray:
    """RGB H×W×3 uint8 → normalised NCHW float32."""
    resized = cv2.resize(frame_rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)
    norm = (resized.astype(np.float32) / 255.0 - _MEAN) / _STD
    return np.expand_dims(norm.transpose(2, 0, 1), axis=0)  # HWC → NCHW


def _postprocess(raw: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    """Squeeze, resize to target, normalise to uint8 [0–255]."""
    depth = raw.squeeze()
    h, w = target_hw
    depth = cv2.resize(depth, (w, h), interpolation=cv2.INTER_LINEAR)
    d_min, d_max = depth.min(), depth.max()
    if d_max - d_min < 1e-6:
        return np.zeros((h, w), dtype=np.uint8)
    return ((depth - d_min) / (d_max - d_min) * 255).astype(np.uint8)


def _colourize(depth_u8: np.ndarray) -> np.ndarray:
    return cv2.applyColorMap(depth_u8, cv2.COLORMAP_INFERNO)


# ── Zone analysis ──────────────────────────────────────────────────────────────

def _analyse_zones(depth_norm: np.ndarray) -> dict[str, dict]:
    """Split into LEFT / CENTRE / RIGHT, classify each by p95 depth."""
    h, w = depth_norm.shape
    t = w // 3
    zones = {"left": depth_norm[:, :t], "centre": depth_norm[:, t:2*t], "right": depth_norm[:, 2*t:]}
    result = {}
    for name, region in zones.items():
        p95 = float(np.percentile(region, 95))
        label = "NEAR" if p95 >= _ZONE_NEAR else ("MEDIUM" if p95 >= _ZONE_MEDIUM else "FAR")
        result[name] = {"zone": label, "mean": round(float(region.mean()), 3), "p95": round(p95, 3)}
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    _ensure_model()

    print("\nLoading ONNX session …")
    import onnxruntime as ort
    sess = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    inp_name  = sess.get_inputs()[0].name
    out_name  = sess.get_outputs()[0].name
    print(f"  Input  : {inp_name}  {sess.get_inputs()[0].shape}")
    print(f"  Output : {out_name}  {sess.get_outputs()[0].shape}")

    print("\nStarting camera …")
    import RPi.GPIO as GPIO
    from lib.camera import Camera

    GPIO.setmode(GPIO.BCM)
    camera = Camera()
    if camera.start().get("status") != "ok":
        print("Camera failed to start"); GPIO.cleanup(); sys.exit(1)
    print(f"  Resolution : {camera.get_resolution()}")
    print("  Warming up (1.5 s) …")
    time.sleep(1.5)

    print(f"\nWarm-up ({NUM_WARMUP_FRAMES} frames) …")
    for _ in range(NUM_WARMUP_FRAMES):
        frame = camera.get_frame()
        if frame is not None:
            sess.run([out_name], {inp_name: _preprocess(frame)})

    print(f"\nBenchmark ({NUM_BENCHMARK_FRAMES} frames) …")
    latencies: list[float] = []
    last_frame: np.ndarray | None = None
    last_depth_u8: np.ndarray | None = None

    for i in range(NUM_BENCHMARK_FRAMES):
        frame = camera.get_frame()
        if frame is None:
            print(f"  Frame {i+1:2d}: no frame"); continue

        t0 = time.perf_counter()
        raw = sess.run([out_name], {inp_name: _preprocess(frame)})[0]
        ms = (time.perf_counter() - t0) * 1000

        h, w = frame.shape[:2]
        depth_u8   = _postprocess(raw, (h, w))
        depth_norm = depth_u8.astype(np.float32) / 255.0
        zones      = _analyse_zones(depth_norm)

        latencies.append(ms)
        last_frame, last_depth_u8 = frame, depth_u8

        zstr = "  ".join(f"{k.upper():6s}: {v['zone']:6s}(p95={v['p95']:.2f})" for k, v in zones.items())
        print(f"  Frame {i+1:2d}  {ms:6.0f} ms  |  {zstr}")

    if last_frame is not None and last_depth_u8 is not None:
        coloured = _colourize(last_depth_u8)
        cv2.imwrite(str(DEPTH_COLOUR_PATH), coloured)

        h, w = last_frame.shape[:2]
        bgr = cv2.cvtColor(last_frame, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(DEPTH_SIDE_BY_SIDE_PATH), np.hstack([bgr, cv2.resize(coloured, (w, h))]))

        print(f"\nDepth map    → {DEPTH_COLOUR_PATH}")
        print(f"Side-by-side → {DEPTH_SIDE_BY_SIDE_PATH}")

        zones_final = _analyse_zones(last_depth_u8.astype(np.float32) / 255.0)
        print("\nFinal frame zones (higher = closer):")
        print(f"  {'Zone':<10} {'Label':<8}  mean    p95")
        for name, v in zones_final.items():
            print(f"  {name:<10} {v['zone']:<8}  {v['mean']:.3f}   {v['p95']:.3f}")

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"\n{'─'*46}")
        print(f"Timing ({len(latencies)} frames, {INPUT_SIZE}×{INPUT_SIZE} input):")
        print(f"  Avg {avg:.0f} ms  ({1000/avg:.1f} fps)  |  Min {min(latencies):.0f} ms  Max {max(latencies):.0f} ms")

    camera.stop()
    GPIO.cleanup()
    print("\nDone.")


if __name__ == "__main__":
    main()
