"""单元测试：CampaignMemory"""

from datetime import date
from pathlib import Path

import pytest

from src.agents.planner.campaign_memory import CampaignMemory


@pytest.fixture
def campaign_root(tmp_path) -> Path:
    return tmp_path / "campaigns" / "TestProduct"


def _write_plan(campaign_root: Path, date_str: str, content: str) -> None:
    p = campaign_root / "daily" / date_str / "plan" / "daily_marketing_plan.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_no_history_cold_start(campaign_root):
    memory = CampaignMemory(campaign_root)
    summary = memory.build_summary(date(2026, 3, 17))
    assert "冷启动" in summary or "暂无" in summary


def test_single_day_history(campaign_root):
    _write_plan(campaign_root, "2026-03-16", "## 今日主题\n产品功能展示，核心卖点介绍")
    memory = CampaignMemory(campaign_root)
    summary = memory.build_summary(date(2026, 3, 17))
    assert "2026-03-16" in summary
    assert "产品功能展示" in summary


def test_multiple_days_history(campaign_root):
    for i, topic in enumerate(["功能演示", "用户案例", "价格优惠"], start=1):
        _write_plan(campaign_root, f"2026-03-{16 - i + 1:02d}", f"## 今日主题\n{topic}")
    memory = CampaignMemory(campaign_root, lookback_days=30)
    summary = memory.build_summary(date(2026, 3, 17))
    # 应包含近期记录
    assert "2026-03" in summary


def test_lookback_days_limit(campaign_root):
    # 写一条 60 天前的记录，不应被读取
    _write_plan(campaign_root, "2026-01-01", "## 今日主题\n旧内容，不应出现")
    memory = CampaignMemory(campaign_root, lookback_days=30)
    summary = memory.build_summary(date(2026, 3, 17))
    assert "旧内容" not in summary


def test_plan_without_theme_section(campaign_root):
    """没有 ## 今日主题 的计划文件，应回退到前200字。"""
    _write_plan(campaign_root, "2026-03-16", "这是一份没有标准章节的计划，直接写了内容。")
    memory = CampaignMemory(campaign_root)
    summary = memory.build_summary(date(2026, 3, 17))
    assert "2026-03-16" in summary
