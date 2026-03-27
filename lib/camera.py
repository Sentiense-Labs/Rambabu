#!/usr/bin/env python3
"""
Camera class for AI RC Car
Captures frames using picamera2 library
"""

import numpy as np
import threading
import time
from picamera2 import Picamera2
import config
from utils.logger import log_error


class Camera:
    """Camera capture with background thread for continuous capture"""

    def __init__(self):
        """Initialize camera with background capture thread"""
        self.camera = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.latest_frame = None
        self.resolution = (config.CAMERA_WIDTH, config.CAMERA_HEIGHT)

    def start(self) -> dict:
        """Start camera and background capture thread."""
        if self.running:
            return {"status": "ok", "action": "start", "note": "already_running"}

        try:
            self.camera = Picamera2()
        except Exception as e:
            return {"status": "error", "error_code": "CAMERA_ERROR", "message": str(e)}

        cam_config = self.camera.create_preview_configuration(
            main={"size": self.resolution, "format": "RGB888"}
        )
        self.camera.configure(cam_config)
        self.camera.start()

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return {"status": "ok", "action": "start", "resolution": list(self.resolution)}

    def _capture_loop(self):
        """Background thread for continuous frame capture at 30fps"""
        while self.running:
            try:
                frame = self.camera.capture_array()
                # Camera is mounted upside-down — rotate 180° to correct
                frame = frame[::-1, ::-1]
                with self.lock:
                    self.latest_frame = frame
                time.sleep(0.033)  # ~30fps
            except Exception as e:
                log_error(f"Camera capture error: {e}")
                time.sleep(0.1)

    def stop(self) -> dict:
        """Stop camera and background thread."""
        self.running = False

        if self.thread:
            self.thread.join(timeout=1.0)

        if self.camera:
            self.camera.stop()
            self.camera.close()
            self.camera = None

        return {"status": "ok", "action": "stop"}

    def get_frame(self) -> np.ndarray | None:
        """Returns latest frame (thread-safe)."""
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
            return None

    def get_resolution(self) -> tuple[int, int]:
        """Returns current resolution (width, height)."""
        return self.resolution

    def cleanup(self) -> None:
        """Clean shutdown."""
        self.stop()
