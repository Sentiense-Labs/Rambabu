"""
Model presets for Agno agents.

Mirrors the Mastra ModelPresets pattern:
  - Pre-configured model instances with metadata
  - Factory function get_model() for instantiation
  - Support for timeout configuration and prompt caching

Usage:
  from agno.models import get_model

  # Agent model (default)
  agent_model = get_model("FAST")

  # Compression model (background LLM passes)
  compress_model = get_model("COMPRESSION")

  # With extra kwargs
  model = get_model("BALANCED", temperature=0.3, thinking_budget=1280)

Available presets:
  FAST          gemini-2.5-flash       (default agent model)
  BALANCED      gemini-2.5-pro       (complex reasoning)
  COMPRESSION   gemini-2.5-flash-lite (background synthesis)
  ANTHROPIC     claude-sonnet-4-5    (reasoning — expensive, use selectively)
"""

from __future__ import annotations

import os
from typing import Any, Callable

import httpx

from agno.models.google import Gemini
from agno.models.anthropic import Claude
from agno.models.openai import OpenAIChat

# ── Timeout constants (mirrors Mastra's undici setup) ────────────────────────────

HEADERS_TIMEOUT = 600_000  # 10 minutes — wait for API to start responding
BODY_TIMEOUT = 600_000  # 10 minutes — wait for full body
CONNECT_TIMEOUT = 30_000  # 30 seconds — initial TCP connect


def _make_httpx_client(
    headers_timeout: int = HEADERS_TIMEOUT,
    body_timeout: int = BODY_TIMEOUT,
    connect_timeout: int = CONNECT_TIMEOUT,
) -> httpx.Client:
    """Create an httpx client with Mastra-style timeouts."""
    return httpx.Client(
        timeout=httpx.Timeout(
            headers=headers_timeout / 1000,
            read=body_timeout / 1000,
            connect=connect_timeout / 1000,
        ),
    )


# ── Model presets ────────────────────────────────────────────────────────────────

PRESETS: dict[str, dict[str, Any]] = {
    # Google Gemini
    "FAST": {
        "model_class": Gemini,
        "model_id": "gemini-2.5-flash",
        "provider": "google",
        "description": "Gemini 2.5 Flash — $0.30/$2.50 per 1M tokens, 1M context",
        "use_case": "Default agent model, development, cost-sensitive",
        "extra_kwargs": {},
    },
    "BALANCED": {
        "model_class": Gemini,
        "model_id": "gemini-2.5-pro",
        "provider": "google",
        "description": "Gemini 2.5 Pro — $1.25/$10.00 per 1M tokens, 2M context",
        "use_case": "Complex reasoning, large context tasks",
        "extra_kwargs": {},
    },
    "COMPRESSION": {
        "model_class": Gemini,
        "model_id": "gemini-2.5-flash-lite",
        "provider": "google",
        "description": "Gemini 2.5 Flash Lite — cheapest for background synthesis",
        "use_case": "Memory compression, observation/reflect passes",
        "extra_kwargs": {},
    },
    "VISION": {
        "model_class": Gemini,
        "model_id": "gemini-2.5-flash",
        "provider": "google",
        "description": "Gemini 2.5 Flash — multimodal vision",
        "use_case": "look_around camera analysis",
        "extra_kwargs": {},
    },
    # OpenAI
    "OPENAI_FAST": {
        "model_class": OpenAIChat,
        "model_id": "gpt-4o-mini",
        "provider": "openai",
        "description": "GPT-4o Mini — $0.15/$0.60 per 1M tokens",
        "use_case": "Simple tasks, high-volume, cost-sensitive",
        "extra_kwargs": {},
    },
    "OPENAI_BALANCED": {
        "model_class": OpenAIChat,
        "model_id": "gpt-4.1",
        "provider": "openai",
        "description": "GPT-4.1 — $2.00/$8.00 per 1M tokens, 1M context",
        "use_case": "General-purpose production",
        "extra_kwargs": {},
    },
    # Anthropic (expensive — use selectively)
    "ANTHROPIC": {
        "model_class": Claude,
        "model_id": "claude-sonnet-4-5",
        "provider": "anthropic",
        "description": "Claude Sonnet 4.5 — $3.00/$15.00 per 1M tokens",
        "use_case": "Complex reasoning, structured output, code analysis",
        "extra_kwargs": {
            "cache_system_prompt": True,
        },
    },
    "ANTHROPIC_FAST": {
        "model_class": Claude,
        "model_id": "claude-haiku-4-5",
        "provider": "anthropic",
        "description": "Claude Haiku 4.5 — $1.00/$5.00 per 1M tokens",
        "use_case": "Fast structured formatting, low-cost Anthropic",
        "extra_kwargs": {
            "cache_system_prompt": True,
        },
    },
}


# ── API key getters ─────────────────────────────────────────────────────────────

_API_KEY_GETTERS: dict[str, Callable[[], str | None]] = {
    "google": lambda: os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY"),
    "openai": lambda: os.environ.get("OPENAI_API_KEY"),
    "anthropic": lambda: os.environ.get("ANTHROPIC_API_KEY"),
}


def _get_api_key(provider: str) -> str:
    getter = _API_KEY_GETTERS.get(provider, lambda: None)
    key = getter()
    if not key:
        env_var = {
            "google": "GOOGLE_GENERATIVE_AI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }[provider]
        raise RuntimeError(
            f"{env_var} is not set — required for {provider} model preset"
        )
    return key


# ── Public factory ───────────────────────────────────────────────────────────────


def get_model(
    name: str,
    api_key: str | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> Gemini | Claude | OpenAIChat:
    """Resolve a named preset to an instantiated model.

    Args:
        name: Preset name (e.g. "FAST", "BALANCED", "COMPRESSION")
        api_key: Override API key for this call. Falls back to env vars.
        timeout: Request timeout override in seconds.
        **kwargs: Additional kwargs merged with preset extra_kwargs,
            forwarded to the model constructor.
    """
    preset = PRESETS.get(name)
    if preset is None:
        raise KeyError(
            f"Unknown model preset '{name}'. Available: {list(PRESETS.keys())}"
        )

    model_cls = preset["model_class"]
    model_id = preset["model_id"]
    provider = preset["provider"]

    resolved_key = api_key or _get_api_key(provider)

    # Build constructor kwargs: extra_kwargs + call-site kwargs (call-site wins)
    extra = dict(preset["extra_kwargs"])
    extra.update(kwargs)

    # Timeout can come from preset (default) or call-site override
    if timeout is not None:
        extra["timeout"] = timeout

    # httpx client for Anthropic — mirrors Mastra's undici timeout setup
    if provider == "anthropic" and "http_client" not in extra:
        extra["http_client"] = _make_httpx_client()

    return model_cls(id=model_id, api_key=resolved_key, **extra)
