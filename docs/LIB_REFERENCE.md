# lib/ Module Reference

Hardware abstraction layer — one class per peripheral. Each class is designed as an LLM-callable tool with structured dict returns.

---

## motor.py — `MotorController`

Controls rear drive motor and steering motor via L9110S driver using RPi.GPIO PWM.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `front(speed)` | `speed: int = DEFAULT_SPEED` (0-100) | `dict` | Drive forward. Refuses if obstacle detected/latched. |
| `back(speed)` | `speed: int = DEFAULT_SPEED` (0-100) | `dict` | Drive backward. Clears obstacle latch. |
| `left()` | — | `dict` | Steer left for `STEER_PULSE_DURATION` then auto-center. |
| `right()` | — | `dict` | Steer right for `STEER_PULSE_DURATION` then auto-center. |
| `steer_left_hold()` | — | `dict` | Hold left steering (call `steer_center()` to release). |
| `steer_right_hold()` | — | `dict` | Hold right steering (call `steer_center()` to release). |
| `steer_center()` | — | `dict` | Return steering to center. |
| `stop()` | — | `dict` | Stop all motors immediately. |
| `set_obstacle_check(check_fn, clear_fn)` | callbacks | `None` | Inject obstacle detection callbacks. |
| `latch_obstacle()` | — | `None` | Engage obstacle latch (blocks forward). |
| `cleanup()` | — | `None` | Stop motors and release PWM/GPIO. |

**Properties:**
- `is_moving_forward` — `bool`, True when driving forward.

**Obstacle safety:** Two-layer system — obstacle latch engages on detection, only releases when distance exceeds `OBSTACLE_CLEAR_DISTANCE` or car reverses.

---

## pan_tilt.py — `PanTilt` (PCA9685 I2C version — active)

Controls pan/tilt camera servos via PCA9685 I2C PWM driver (smbus2). Uses move-and-kill pattern: send PWM, wait for settle, kill signal. No jitter at rest.

### Absolute Positioning

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `pan_to(angle)` | `angle: int` | `dict` | Pan to absolute angle (clamped to PAN_MIN..PAN_MAX). |
| `tilt_to(angle)` | `angle: int` | `dict` | Tilt to absolute angle (clamped to TILT_MIN..TILT_MAX). |

### Relative Step Moves

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `pan_left(deg)` | `deg: int = 10` | `dict` | Pan left by degrees. |
| `pan_right(deg)` | `deg: int = 10` | `dict` | Pan right by degrees. |
| `tilt_up(deg)` | `deg: int = 10` | `dict` | Tilt up by degrees. |
| `tilt_down(deg)` | `deg: int = 10` | `dict` | Tilt down by degrees. |

### Continuous Movement (Joystick)

8-direction smooth movement — starts a background thread that steps until stopped or limit hit.

| Method | Returns | Description |
|--------|---------|-------------|
| `pan_left_start()` | `dict` | Start continuous pan left. |
| `pan_right_start()` | `dict` | Start continuous pan right. |
| `tilt_up_start()` | `dict` | Start continuous tilt up. |
| `tilt_down_start()` | `dict` | Start continuous tilt down. |
| `up_left_start()` | `dict` | Start continuous up-left diagonal. |
| `up_right_start()` | `dict` | Start continuous up-right diagonal. |
| `down_left_start()` | `dict` | Start continuous down-left diagonal. |
| `down_right_start()` | `dict` | Start continuous down-right diagonal. |
| `servo_stop()` | `dict` | Stop current movement, kill PWM. |

### Utility

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `center()` | — | `dict` | Return to PAN_CENTER / TILT_CENTER. |
| `get_angles()` | — | `dict[str, int]` | Current `{"pan": ..., "tilt": ...}`. |
| `set_as_current_center()` | — | `None` | Mark current position as 90/90 reference. |
| `pan_scan(start, end, step)` | `start: int, end: int, step: int = 2` | `None` | Sweep pan from start to end. |
| `cleanup()` | — | `None` | Center, kill PWM, close I2C bus. |

---

## camera.py — `Camera`

Captures frames from Pi Camera v2 via picamera2 with a background thread at ~30fps. Frames are rotated 180 (camera mounted upside-down).

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `start()` | — | `dict` | Start camera and background capture thread. |
| `stop()` | — | `dict` | Stop camera and thread. |
| `get_frame()` | — | `np.ndarray \| None` | Latest frame (thread-safe copy). |
| `get_resolution()` | — | `tuple[int, int]` | Current (width, height). |
| `cleanup()` | — | `None` | Alias for `stop()`. |

---

## ultrasonic.py — `Ultrasonic`

HC-SR04 distance sensor with median-filtered background measurement at 20Hz. Includes streak confirmation and emergency fast-path.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `start()` | — | `dict` | Start background measurement thread. |
| `stop()` | — | `dict` | Stop background thread. |
| `get_distance()` | — | `float` | Median-filtered distance in cm (thread-safe). |
| `is_obstacle_confirmed()` | — | `bool` | True when filtered evidence confirms real obstacle. |
| `is_clear(threshold)` | `threshold: int = SAFE_DISTANCE` | `bool` | True if distance > threshold. |
| `is_blocked(threshold)` | `threshold: int = STOP_DISTANCE` | `bool` | True if distance < threshold. |
| `get_zone()` | — | `str` | `"safe"`, `"warning"`, or `"danger"`. |
| `wait_for_reading(timeout)` | `timeout: float = 2.0` | `bool` | Block until valid reading available. |
| `cleanup()` | — | `None` | Alias for `stop()`. |

**Filtering:** Median of 5 rolling window + streak confirmation (2 consecutive medians below threshold). Emergency path at <10cm with plausibility check.

---

## microphone.py — `Microphone`

Two-stage voice pipeline: OpenWakeWord detection at 16kHz, then faster-whisper STT transcription.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `start()` | — | `dict` | Start background wake-word listening thread. |
| `stop()` | — | `dict` | Stop listening thread. |
| `get_command()` | — | `str \| None` | Latest transcribed command (consumes it). |
| `is_listening()` | — | `bool` | True if background thread is active. |
| `clear()` | — | `dict` | Clear command buffer. |
| `cleanup()` | — | `None` | Stop thread and release PyAudio. |

**Pipeline:** Wake word detected -> record utterance (energy-based VAD) -> transcribe with Whisper -> store command.

---

## speaker.py — `Speaker`

Bluetooth speaker management (Sony SRS-XB13) with TTS (pyttsx3) and audio playback (WAV/MP3).

### Bluetooth

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `is_connected()` | — | `bool` | Check if BT speaker is connected. |
| `connect()` | — | `dict` | Connect to BT speaker, set as default sink. |
| `reconnect()` | — | `dict` | Disconnect then reconnect. |

### TTS

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `speak(text)` | `text: str` | `dict` | Queue text for speech (non-blocking). |
| `speak_sync(text)` | `text: str` | `dict` | Speak text synchronously (blocking). |
| `greet()` | — | `dict` | Say "AI RC Car is online and ready". |
| `announce(label, confidence)` | `label: str, confidence: float` | `dict` | Announce detection if above threshold. |
| `say_distance(cm)` | `cm: float` | `dict` | Speak distance if within threshold. |

### Audio Playback

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `play_wav(file_path)` | `file_path: str` | `dict` | Play WAV file (blocking). |
| `play_wav_async(file_path)` | `file_path: str` | `dict` | Play WAV file in background thread. |
| `play_mp3(file_path)` | `file_path: str` | `dict` | Play MP3 file (blocking, via mpg123). |
| `play_mp3_async(file_path)` | `file_path: str` | `dict` | Play MP3 file in background thread. |

### Settings

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `set_rate(rate)` | `rate: int` | `dict` | Set speech rate (WPM). |
| `set_volume(volume)` | `volume: float` (0.0-1.0) | `dict` | Set speech volume. |
| `start()` / `stop()` / `cleanup()` | — | `dict` / `None` | Lifecycle management. |

---

## bluetooth_server.py — `BluetoothServer`

BLE GATT server — phone connects and sends JSON commands via the Command characteristic. Same payload format as MQTT.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `start()` | — | `dict` | Start BLE GATT server in background thread. |
| `cleanup()` | — | `None` | Signal async server to stop. |

**Service:** `RC-Car` (advertised name)
**Command format:** `{"action": "MOTOR_FRONT", "speed": 70}`
**Test with:** nRF Connect app on Android/iOS.

---

## Legacy / Inactive Files

| File | Status | Description |
|------|--------|-------------|
| `pan_tilt_gpiozero.py` | Legacy | PanTilt via RPi.GPIO software PWM (replaced by PCA9685 I2C version). |
| `pan_tilt_old.py` | Legacy | Original PanTilt without continuous movement support. |
| `scanner.py` | Empty | Placeholder (no implementation). |
| `__init__.py` | Empty | Package marker. |
