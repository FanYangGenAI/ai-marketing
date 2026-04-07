"""Tests for src.llm.client_factory."""

import pytest

from src.llm.client_factory import (
    build_llm_client,
    clear_llm_client_cache,
    resolve_moderator_model,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_llm_client_cache()
    yield
    clear_llm_client_cache()


def test_resolve_moderator_prefers_top_level_moderator():
    cfg = {"moderator": "gemini-pro", "planner_moderator": "other"}
    assert resolve_moderator_model(cfg, "planner") == "gemini-pro"


def test_resolve_moderator_falls_back_to_stage_key():
    cfg = {"planner_moderator": "gemini-x"}
    assert resolve_moderator_model(cfg, "planner") == "gemini-x"


def test_resolve_moderator_default():
    assert resolve_moderator_model({}, "planner") == "gemini-2.5-flash"


def test_build_llm_client_caches_same_model(monkeypatch):
    class FakeOpenAI:
        def __init__(self, model: str = ""):
            self._model = model

        def model_name(self) -> str:
            return self._model

    monkeypatch.setattr("src.llm.openai_client.OpenAIClient", FakeOpenAI)
    a = build_llm_client("gpt-5-nano")
    b = build_llm_client("gpt-5-nano")
    assert a is b


def test_build_llm_client_gemini_branch(monkeypatch):
    class FakeGemini:
        def __init__(self, model: str = ""):
            self._model = model

        def model_name(self) -> str:
            return self._model

    monkeypatch.setattr("src.llm.gemini_client.GeminiClient", FakeGemini)
    g = build_llm_client("gemini-2.5-flash")
    assert g.model_name() == "gemini-2.5-flash"
