# AI RC Car — Atomic Project Structure

```
ai_rc_car/
│
├── main.py                        # Entry point — boots all modules in order, starts navigator loop
├── config.py                      # Single source of truth — GPIO pins, speeds, thresholds, AWS creds, MQTT topics
├── requirements.txt               # All pip dependencies
├── README.md                      # Setup, wiring, how to run
├── pinout.txt                     # Final GPIO reference (filled in after wiring phase)
│
│
├── lib/                           # ── ATOMIC HARDWARE CONTROL ──────────────────────────────────────
│   │                              #    Each file = one hardware concern. Import and call. No setup.
│   │                              #    Every function here is directly LLM-callable as a tool.
│   │
│   ├── motor.py                   # L9110S × 2 — drive control
│   │     front(speed=70)          #   Drive all 4 wheels forward
│   │     back(speed=70)           #   Drive all 4 wheels backward
│   │     left(speed=60)           #   Differential left turn
│   │     right(speed=60)          #   Differential right turn
│   │     stop()                   #   Immediate stop — all GPIO LOW
│   │     brake()                  #   Hard brake — L9110S brake mode
│   │     set_speed(percent)       #   Set global base speed 0–100
│   │     get_speed()              #   Returns current base speed %
│   │
│   ├── pan_tilt.py                # SG90 × 2 — camera pan-tilt bracket (GPIO 12, 13)
│   │     pan_left(deg=15)         #   Pan camera left by N degrees
│   │     pan_right(deg=15)        #   Pan camera right by N degrees
│   │     pan_to(angle)            #   Pan to absolute angle 0–180 (90 = center)
│   │     tilt_up(deg=15)          #   Tilt camera up by N degrees
│   │     tilt_down(deg=15)        #   Tilt camera down by N degrees
│   │     tilt_to(angle)           #   Tilt to absolute angle 0–180 (90 = level)
│   │     center()                 #   Reset both pan and tilt to 90°
│   │     get_angles()             #   Returns {"pan": int, "tilt": int}
│   │
│   ├── scanner.py                 # SG90 × 1 — ultrasonic scanner rotation (GPIO 25)
│   │     scan_left()              #   Rotate sensor to 135° (left)
│   │     scan_right()             #   Rotate sensor to 45° (right)
│   │     scan_center()            #   Return sensor to 90° (straight)
│   │     scan_to(angle)           #   Rotate to absolute angle
│   │     scan_sweep()             #   Full sweep — returns {"left_cm", "center_cm", "right_cm"}
│   │     get_angle()              #   Returns current scanner angle
│   │
│   ├── ultrasonic.py              # HC-SR04 — distance sensing (TRIG GPIO23, ECHO GPIO24)
│   │     get_distance()           #   Returns latest distance in cm (background thread, non-blocking)
│   │     is_clear(threshold=30)   #   True if distance > threshold
│   │     is_blocked(threshold=30) #   True if obstacle within threshold
│   │     get_zone()               #   Returns "CLEAR" / "CAUTION" / "BLOCKED"
│   │
│   ├── speaker.py                 # USB Speaker — voice output via pyttsx3 (non-blocking, queued)
│   │     speak(text)              #   Say any text through USB speaker
│   │     greet()                  #   Boot greeting — "AI car is online"
│   │     announce(label, conf)    #   "Person detected ahead, 94% confidence"
│   │     beep()                   #   Short alert tone for obstacle events
│   │     say_distance(cm)         #   "Obstacle at 18 centimeters"
│   │
│   ├── microphone.py              # USB Mic — voice input via SpeechRecognition (background thread)
│   │     listen()                 #   Start background listening thread (call once at boot)
│   │     get_command()            #   Returns latest command string or None
│   │     is_saying(word)          #   True if last command contains word
│   │     clear()                  #   Clear command queue after processing
│   │
│   └── camera.py                  # Pi Camera v2 — frame capture via Picamera2
│         start()                  #   Start camera (call once at boot, ~2s warmup)
│         stop()                   #   Release camera on shutdown
│         get_frame()              #   Latest BGR numpy array — thread-safe, ready for OpenCV
│         get_resolution()         #   Returns (width, height)
│
│
├── vision/                        # ── VISION PIPELINE ──────────────────────────────────────────────
│   │                              #    Uses lib/camera.py for frames. No direct hardware access.
│   │
│   ├── detector.py                # MobileNet SSD — object detection
│   │     detect(frame)            #   Run inference on frame, returns list of detections
│   │     get_detections()         #   Latest detections from most recent frame (LLM callable)
│   │     what_is_ahead()          #   Returns closest high-confidence detection label
│   │     closest_object()         #   Returns {label, confidence, distance_estimate}
│   │
│   └── stream.py                  # MJPEG stream server — Flask route /video_feed with detection overlay
│
│
├── navigation/                    # ── AUTONOMOUS BRAIN ─────────────────────────────────────────────
│   │                              #    Calls lib/ functions only. No direct GPIO access.
│   │
│   ├── modes.py                   # Mode state machine
│   │     set_mode(mode)           #   "AUTONOMOUS" | "MANUAL" | "STOPPED"
│   │     get_mode()               #   Returns current mode string
│   │     is_auto()                #   True if AUTONOMOUS
│   │     is_manual()              #   True if MANUAL
│   │
│   ├── avoidance.py               # Obstacle avoidance routine
│   │     check_and_avoid()        #   If blocked → stop → sweep → turn to clearest side → resume
│   │     avoid_obstacle()         #   Full avoidance sequence (called by navigator)
│   │
│   └── navigator.py               # 10Hz decision loop
│         run_loop()               #   Main loop: read sensors + detections → call lib/ actions
│                                  #   Also consumes voice commands and MQTT commands each tick
│
│
├── server/                        # ── CONNECTIVITY LAYER ───────────────────────────────────────────
│   │                              #    WiFi control + AWS IoT MQTT + Lighthouse IoT platform
│   │
│   ├── app.py                     # Flask app factory — registers all routes, serves static/
│   │
│   ├── routes.py                  # HTTP REST routes — thin bridge from HTTP → lib/ calls
│   │     POST /motor/<action>     #   front | back | left | right | stop
│   │     POST /servo/pan          #   body: {angle} or {direction, degrees}
│   │     POST /servo/tilt         #   body: {angle} or {direction, degrees}
│   │     POST /mode/<name>        #   AUTONOMOUS | MANUAL | STOPPED
│   │     POST /speak/<text>       #   Say something through speaker
│   │     GET  /status             #   Returns full car status JSON (for Lighthouse polling)
│   │     GET  /video_feed         #   MJPEG live stream with detection overlay
│   │
│   ├── mqtt/                      # ── AWS IoT Core + Lighthouse MQTT ──────────────────────────────
│   │   │
│   │   ├── client.py              # AWS IoT MQTT client — manages connection, reconnect, TLS certs
│   │   │     connect()            #   Connect to AWS IoT Core endpoint with cert auth
│   │   │     disconnect()         #   Clean disconnect
│   │   │     publish(topic, msg)  #   Publish JSON payload to any topic
│   │   │     subscribe(topic, cb) #   Subscribe to topic with callback function
│   │   │     is_connected()       #   Returns connection state bool
│   │   │
│   │   ├── topics.py              # All MQTT topic strings defined in one place
│   │   │     TELEMETRY            #   "car/telemetry"        → car publishes status here
│   │   │     COMMANDS             #   "car/commands"         → Lighthouse publishes here
│   │   │     DETECTIONS           #   "car/detections"       → car publishes what it sees
│   │   │     ALERTS               #   "car/alerts"           → obstacle / error events
│   │   │     CAMERA_CONTROL       #   "car/camera/control"   → pan/tilt commands from Lighthouse
│   │   │     MOTOR_CONTROL        #   "car/motor/control"    → drive commands from Lighthouse
│   │   │     MODE_CONTROL         #   "car/mode"             → mode switch from Lighthouse
│   │   │     ACK                  #   "car/ack"              → car confirms command received
│   │   │
│   │   ├── telemetry.py           # Publishes car status to AWS IoT on schedule
│   │   │     start_loop()         #   Starts background thread — publishes every N seconds
│   │   │     publish_status()     #   Sends: {mode, speed, distance, servo_angles, detections, uptime}
│   │   │     publish_detection()  #   Sends detection event immediately when object found
│   │   │     publish_alert()      #   Sends obstacle / error alert immediately
│   │   │
│   │   └── command_handler.py     # Receives MQTT commands from Lighthouse → calls lib/ functions
│   │         on_command(msg)      #   Parses incoming JSON → routes to correct lib/ function
│   │         on_motor(payload)    #   {"action": "front", "speed": 70} → lib/motor.front(70)
│   │         on_camera(payload)   #   {"pan": 45, "tilt": 90}          → lib/pan_tilt.pan_to(45)
│   │         on_mode(payload)     #   {"mode": "AUTONOMOUS"}           → navigation/modes.set_mode()
│   │         on_speak(payload)    #   {"text": "hello"}                → lib/speaker.speak()
│   │         register_all()       #   Subscribes all command topics on boot
│   │
│   └── __init__.py
│
│
├── utils/                         # ── SHARED HELPERS ───────────────────────────────────────────────
│   │                              #    No hardware code. No lib/ imports. Pure utility functions only.
│   │
│   ├── logger.py                  # Timestamped logging to logs/runtime.log
│   │     log_event(msg)           #   General event log
│   │     log_detection(lbl,cf,d)  #   Structured detection entry
│   │     log_mode_change(old,new) #   Mode transition log
│   │     log_mqtt(topic, msg)     #   MQTT publish/receive log
│   │     log_error(msg)           #   Error level entry
│   │
│   ├── timing.py                  # Time utilities
│   │     sleep_ms(ms)             #   Sleep N milliseconds
│   │     rate_limit(fn, hz)       #   Wrap function to max N calls/sec
│   │     debounce(fn, ms)         #   Prevent re-firing within ms window
│   │     stopwatch()              #   Context manager for timing code blocks
│   │
│   └── converters.py              # Unit and signal conversion
│         angle_to_duty(angle)     #   SG90 angle → pigpio duty cycle value
│         duty_to_angle(duty)      #   Reverse of above
│         percent_to_pwm(pct)      #   0–100% speed → 0–255 PWM value
│         cm_to_inches(cm)         #   Unit conversion
│
│
├── certs/                         # ── AWS IoT TLS CERTIFICATES ─────────────────────────────────────
│   ├── root-CA.crt                # Amazon Root CA — downloaded from AWS
│   ├── device.pem.crt             # Device certificate — issued by AWS IoT
│   └── private.pem.key            # Device private key — generated at registration
│                                  # ⚠ Never commit certs/ to git — add to .gitignore
│
│
├── model/                         # ── DETECTION MODEL ──────────────────────────────────────────────
│   ├── MobileNetSSD_deploy.caffemodel   # Trained weights (22MB) — download once
│   └── MobileNetSSD_deploy.prototxt    # Model architecture definition
│
│
├── static/                        # ── WEB DASHBOARD ────────────────────────────────────────────────
│   ├── index.html                 # Live stream + WASD control + mode toggle + servo controls
│   ├── style.css                  # Dashboard dark theme
│   └── control.js                 # Keydown → fetch() to /motor/ and /servo/ routes
│
│
└── logs/                          # ── RUNTIME LOGS (auto-created) ──────────────────────────────────
    └── runtime.log                # All events — detections, obstacles, MQTT, mode switches
```


---


## Import Rules (One-Way Only)

```
main.py
  └── imports from: navigation/, server/, lib/, vision/

navigation/
  └── imports from: lib/, utils/

server/routes.py
  └── imports from: lib/, navigation/modes

server/mqtt/
  └── imports from: lib/, navigation/modes, utils/

vision/
  └── imports from: lib/camera, utils/

lib/
  └── imports from: utils/, config  ← ONLY

utils/
  └── imports nothing internal      ← PURE PYTHON ONLY

config.py
  └── imports nothing               ← CONSTANTS ONLY
```


---


## MQTT Data Flow (AWS IoT Core ↔ Lighthouse)

```
  CAR (Raspberry Pi)                        AWS IoT Core              Lighthouse (Your Platform)
  ─────────────────                         ────────────              ──────────────────────────

  telemetry.py ──── PUBLISH ──────────────► car/telemetry  ─────────► Lighthouse subscribes
                    {mode, speed,                                       displays live dashboard
                     distance, angles,
                     detections, uptime}

  detector.py  ──── PUBLISH ──────────────► car/detections ─────────► Lighthouse triggers alerts
                    {label, confidence,                                 logs to your platform
                     timestamp}

  ultrasonic   ──── PUBLISH ──────────────► car/alerts     ─────────► Lighthouse notifies you
                    {type:"obstacle",
                     distance_cm}

                                            car/commands   ◄───────── Lighthouse publishes
  command_handler  ◄── SUBSCRIBE ──────────                            {"action":"front","speed":70}
  → calls lib/motor.front(70)

                                            car/camera/control ◄────── Lighthouse publishes
  command_handler  ◄── SUBSCRIBE ──────────                            {"pan":45,"tilt":90}
  → calls lib/pan_tilt.pan_to(45)

                                            car/mode ◄───────────────── Lighthouse publishes
  command_handler  ◄── SUBSCRIBE ──────────                            {"mode":"AUTONOMOUS"}
  → calls modes.set_mode()

  command_handler  ──── PUBLISH ──────────► car/ack        ─────────► Lighthouse confirms receipt
                    {command_id, status}
```


---


## Boot Order (main.py)

```
01  config.py loaded               — all pins, creds, topics available
02  lib/camera.start()             — camera warmup (~2s)
03  lib/ultrasonic — thread start  — distance polling every 50ms
04  lib/pan_tilt.center()          — camera servos to 90°
05  lib/scanner.scan_center()      — scanner servo to 90°
06  vision/detector — model load   — MobileNet SSD into RAM (~5–8s)
07  lib/microphone.listen()        — voice input thread starts
08  server/mqtt/client.connect()   — AWS IoT Core TLS connection
09  server/mqtt/command_handler.register_all()  — subscribe all command topics
10  server/mqtt/telemetry.start_loop()          — begin publishing status every 5s
11  lib/speaker.greet()            — "AI car is online"
12  server/app.py — Flask on :5000 — web dashboard + stream live
13  navigation/navigator.run_loop()             — 10Hz autonomous loop begins
```


---


## LLM Tool → lib/ Mapping

```
Tool Name          →  lib/ Function(s)                     Parameters
─────────────────────────────────────────────────────────────────────────────
move_motor         →  front() back() left() right() stop() direction, speed
pan_camera         →  pan_to() pan_left() pan_right()       angle or direction+degrees
tilt_camera        →  tilt_to() tilt_up() tilt_down()       angle or direction+degrees
center_camera      →  center()                              none
get_distance       →  get_distance() get_zone()             none → returns cm + zone
sweep_scan         →  scan_sweep()                          none → returns L/C/R distances
what_do_i_see      →  get_detections() what_is_ahead()      none → returns detection list
speak              →  speak() announce()                    text string
set_mode           →  modes.set_mode()                      "AUTONOMOUS"|"MANUAL"|"STOPPED"
get_status         →  get_mode() get_distance()             none → full status snapshot
                       get_angles() get_speed()
```