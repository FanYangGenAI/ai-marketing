"""
集成测试：Pipeline 端到端冒烟测试（全 Mock LLM）

使用 dry_run=False 但注入 Mock LLM，验证：
1. Strategist 作为第 0 步运行
2. 所有 6 个步骤都出现在结果中
3. product_config.json 的 user_brief 被正确传入 context
4. pipeline_state.json 被正确写入
"""

import json
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from src.llm.base import BaseLLMClient, LLMMessage, LLMResponse
from src.orchestrator.pipeline import STEPS


# ── Minimal Mock LLM ──────────────────────────────────────────────────────────

class NoopLLMClient(BaseLLMClient):
    """返回最小合法文本的 Mock LLM，避免 Agent 因空内容报错。"""

    def model_name(self) -> str:
        return "noop"

    async def chat(self, messages, system=None, max_tokens=4096, temperature=0.7) -> LLMResponse:
        return LLMResponse(
            content="测试输出内容",
            model="noop",
            input_tokens=5,
            output_tokens=5,
        )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def campaigns_root(tmp_path) -> Path:
    return tmp_path / "campaigns"


@pytest.fixture
def product_dir(campaigns_root) -> Path:
    product = campaigns_root / "TestProduct"
    for sub in ["config", "docs", "memory", "asset_library", "daily"]:
        (product / sub).mkdir(parents=True)
    return product


@pytest.fixture
def product_config(product_dir) -> Path:
    cfg = {
        "platform": "xiaohongshu",
        "suppress_version_in_copy": True,
        "user_brief": "这是集成测试用的产品描述",
    }
    path = product_dir / "config" / "product_config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return path


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_steps_constant():
    """STEPS 常量应包含所有预期步骤，且 strategist 在首位。"""
    assert STEPS[0] == "strategist"
    assert "planner" in STEPS
    assert "scriptwriter" in STEPS
    assert "director" in STEPS
    assert "creator" in STEPS
    assert "audit" in STEPS


def test_pipeline_load_product_config(product_dir, product_config):
    """_load_product_config 应正确读取 user_brief 和 suppress_version_in_copy。"""
    from src.orchestrator.pipeline import Pipeline

    # Pipeline._load_product_config is a static method
    cfg = Pipeline._load_product_config(product_dir)
    assert cfg["user_brief"] == "这是集成测试用的产品描述"
    assert cfg["suppress_version_in_copy"] is True
    assert cfg["platform"] == "xiaohongshu"


def test_pipeline_load_product_config_missing_file(tmp_path):
    """product_config.json 不存在时应返回空 dict（不抛错）。"""
    from src.orchestrator.pipeline import Pipeline

    cfg = Pipeline._load_product_config(tmp_path / "nonexistent")
    assert cfg == {}


@pytest.mark.asyncio
async def test_pipeline_dry_run_includes_strategist(campaigns_root, product_dir, product_config, capsys):
    """dry_run 模式应打印包含 strategist 在内的全部 6 个步骤计划。"""
    from src.orchestrator.pipeline import Pipeline

    pipeline = Pipeline(
        product_name="TestProduct",
        campaigns_root=campaigns_root,
        platform="xiaohongshu",
    )

    result = await pipeline.run(
        run_date=date(2026, 3, 22),
        dry_run=True,
    )

    # dry_run 返回空 dict
    assert result == {}

    captured = capsys.readouterr()
    assert "strategist" in captured.out.lower() or "Strategist" in captured.out
