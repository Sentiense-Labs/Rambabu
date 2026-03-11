#!/usr/bin/env python3
"""
Camera class for AI RC Car
Captures frames using picamera2 library
"""

import cv2
import numpy as np
import threading
from picamera2 import Picamera2
import config


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

    def start(self):
        """Start camera and background capture thread"""
        if self.running:
            return

        self.camera = Picamera2()

        # Configure camera
        config = self.camera.create_preview_configuration(
            main={"size": self.resolution}, format="BGR888"
        )
        self.camera.configure(config)

        # Start camera
        self.camera.start()

        # Start background capture thread
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        """Background thread for continuous frame capture at 30fps"""
        while self.running:
            try:
                # Capture frame
                frame = self.camera.capture_array()

                # Thread-safe update of latest frame
                with self.lock:
                    self.latest_frame = frame

                # 30fps = ~33ms per frame
                import time

                time.sleep(0.033)

            except Exception as e:
                # Log error but keep running
                print(f"Camera capture error: {e}")
                import time

                time.sleep(0.1)

    def stop(self):
        """Stop camera and background thread"""
        self.running = False

        if self.thread:
            self.thread.join(timeout=1.0)

        if self.camera:
            self.camera.stop()
            self.camera.close()
            self.camera = None

    def get_frame(self) -> np.ndarray | None:
        """Returns latest frame (thread-safe)"""
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
            return None

    def get_resolution(self) -> tuple[int, int]:
        """Returns current resolution (width, height)"""
        return self.resolution

    def cleanup(self):
        """Clean shutdown"""
        self.stop()
