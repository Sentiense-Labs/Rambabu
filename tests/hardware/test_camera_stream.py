#!/usr/bin/env python3
"""
Camera stream test — standalone Flask server serving MJPEG feed.

Opens Pi Camera, streams MJPEG at /video_feed, and serves a minimal
HTML viewer at / so you can watch the feed in any browser on the network.

Run:
    sudo .venv/bin/python3 scripts/test_camera_stream.py

Then open:
    http://<pi-ip>:5001
"""

import sys
import time
import cv2
from flask import Flask, Response, render_template_string
from lib.camera import Camera

PORT = 5001

HTML = """<!DOCTYPE html>
<html>
<head>
  <title>RC Car Camera Test</title>
  <style>
    body {
      margin: 0;
      background: #111;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      font-family: monospace;
      color: #eee;
    }
    h2 { margin-bottom: 12px; letter-spacing: 2px; }
    img {
      border: 2px solid #444;
      border-radius: 6px;
      max-width: 100%;
    }
    p { margin-top: 10px; font-size: 13px; color: #888; }
  </style>
</head>
<body>
  <h2>RC Car — Camera Feed</h2>
  <img src="/video_feed" />
  <p>MJPEG stream &bull; 1920×1080 &bull; ~15fps</p>
</body>
</html>"""

app = Flask(__name__)
camera = None


def generate():
    """Yield MJPEG frames from the camera."""
    while True:
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        # Timestamp overlay
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        h, w = frame.shape[:2]
        cv2.putText(
            frame, ts, (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
        )

        ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
        )

        time.sleep(1 / 15)  # 15 fps cap


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/video_feed")
def video_feed():
    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def main():
    global camera

    print("Starting camera ...")
    camera = Camera()
    result = camera.start()
    if result["status"] != "ok":
        print(f"Camera failed to start: {result}", file=sys.stderr)
        sys.exit(1)

    print(f"Camera started at {result['resolution'][0]}x{result['resolution'][1]}")
    print(f"\nOpen in browser:  http://<pi-ip>:{PORT}")
    print(f"Direct stream:    http://<pi-ip>:{PORT}/video_feed")
    print("Press Ctrl+C to stop.\n")

    try:
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping camera ...")
        camera.cleanup()


if __name__ == "__main__":
    main()
