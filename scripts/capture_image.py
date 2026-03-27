#!/usr/bin/env python3
"""
Captures a still image from the PiCamera, saves it to the workspace,
and prints the file path to stdout.
"""
import sys
import os
import time
from picamera2 import Picamera2

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

def capture_image():
    output_path = ""
    picam2 = None
    try:
        picam2 = Picamera2()
        config = picam2.create_still_configuration(main={"size": (1920, 1080)})
        picam2.configure(config)
        picam2.start()
        time.sleep(2) # Camera warm-up

        workspace_dir = "/home/rambabu/.openclaw/workspace/captures"
        os.makedirs(workspace_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        file_name = f"capture-{timestamp}.jpg"
        output_path = os.path.join(workspace_dir, file_name)

        picam2.capture_file(output_path)
        print(output_path)

    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}", file=sys.stderr)
        
    finally:
        if picam2 and picam2.started:
            picam2.stop()
            picam2.close()

if __name__ == "__main__":
    capture_image()
