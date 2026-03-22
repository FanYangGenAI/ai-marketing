"""单元测试：BaseAgent 基类 + AgentContext + AgentOutput"""

import pytest
from datetime import date
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage, LLMResponse


# ── Mock LLM Client ───────────────────────────────────────────────────────────

class MockLLMClient(BaseLLMClient):
    def __init__(self, response_text: str = "mock response"):
        self._response = response_text

    def model_name(self) -> str:
        return "mock-model"

    async def chat(self, messages, system=None, max_tokens=4096, temperature=0.7) -> LLMResponse:
        return LLMResponse(
            content=self._response,
            model="mock-model",
            input_tokens=10,
            output_tokens=20,
        )


# ── Mock Concrete Agent ───────────────────────────────────────────────────────

class EchoAgent(BaseAgent):
    """测试用 Agent，将输入写入文件后返回 AgentOutput。"""

    async def run(self, context: AgentContext) -> AgentOutput:
        output_path = context.daily_folder / "echo_output.txt"
        self._write_output(output_path, f"echo: {context.user_note}")
        return AgentOutput(
            output_path=output_path,
            summary="echo done",
        )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def context(tmp_path) -> AgentContext:
    campaign_root = tmp_path / "campaigns" / "TestProduct"
    daily = campaign_root / "daily" / "2026-03-17"
    daily.mkdir(parents=True)
    return AgentContext(
        campaign_root=campaign_root,
        daily_folder=daily,
        run_date=date(2026, 3, 17),
        product_name="TestProduct",
        user_note="测试备注",
    )


def test_agent_context_paths(context, tmp_path):
    assert context.asset_library_root == context.campaign_root / "asset_library"
    assert context.strategy_path == context.daily_folder / "strategy" / "strategy_suggestion.md"
    assert context.strategy_latest_mirror_path == context.campaign_root / "strategy_suggestion.md"


def test_agent_context_subdir(context):
    sub = context.subdir("plan")
    assert sub.exists()
    assert sub == context.daily_folder / "plan"


def test_agent_context_subdir_nested(context):
    sub = context.subdir("assets", "raw")
    assert sub.exists()


@pytest.mark.asyncio
async def test_echo_agent_run(context):
    agent = EchoAgent(
        name="EchoAgent",
        llm_client=MockLLMClient(),
        role_description="test",
    )
    output = await agent.run(context)
    assert output.success is True
    assert output.output_path.exists()
    assert output.read_text() == "echo: 测试备注"


def test_agent_output_to_context_extra(context, tmp_path):
    p = tmp_path / "out.txt"
    p.write_text("hello")
    out = AgentOutput(output_path=p, summary="test summary")
    extra = out.to_context_extra("planner")
    assert "planner" in extra
    assert extra["planner"]["summary"] == "test summary"


def test_read_optional_missing(context):
    agent = EchoAgent("a", MockLLMClient())
    result = agent._read_optional(Path("/nonexistent/file.txt"), default="fallback")
    assert result == "fallback"


def test_write_json(context):
    agent = EchoAgent("a", MockLLMClient())
    out_path = context.daily_folder / "test.json"
    agent._write_json(out_path, {"key": "value", "num": 42})
    import json
    data = json.loads(out_path.read_text())
    assert data["key"] == "value"
    assert data["num"] == 42
