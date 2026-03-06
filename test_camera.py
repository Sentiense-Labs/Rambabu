from picamera2 import Picamera2
import time

print("Testing basic camera capture...")
picam = Picamera2()
picam.configure(picam.create_still_configuration(main={"size": (640, 480)}))
picam.start()

# Try a simple capture
try:
    time.sleep(2)  # Let camera warm up
    frame = picam.capture_array()
    print(f"Success! Captured frame shape: {frame.shape}")
    picam.stop()
except Exception as e:
    print(f"Camera error: {e}")
    picam.stop()
