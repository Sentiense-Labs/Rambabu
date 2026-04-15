"""
look_around — capture a frame and describe it using Gemini Vision.

Returns a text description. If images are attached to the ToolResult they
are passed back to the LLM automatically by Agno.
"""

from __future__ import annotations

import io
import os

import cv2
from PIL import Image

from agno.middleware.logging import with_logging
from agno.middleware.timeout import with_timeout
from agno_ai.types.context import HardwareContext
from agno_ai import constants as C
from google import genai as google_genai

_GEMINI_VISION_MODEL = C.GEMINI_VISION_MODEL
_MAX_IMAGE_DIM = C.MAX_IMAGE_DIM
_JPEG_QUALITY = C.JPEG_QUALITY

_LOOK_AROUND_PERSONA = (
    "You are Rambabu, a small AI-powered RC rover with a camera. "
    "This image is what you can see right now."
)
_LOOK_AROUND_DEFAULT = (
    "Describe your surroundings in 2-3 short conversational sentences "
    "— first person, present tense. Mention specific objects you notice. "
    "Be curious and a little opinionated if something catches your eye. "
    "If the view is boring, say so honestly. "
    "End with one short sentence in this format: "
    "'Open path: left' or 'Open path: front' or 'Open path: right' or "
    "'Open path: none — back up'. Pick the most walkable lane based on "
    "what you see. If everything in view is blocked or cluttered, say "
    "'none — back up'."
)
_LOOK_AROUND_OUTPUT_RULES = (
    "Output only the spoken words — no brackets, no stage directions, "
    "no bullet points, no labels."
)


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


def _build_prompt(question: str | None) -> str:
    if question and question.strip():
        task = (
            f'The user just told you: "{question.strip()}"\n'
            "Respond to that request based on what you see in the image, "
            "in 2-3 short conversational sentences — first person, present "
            "tense. Stay in character as Rambabu."
        )
    else:
        task = _LOOK_AROUND_DEFAULT
    return f"{_LOOK_AROUND_PERSONA}\n\n{task}\n\n{_LOOK_AROUND_OUTPUT_RULES}"


@with_logging
@with_timeout(seconds=C.TIMEOUT_LOOK_AROUND)
def look_around(question: str | None = None, run_context=None) -> str:
    """Capture a frame and describe it. Pass a question to focus the answer."""
    hw = _get_hw(run_context)
    if hw is None or hw.camera is None:
        return '{"status": "error", "message": "camera not available"}'

    try:
        frame = hw.camera.get_frame()
        if frame is None:
            return '{"status": "error", "message": "camera returned no frame"}'

        ok, jpeg_buf = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY]
        )
        if not ok:
            return '{"status": "error", "message": "JPEG encoding failed"}'

        image = Image.open(io.BytesIO(jpeg_buf.tobytes()))
        image.thumbnail((_MAX_IMAGE_DIM, _MAX_IMAGE_DIM))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=_JPEG_QUALITY)

        from google.genai import types

        image_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        api_key = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
        client = google_genai.Client(api_key=api_key)
        prompt = _build_prompt(question)
        response = client.models.generate_content(
            model=_GEMINI_VISION_MODEL,
            contents=[image_part, prompt],
        )
        description = (response.text or "").strip()
        if not description:
            return '{"status": "error", "message": "Gemini returned empty description"}'
        return description

    except Exception as exc:
        return f'{{"status": "error", "message": "{exc}"}}'
