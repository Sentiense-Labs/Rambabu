# test_gpio.py
import RPi.GPIO as GPIO
import time
from config import PAN_SERVO

GPIO.setmode(GPIO.BCM)
GPIO.setup(PAN_SERVO, GPIO.OUT)

pwm = GPIO.PWM(PAN_SERVO, 50)  # 50Hz for servo
pwm.start(0)

print("Testing servo sweep...")
for angle in [0, 45, 90, 135, 180, 90]:
    duty = 2 + (angle / 180) * 10
    pwm.ChangeDutyCycle(duty)
    print(f"Angle: {angle}° (duty: {duty}%)")
    time.sleep(1)

pwm.stop()
GPIO.cleanup()
print("Test complete!")
