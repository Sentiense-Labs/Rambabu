#!/usr/bin/env python3
"""
Simple web server for testing dashboard without hardware
"""

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import time

app = Flask(__name__, template_folder="../static")
CORS(app)

# Mock state
state = {
    "mode": "MANUAL",
    "distance": 50,
    "pan": 90,
    "tilt": 90,
    "uptime": 0,
    "camera_active": False,
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/motor/<action>", methods=["POST"])
def motor_action(action):
    print(f"[API] Motor {action}")
    return jsonify({"status": "success", "action": action})


@app.route("/servo/pan", methods=["POST"])
def servo_pan():
    data = request.json or {}
    if "angle" in data:
        state["pan"] = data["angle"]
        print(f"[API] Pan to {data['angle']}°")
    return jsonify({"status": "success", "pan": state["pan"], "tilt": state["tilt"]})


@app.route("/servo/tilt", methods=["POST"])
def servo_tilt():
    data = request.json or {}
    if "angle" in data:
        state["tilt"] = data["angle"]
        print(f"[API] Tilt to {data['angle']}°")
    return jsonify({"status": "success", "pan": state["pan"], "tilt": state["tilt"]})


@app.route("/servo/center", methods=["POST"])
def servo_center():
    state["pan"] = 90
    state["tilt"] = 90
    print("[API] Centered servos")
    return jsonify({"status": "success", "pan": 90, "tilt": 90})


@app.route("/mode/<mode>", methods=["POST"])
def set_mode(mode):
    state["mode"] = mode
    print(f"[API] Mode set to {mode}")
    return jsonify({"status": "success", "mode": mode})


@app.route("/speak", methods=["POST"])
def speak():
    data = request.json or {}
    text = data.get("text", "")
    print(f"[API] Speaking: '{text}'")
    return jsonify({"status": "success", "text": text})


@app.route("/status")
def get_status():
    state["uptime"] = int(time.time())
    return jsonify(state)


@app.route("/video_feed")
def video_feed():
    return "Camera not available in test mode", 503


if __name__ == "__main__":
    print("=== Web Test Server ===")
    print("Access dashboard at: http://localhost:5000")
    print("Press Ctrl+C to stop")
    app.run(host="0.0.0.0", port=5000, debug=False)
