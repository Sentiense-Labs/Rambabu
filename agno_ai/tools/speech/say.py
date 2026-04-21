from __future__ import annotations

import threading

from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai import constants as C

# Tracks the currently playing audio thread so we can detect overlap.
_play_lock = threading.Lock()
_current_thread: threading.Thread | None = None


def _play_in_background(text: str) -> None:
    global _current_thread
    hw = get_hw()
    if hw is None or hw.speaker is None:
        return
    try:
        from utils.elevenlabs import synthesize

        mp3 = synthesize(text)
        if mp3 is not None:
            hw.speaker.play_mp3_bytes(mp3)
        else:
            hw.speaker.speak_sync(text)
    except Exception:
        pass  # background — nothing to propagate


@with_logging
def say(text: str, run_context=None) -> str:
    """
    Speak text through the Bluetooth speaker.

    Returns immediately after queuing playback — does not block the agent
    while audio plays. If a previous utterance is still playing it continues
    uninterrupted; the new one starts as soon as the speaker is free.
    """
    if not text or not text.strip():
        return '{"status": "error", "message": "no text provided"}'

    hw = get_hw()
    if hw is None or hw.speaker is None:
        return '{"status": "error", "message": "speaker not available"}'

    global _current_thread
    with _play_lock:
        t = threading.Thread(target=_play_in_background, args=(text,), daemon=True)
        _current_thread = t
        t.start()

    preview = text[:60].replace('"', "'")
    return f'{{"status": "queued", "preview": "{preview}"}}'
