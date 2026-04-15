from agno.middleware.logging import with_logging
from agno.middleware.timeout import with_timeout
from agno.types.context import HardwareContext
from agno import constants as C


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


@with_logging
@with_timeout(seconds=C.TIMEOUT_SAY)
def say(text: str, run_context=None) -> str:
    """Speak text through the Bluetooth speaker."""
    if not text or not text.strip():
        return '{"status": "error", "message": "no text provided"}'

    hw = _get_hw(run_context)
    if hw is None or hw.speaker is None:
        return '{"status": "error", "message": "speaker not available"}'

    try:
        from utils.elevenlabs import synthesize

        mp3 = synthesize(text)
        if mp3 is not None:
            hw.speaker.play_mp3_bytes(mp3)
            return f"status: ok\nengine: elevenlabs\nbytes: {len(mp3)}"
        else:
            hw.speaker.speak_sync(text)
            return "status: ok\nengine: pyttsx3"
    except Exception as exc:
        return f'{{"status": "error", "message": "{exc}"}}'
