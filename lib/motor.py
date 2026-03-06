import RPi.GPIO as GPIO
import time

FORWARD = 22
REVERSE = 23

GPIO.setmode(GPIO.BCM)

GPIO.setup(FORWARD, GPIO.OUT)
GPIO.setup(REVERSE, GPIO.OUT)

def stop():
    GPIO.output(FORWARD,0)
    GPIO.output(REVERSE,0)

try:

    # Move Forward
    print("Forward")
    GPIO.output(FORWARD,1)
    GPIO.output(REVERSE,0)
    time.sleep(1)

    stop()
    time.sleep(2)

    # Move Reverse
    print("Reverse")
    GPIO.output(FORWARD,0)
    GPIO.output(REVERSE,1)
    time.sleep(1)

    stop()

except KeyboardInterrupt:
    GPIO.cleanup()