# BLE Command Reference

All commands are sent as UTF-8 JSON, base64-encoded, to the Command characteristic.

```
Device Name  : RC-Car
Service UUID : A1B20000-C3D4-E5F6-A7B8-C9D0E1F20000
Command UUID : A1B20001-C3D4-E5F6-A7B8-C9D0E1F20000
Status UUID  : A1B20002-C3D4-E5F6-A7B8-C9D0E1F20000
```

---

## Motor Drive

| Action | Required | Optional |
|---|---|---|
| `MOTOR_FRONT` | — | `speed` (0–100) |
| `MOTOR_BACK` | — | `speed` (0–100) |
| `MOTOR_STOP` | — | — |

```json
{"action": "MOTOR_FRONT", "speed": 70}
{"action": "MOTOR_BACK", "speed": 50}
{"action": "MOTOR_STOP"}
```

---

## Steering

| Action | Description |
|---|---|
| `MOTOR_LEFT` | Single pulse left |
| `MOTOR_RIGHT` | Single pulse right |
| `MOTOR_STEER_LEFT_HOLD` | Hold left |
| `MOTOR_STEER_RIGHT_HOLD` | Hold right |
| `MOTOR_STEER_CENTER` | Return to center |

```json
{"action": "MOTOR_STEER_LEFT_HOLD"}
{"action": "MOTOR_STEER_RIGHT_HOLD"}
{"action": "MOTOR_STEER_CENTER"}
```

---

## Compound (reverse + steer simultaneously)

```json
{"action": "MOTOR_BACK_STEER_LEFT", "speed": 50}
{"action": "MOTOR_BACK_STEER_RIGHT", "speed": 50}
```

---

## Pan Servo (camera left / right)

| Action | Required | Optional |
|---|---|---|
| `SERVO_PAN_TO` | `angle` (0–180) | — |
| `SERVO_PAN_LEFT` | — | `degrees` (default 10) |
| `SERVO_PAN_RIGHT` | — | `degrees` (default 10) |

```json
{"action": "SERVO_PAN_TO", "angle": 90}
{"action": "SERVO_PAN_LEFT", "degrees": 15}
{"action": "SERVO_PAN_RIGHT", "degrees": 15}
```

---

## Tilt Servo (camera up / down)

| Action | Required | Optional |
|---|---|---|
| `SERVO_TILT_TO` | `angle` (0–180) | — |
| `SERVO_TILT_UP` | — | `degrees` (default 10) |
| `SERVO_TILT_DOWN` | — | `degrees` (default 10) |

```json
{"action": "SERVO_TILT_TO", "angle": 90}
{"action": "SERVO_TILT_UP", "degrees": 15}
{"action": "SERVO_TILT_DOWN", "degrees": 15}
```

---

## Center Camera

```json
{"action": "SERVO_CENTER"}
```

---

## Expo App Integration (react-native-ble-plx)

### Setup

```ts
import { BleManager } from "react-native-ble-plx";
import { Buffer } from "buffer";

const manager = new BleManager();

const BLE_DEVICE_NAME     = "RC-Car";
const BLE_SERVICE_UUID    = "A1B20000-C3D4-E5F6-A7B8-C9D0E1F20000";
const BLE_COMMAND_UUID    = "A1B20001-C3D4-E5F6-A7B8-C9D0E1F20000";
```

### Connect

```ts
async function connectToRCCar(): Promise<Device> {
  return new Promise((resolve, reject) => {
    manager.startDeviceScan(null, null, (error, device) => {
      if (error) { reject(error); return; }

      if (device?.name === BLE_DEVICE_NAME) {
        manager.stopDeviceScan();
        device
          .connect()
          .then((d) => d.discoverAllServicesAndCharacteristics())
          .then(resolve)
          .catch(reject);
      }
    });
  });
}
```

### Send a command

```ts
async function sendCommand(
  device: Device,
  action: string,
  params: Record<string, unknown> = {}
): Promise<void> {
  const payload = Buffer.from(JSON.stringify({ action, ...params })).toString("base64");
  await device.writeCharacteristicWithResponseForService(
    BLE_SERVICE_UUID,
    BLE_COMMAND_UUID,
    payload
  );
}
```

### Usage examples

```ts
const device = await connectToRCCar();

// Drive
await sendCommand(device, "MOTOR_FRONT", { speed: 70 });
await sendCommand(device, "MOTOR_BACK",  { speed: 50 });
await sendCommand(device, "MOTOR_STOP");

// Steering
await sendCommand(device, "MOTOR_STEER_LEFT_HOLD");
await sendCommand(device, "MOTOR_STEER_CENTER");

// Reverse + steer
await sendCommand(device, "MOTOR_BACK_STEER_LEFT", { speed: 50 });

// Camera pan / tilt
await sendCommand(device, "SERVO_PAN_LEFT",  { degrees: 15 });
await sendCommand(device, "SERVO_TILT_UP",   { degrees: 10 });
await sendCommand(device, "SERVO_PAN_TO",    { angle: 45 });
await sendCommand(device, "SERVO_CENTER");
```

### Disconnect

```ts
await device.cancelConnection();
```
