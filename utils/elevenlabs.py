#!/usr/bin/env python3
"""
ElevenLabs TTS synthesizer.

Pure network helper — no hardware, no playback, no disk I/O. Given text,
returns raw mp3 bytes, or None on failure. Callers pipe the bytes to
lib.speaker.Speaker.play_mp3_bytes() and MUST provide a fallback for None.

Uses the /with-timestamps endpoint to mirror the working TSX reference in
docs/references/elevenlabsmessageservice.tsx — that endpoint has separate
rate-limit pools from the plain /text-to-speech endpoint and is much less
likely to return HTTP 429 `system_busy` under heavy ElevenLabs load.

Usage:
    from utils.elevenlabs import synthesize

    mp3 = synthesize("I think I'll go left.")
    if mp3 is not None:
        speaker.play_mp3_bytes(mp3)
    else:
        speaker.speak("I think I'll go left.")  # pyttsx3 fallback
"""

import base64
import os
import re

import httpx

import config
from utils.logger import log_info, log_error, log_warning


# Expressions like [excited], [sighs], [curious] are stripped before
# synthesis — these are stage directions meant for the reasoning model,
# not the voice.
_BRACKET_EXPRESSION = re.compile(r"\[[^\]]+\]")


def clean_text_for_tts(text: str) -> str:
    """Remove bracket expressions and trim whitespace."""
    return _BRACKET_EXPRESSION.sub("", text).strip()


def synthesize(
    text: str,
    voice_id: str | None = None,
    model_id: str | None = None,
) -> bytes | None:
    """Synthesize `text` via ElevenLabs and return raw mp3 bytes.

    Hits `/v1/text-to-speech/{voice_id}/with-timestamps`, which returns a
    JSON body containing base64 audio + character alignment. We decode the
    base64 and return the raw mp3 bytes — alignment data is discarded
    because the rover doesn't need word-level highlighting.

    Args:
        text: Non-empty string to synthesize. Bracket expressions like
            [excited] are stripped automatically.
        voice_id: Override config.ELEVENLABS_VOICE_ID for this call.
        model_id: Override config.ELEVENLABS_MODEL_ID for this call.

    Returns:
        Raw mp3 bytes on success, None on failure.
    """
    cleaned = clean_text_for_tts(text or "")
    if not cleaned:
        return None

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        log_warning("ELEVENLABS_API_KEY not set — skipping ElevenLabs synth")
        return None

    voice = voice_id or config.ELEVENLABS_VOICE_ID
    model = model_id or config.ELEVENLABS_MODEL_ID

    url = f"{config.ELEVENLABS_API_URL}/{voice}/with-timestamps"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": cleaned,
        "model_id": model,
        "voice_settings": {
            "stability": config.ELEVENLABS_STABILITY,
            "similarity_boost": config.ELEVENLABS_SIMILARITY,
            "speed": config.ELEVENLABS_SPEED,
        },
    }

    try:
        with httpx.Client(timeout=config.ELEVENLABS_TIMEOUT) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        log_error(f"ElevenLabs request failed: {exc}")
        return None

    if response.status_code != 200:
        # Surface the specific `status` ElevenLabs returns so quota vs.
        # `system_busy` are distinguishable in the logs.
        detail_status = None
        detail_message = None
        try:
            detail = response.json().get("detail", {})
            detail_status = detail.get("status")
            detail_message = detail.get("message")
        except (ValueError, AttributeError):
            pass
        log_error(
            f"ElevenLabs HTTP {response.status_code} "
            f"status={detail_status!r}: {detail_message or response.text[:200]}"
        )
        return None

    try:
        data = response.json()
    except ValueError as exc:
        log_error(f"ElevenLabs response was not JSON: {exc}")
        return None

    audio_base64 = data.get("audio_base64")
    if not isinstance(audio_base64, str) or not audio_base64:
        log_error("ElevenLabs response missing `audio_base64`")
        return None

    try:
        mp3_bytes = base64.b64decode(audio_base64)
    except (ValueError, TypeError) as exc:
        log_error(f"ElevenLabs base64 decode failed: {exc}")
        return None

    if not mp3_bytes:
        log_error("ElevenLabs returned an empty audio payload")
        return None

    log_info(f"ElevenLabs synth ok: {len(mp3_bytes)} bytes (via /with-timestamps)")
    return mp3_bytes
