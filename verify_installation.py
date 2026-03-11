#!/usr/bin/env python3
"""
Complete installation verification for AI RC Car project
"""

import sys
import subprocess


def test_import(package_name, import_name=None):
    """Test if a package can be imported"""
    try:
        __import__(import_name or package_name)
        print(f"✓ {package_name}")
        return True
    except ImportError as e:
        print(f"✗ {package_name}: {e}")
        return False


def test_hardware_access():
    """Test hardware access"""
    print("\n=== Hardware Access Tests ===")

    # Test GPIO
    try:
        import RPi.GPIO as GPIO

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        print("✓ GPIO access")
        GPIO.cleanup()
    except Exception as e:
        print(f"✗ GPIO access: {e}")

    # Test camera
    try:
        from picamera2 import Picamera2

        camera = Picamera2()
        print("✓ Camera initialization")
        camera.close()
    except Exception as e:
        print(f"✗ Camera initialization: {e}")

    # Test audio devices
    try:
        import speech_recognition as sr

        mic_list = sr.Microphone.list_microphone_names()
        print(f"✓ Audio devices found: {len(mic_list)} microphones")
    except Exception as e:
        print(f"✗ Audio devices: {e}")


def main():
    print("=== AI RC Car Installation Verification ===")

    # Core packages
    core_packages = [
        ("RPi.GPIO", "RPi.GPIO"),
        ("cv2", "cv2"),
        ("numpy", "numpy"),
        ("picamera2", "picamera2"),
        ("flask", "flask"),
        ("httpx", "httpx"),
        ("orjson", "orjson"),
    ]

    # AI/ML packages
    ai_packages = [
        ("faster_whisper", "faster_whisper"),
        ("pyttsx3", "pyttsx3"),
        ("speech_recognition", "speech_recognition"),
    ]

    # Connectivity packages
    connectivity_packages = [
        ("paho.mqtt.client", "paho.mqtt.client"),
        ("awsiot", "awsiot"),
    ]

    print("\n=== Core Packages ===")
    core_ok = sum(test_import(*pkg) for pkg in core_packages)

    print("\n=== AI/ML Packages ===")
    ai_ok = sum(test_import(*pkg) for pkg in ai_packages)

    print("\n=== Connectivity Packages ===")
    connectivity_ok = sum(test_import(*pkg) for pkg in connectivity_packages)

    test_hardware_access()

    # Summary
    total_packages = len(core_packages) + len(ai_packages) + len(connectivity_packages)
    working_packages = core_ok + ai_ok + connectivity_ok

    print(f"\n=== Summary ===")
    print(f"Working packages: {working_packages}/{total_packages}")

    if working_packages >= total_packages * 0.8:  # 80% success rate
        print("🎉 Installation successful! Ready to start development.")
        return True
    else:
        print("⚠️  Some packages failed. Check the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
