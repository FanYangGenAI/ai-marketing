"""
Build LLM clients from model id strings in llm_config.json.

OpenAI vs Gemini is chosen by model name prefix. Identical model names share one
client instance (cache) within the process.
"""

from __future__ import annotations

from src.llm.base import BaseLLMClient

_client_cache: dict[str, BaseLLMClient] = {}


def clear_llm_client_cache() -> None:
    """Drop cached clients (for tests or config reload)."""
    _client_cache.clear()


def resolve_moderator_model(cfg: dict, stage: str) -> str:
    """
    Resolve which model id to use for debate Moderator.

    Args:
        cfg:    Parsed llm_config.json
        stage:  "strategy" | "planner" | "scriptwriter"

    Returns:
        Model string; falls back to {stage}_moderator then a safe default.
    """
    top = (cfg.get("moderator") or "").strip()
    if top:
        return top
    return cfg.get(f"{stage}_moderator") or "gemini-2.5-flash"


def _uses_openai(model_name: str) -> bool:
    n = model_name.lower().strip()
    return (
        n.startswith("gpt-")
        or n.startswith("o1")
        or n.startswith("o3")
        or n.startswith("o4")
        or n.startswith("chatgpt-")
    )


def build_llm_client(model_name: str) -> BaseLLMClient:
    """
    Return a client for the given model id. Caches by exact model string.

    Raises:
        KeyError / env errors from underlying clients if API keys missing.
    """
    key = model_name.strip()
    if not key:
        key = "gemini-2.5-flash"
    if key in _client_cache:
        return _client_cache[key]

    if _uses_openai(key):
        from src.llm.openai_client import OpenAIClient

        client: BaseLLMClient = OpenAIClient(model=key)
    else:
        from src.llm.gemini_client import GeminiClient

        client = GeminiClient(model=key)

    _client_cache[key] = client
    return client
