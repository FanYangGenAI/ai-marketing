"""单元测试：StrategistAgent"""

import pytest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base import AgentContext, AgentOutput
from src.llm.base import BaseLLMClient, LLMMessage, LLMResponse


# ── Mock LLM Client ───────────────────────────────────────────────────────────

class MockLLMClient(BaseLLMClient):
    def __init__(self, response_text: str = "## 策略建议\n测试策略内容"):
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def campaign_root(tmp_path) -> Path:
    root = tmp_path / "campaigns" / "TestProduct"
    for subdir in ["memory", "daily", "config"]:
        (root / subdir).mkdir(parents=True)
    return root


@pytest.fixture
def context(campaign_root) -> AgentContext:
    daily = campaign_root / "daily" / "2026-03-22"
    daily.mkdir(parents=True, exist_ok=True)
    return AgentContext(
        campaign_root=campaign_root,
        daily_folder=daily,
        run_date=date(2026, 3, 22),
        product_name="TestProduct",
        user_brief="这是一款 AI 辅助工具，目标用户是内容创作者",
        user_note="今天重点推多语言功能",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_strategist_cold_start_writes_strategy_file(campaign_root, context):
    """冷启动（无 LessonMemory 正向信号）时，Strategist 应输出 strategy_suggestion.md。"""
    from src.agents.strategist.strategist import StrategistAgent

    mock_client = MockLLMClient("# 策略建议 - 2026-03-22\n\n## 产品定位\n测试内容")
    agent = StrategistAgent(
        gemini_client=mock_client,
        openai_client=mock_client,
        claude_client=mock_client,
        platform="xiaohongshu",
    )

    output = await agent.run(context)

    # strategy_suggestion.md 必须被写入
    assert context.strategy_path.exists()
    content = context.strategy_path.read_text(encoding="utf-8")
    assert len(content) > 0

    # AgentOutput 元数据检查
    assert output.output_path == context.strategy_path
    assert context.strategy_latest_mirror_path.exists()
    assert context.strategy_latest_mirror_path.read_text(encoding="utf-8") == content
    assert output.data["is_cold_start"] is True
    assert "冷启动" in output.data["start_mode"]


@pytest.mark.asyncio
async def test_strategist_hot_start_detected(campaign_root, context):
    """存在正向 LessonMemory 信号时，Strategist 应检测为热启动。"""
    import json

    # 写入正向 LessonMemory
    memory_path = campaign_root / "memory" / "lessons_xiaohongshu.json"
    memory_data = {
        "platform": "xiaohongshu",
        "lessons": [
            {
                "id": "lesson_001",
                "signal": "positive",
                "source": "user_acceptance",
                "date": "2026-03-20",
                "title": "测试标题",
                "theme": "产品体验",
                "note": "用户接受",
                "category": "content",
            }
        ],
    }
    memory_path.write_text(json.dumps(memory_data, ensure_ascii=False), encoding="utf-8")

    from src.agents.strategist.strategist import StrategistAgent

    mock_client = MockLLMClient("# 策略建议 - 2026-03-22\n热启动策略")
    agent = StrategistAgent(
        gemini_client=mock_client,
        openai_client=mock_client,
        claude_client=mock_client,
    )

    output = await agent.run(context)

    assert output.data["is_cold_start"] is False
    assert "热启动" in output.data["start_mode"]
    assert "1" in output.data["start_mode"]


@pytest.mark.asyncio
async def test_strategist_reads_user_brief_from_context(campaign_root, context):
    """Strategist 应从 context.user_brief 读取产品描述，而非 context.extra。"""
    from src.agents.strategist.strategist import StrategistAgent

    received_contexts = []

    class CapturingClient(BaseLLMClient):
        def model_name(self):
            return "capturing"

        async def chat(self, messages, system=None, **kwargs):
            # Capture the first user message content for inspection
            for m in messages:
                if hasattr(m, 'role') and m.role == 'user':
                    received_contexts.append(m.content)
            return LLMResponse(content="策略内容", model="capturing", input_tokens=5, output_tokens=5)

    client = CapturingClient()
    agent = StrategistAgent(
        gemini_client=client,
        openai_client=client,
        claude_client=client,
    )

    await agent.run(context)

    # user_brief 内容应出现在传给 LLM 的消息中
    all_content = " ".join(received_contexts)
    assert "AI 辅助工具" in all_content or "内容创作者" in all_content


@pytest.mark.asyncio
async def test_strategist_writes_debate_log(campaign_root, context):
    """Strategist 应写入 daily/.../strategy/strategy_debate.md 辩论日志。"""
    from src.agents.strategist.strategist import StrategistAgent

    mock_client = MockLLMClient("策略内容")
    agent = StrategistAgent(
        gemini_client=mock_client,
        openai_client=mock_client,
        claude_client=mock_client,
    )

    await agent.run(context)

    log_path = context.daily_folder / "strategy" / "strategy_debate.md"
    assert log_path.exists()
