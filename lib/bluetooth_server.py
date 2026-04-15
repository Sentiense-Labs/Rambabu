#!/usr/bin/env python3
"""
BLE GATT server — allows a phone to control the RC car over Bluetooth.

The Pi advertises as "RC-Car". The phone connects and writes JSON commands
to the Command characteristic. Same payload format as MQTT:

    {"action": "MOTOR_FRONT", "speed": 70}
    {"action": "SERVO_PAN_LEFT", "degrees": 15}
    {"action": "MOTOR_STOP"}

To test without a custom app, use nRF Connect (Android/iOS):
  1. Scan → connect to "RC-Car"
  2. Open RC Car Control Service
  3. Write to Command characteristic (UTF-8 JSON string)
"""

import asyncio
import json
import subprocess
import threading
from typing import Any

from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)
from dbus_fast.aio import MessageBus
from dbus_fast import BusType

from server.mqtt.command_handler import CommandHandler
from utils.logger import log_info, log_warning, log_error

# ── UUIDs ─────────────────────────────────────────────────────────────────────
RC_CAR_SERVICE_UUID = "A1B20000-C3D4-E5F6-A7B8-C9D0E1F20000"
COMMAND_CHAR_UUID   = "A1B20001-C3D4-E5F6-A7B8-C9D0E1F20000"
STATUS_CHAR_UUID    = "A1B20002-C3D4-E5F6-A7B8-C9D0E1F20000"

DEVICE_NAME = "RC-Car"
_TAG = "[BLE]"


def _ble(msg: str) -> None:
    log_info(f"{_TAG} {msg}")

def _ble_warn(msg: str) -> None:
    log_warning(f"{_TAG} {msg}")

def _ble_err(msg: str) -> None:
    log_error(f"{_TAG} {msg}")


class BluetoothServer:
    """BLE GATT peripheral — accepts motor/servo commands from a phone."""

    def __init__(self, motor=None, pan_tilt=None, speaker=None, control_runner=None):
        self._handler = CommandHandler(
            motor=motor, pan_tilt=pan_tilt, speaker=speaker, control_runner=control_runner
        )
        self._server: BlessServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event: asyncio.Event | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> dict:
        """Start the BLE GATT server in a background daemon thread."""
        try:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True, name="ble-server"
            )
            self._thread.start()
            return {"status": "ok"}
        except Exception as e:
            _ble_err(f"Start failed: {e}")
            return {"status": "error", "message": str(e)}

    def cleanup(self) -> None:
        """Signal the async server to stop."""
        if self._stop_event and self._loop:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        _ble(f"Server stopped")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            _ble_err(f"Event loop error: {e}")

    async def _serve(self) -> None:
        self._stop_event = asyncio.Event()

        self._server = BlessServer(name=DEVICE_NAME, loop=self._loop)
        self._server.read_request_func = self._on_read
        self._server.write_request_func = self._on_write

        await self._server.add_new_service(RC_CAR_SERVICE_UUID)

        await self._server.add_new_characteristic(
            RC_CAR_SERVICE_UUID,
            COMMAND_CHAR_UUID,
            GATTCharacteristicProperties.write
            | GATTCharacteristicProperties.write_without_response,
            None,
            GATTAttributePermissions.writeable,
        )

        await self._server.add_new_characteristic(
            RC_CAR_SERVICE_UUID,
            STATUS_CHAR_UUID,
            GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
            bytearray(b"ok"),
            GATTAttributePermissions.readable,
        )

        await self._server.start()
        self._log_ready()

        await asyncio.gather(
            self._monitor_connections(),
            self._stop_event.wait(),
        )

        await self._server.stop()

    def _log_ready(self) -> None:
        mac = self._get_mac()
        _ble("=" * 46)
        _ble("  BLE SERVER READY")
        _ble(f"  Device Name  : {DEVICE_NAME}")
        _ble(f"  MAC Address  : {mac}")
        _ble(f"  Service UUID : {RC_CAR_SERVICE_UUID}")
        _ble(f"  Command UUID : {COMMAND_CHAR_UUID}")
        _ble(f"  Status UUID  : {STATUS_CHAR_UUID}")
        _ble("  Scan by name — works on Android + iOS")
        _ble("=" * 46)

    async def _monitor_connections(self) -> None:
        """Watch BlueZ D-Bus signals for device connect / disconnect events."""
        try:
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

            # Subscribe to BlueZ PropertiesChanged signals
            await bus.call_message(
                bus.create_message(
                    "org.freedesktop.DBus",
                    "/org/freedesktop/DBus",
                    "org.freedesktop.DBus",
                    "AddMatch",
                ).with_body(
                    "s",
                    [
                        "type='signal',"
                        "sender='org.bluez',"
                        "interface='org.freedesktop.DBus.Properties',"
                        "member='PropertiesChanged'"
                    ],
                )
            )

            def _on_message(msg) -> None:
                try:
                    if msg.member != "PropertiesChanged":
                        return
                    iface, changed, _ = msg.body
                    if iface != "org.bluez.Device1" or "Connected" not in changed:
                        return

                    addr = self._addr_from_path(msg.path)
                    connected = changed["Connected"].value
                    if connected:
                        _ble(f"  Device connected    : {addr}")
                    else:
                        _ble(f"  Device disconnected : {addr}")
                except Exception:
                    pass

            bus.add_message_handler(_on_message)
            await self._stop_event.wait()
            bus.disconnect()

        except Exception as e:
            _ble_warn(f"Connection monitor unavailable: {e}")

    # ── GATT callbacks ────────────────────────────────────────────────────────

    def _on_read(
        self, characteristic: BlessGATTCharacteristic, **kwargs: Any
    ) -> bytearray:
        return characteristic.value or bytearray()

    def _on_write(
        self, characteristic: BlessGATTCharacteristic, value: Any, **kwargs: Any
    ) -> None:
        if characteristic.uuid.lower() != COMMAND_CHAR_UUID.lower():
            return

        try:
            raw = bytes(value).decode("utf-8")
            payload = json.loads(raw)
            action = payload.get("action", "unknown")
            _ble(f"  Command received    : {action} | {payload}")
            self._handler.handle(topic="ble/command", payload=payload)
        except json.JSONDecodeError as e:
            _ble_warn(f"  Invalid JSON: {e} | raw={bytes(value)!r}")
        except Exception as e:
            _ble_err(f"  Command error: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_mac() -> str:
        try:
            out = subprocess.check_output(["bluetoothctl", "show"], text=True)
            for line in out.splitlines():
                if "Controller" in line:
                    return line.split()[1]
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def _addr_from_path(path: str) -> str:
        """Extract readable MAC from BlueZ path e.g. /org/bluez/hci0/dev_AA_BB_CC → AA:BB:CC"""
        try:
            part = path.split("/")[-1]          # dev_AA_BB_CC_DD_EE_FF
            return part.replace("dev_", "").replace("_", ":")
        except Exception:
            return path
