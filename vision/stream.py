#!/usr/bin/env python3
"""
MJPEG streaming module for AI RC Car
Generates video frames with optional detection overlay
"""

import cv2
import time
from typing import Optional, Generator, Tuple
from utils.logger import log_debug, log_error


def generate_frames(camera, detector=None) -> Generator[bytes, None, None]:
    """
    Generate MJPEG frames from camera with optional detection overlay

    Args:
        camera: Camera instance
        detector: Optional detector instance for object detection

    Yields:
        JPEG encoded frames in MJPEG format
    """
    if not camera:
        log_error("Camera not available for streaming")
        return

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            # Get frame from camera
            frame = camera.get_frame()

            if frame is None:
                log_debug("No frame available")
                time.sleep(0.1)
                continue

            # Optional detection overlay
            if detector:
                frame = add_detection_overlay(frame, detector)

            # Add distance overlay (if ultrasonic available)
            # This would be passed in or accessed globally
            # For now, just add timestamp
            frame = add_info_overlay(frame)

            # Encode as JPEG
            ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            if not ret:
                log_error("Failed to encode frame")
                continue

            # Yield MJPEG frame
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            )

            # Frame rate control (~15fps)
            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed > 0:
                fps = frame_count / elapsed
                target_interval = 1.0 / 15.0  # 15fps
                actual_interval = 1.0 / fps
                if actual_interval < target_interval:
                    time.sleep(target_interval - actual_interval)

    except Exception as e:
        log_error(f"Frame generation error: {e}")
        raise


def add_detection_overlay(frame, detector) -> Tuple:
    """
    Add detection bounding boxes and labels to frame

    Args:
        frame: Input frame
        detector: Detector instance

    Returns:
        Frame with detection overlay
    """
    try:
        # Get detections from detector
        detections = detector.detect(frame)

        for detection in detections:
            if detection["confidence"] > 0.5:
                # Draw bounding box
                x1, y1, x2, y2 = detection["box"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # Draw label with confidence
                label = f"{detection['label']}: {detection['confidence']:.0%}"
                cv2.putText(
                    frame,
                    label,
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2,
                )

        return frame

    except Exception as e:
        log_debug(f"Detection overlay error: {e}")
        return frame


def add_info_overlay(frame) -> Tuple:
    """
    Add information overlay to frame

    Args:
        frame: Input frame

    Returns:
        Frame with info overlay
    """
    try:
        h, w = frame.shape[:2]

        # Add timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            frame,
            timestamp,
            (10, h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        # Add frame rate
        fps = "15 FPS"
        cv2.putText(
            frame,
            fps,
            (w - 80, h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        return frame

    except Exception as e:
        log_debug(f"Info overlay error: {e}")
        return frame


class VideoStream:
    """Video stream manager with graceful error handling"""

    def __init__(self, camera, detector=None):
        """
        Initialize video stream

        Args:
            camera: Camera instance
            detector: Optional detector instance
        """
        self.camera = camera
        self.detector = detector
        self.running = False

    def start(self) -> Generator[bytes, None, None]:
        """
        Start streaming frames

        Yields:
            MJPEG encoded frames
        """
        self.running = True

        try:
            yield from generate_frames(self.camera, self.detector)

        except Exception as e:
            log_error(f"Stream error: {e}")
            self.running = False
            raise

    def stop(self):
        """Stop streaming"""
        self.running = False
