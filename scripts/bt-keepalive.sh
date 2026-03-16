#!/usr/bin/env bash
# Bluetooth keepalive for STONE 300
# Checks connection every 30 seconds and reconnects if dropped.
# Registered as systemd user service: bt-keepalive.service

set -uo pipefail

SPEAKER_MAC="6E:8F:35:8A:8E:67"
SPEAKER_NAME="STONE 300"
CHECK_INTERVAL=30

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [bt-keepalive] $1"
}

is_connected() {
    bluetoothctl info "$SPEAKER_MAC" 2>/dev/null | grep -q "Connected: yes"
}

connect_speaker() {
    log "Attempting to connect to $SPEAKER_NAME ($SPEAKER_MAC)..."
    bluetoothctl connect "$SPEAKER_MAC" 2>/dev/null || true
    sleep 3

    if is_connected; then
        log "Connected to $SPEAKER_NAME"
        return 0
    else
        log "Failed to connect to $SPEAKER_NAME"
        return 1
    fi
}

set_default_sink() {
    # Wait for PulseAudio to register the Bluetooth sink
    sleep 3
    local sink
    sink=$(pactl list sinks short 2>/dev/null | grep -i "bluez" | awk '{print $2}' | head -1)
    if [[ -n "$sink" ]]; then
        pactl set-default-sink "$sink" 2>/dev/null
        pactl suspend-sink "$sink" 0 2>/dev/null
        log "Default sink set to $sink"
    else
        log "No Bluetooth sink found in PulseAudio"
    fi
}

log "Starting keepalive for $SPEAKER_NAME ($SPEAKER_MAC)"

while true; do
    if ! is_connected; then
        log "$SPEAKER_NAME disconnected — reconnecting..."
        if connect_speaker; then
            set_default_sink
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
