"""
CampaignMemory — 跨日记忆读取器。

扫描最近 N 天的每日文件夹，汇总「已覆盖话题」，
注入 Planner 上下文，防止选题重复。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path


class CampaignMemory:
    def __init__(self, campaign_root: Path, lookback_days: int = 30):
        self.campaign_root = campaign_root
        self.lookback_days = lookback_days

    def build_summary(self, run_date: date) -> str:
        """
        扫描最近 lookback_days 天的 plan/ 目录，
        返回一段「已覆盖话题摘要」文本，供 Planner 作为上下文输入。
        """
        daily_root = self.campaign_root / "daily"
        if not daily_root.exists():
            return "（暂无历史投放记录，本次为冷启动）"

        entries: list[tuple[date, str]] = []

        for i in range(1, self.lookback_days + 1):
            target_date = run_date - timedelta(days=i)
            date_str = target_date.strftime("%Y-%m-%d")
            plan_file = daily_root / date_str / "plan" / "daily_marketing_plan.md"

            if not plan_file.exists():
                continue

            snippet = self._extract_topic_snippet(plan_file.read_text(encoding="utf-8"))
            if snippet:
                entries.append((target_date, snippet))

        if not entries:
            return "（最近 30 天暂无有效投放记录）"

        lines = [f"## 近期已投放内容摘要（供参考，请避免重复）\n"]
        for d, snippet in entries:
            lines.append(f"**{d.strftime('%Y-%m-%d')}**：{snippet}")

        return "\n".join(lines)

    @staticmethod
    def _extract_topic_snippet(plan_text: str) -> str:
        """
        从 daily_marketing_plan.md 中提取核心话题/方向摘要。
        优先提取 "## 今日主题" 或 "## 核心方向" 段落的首行，
        回退到文件前 200 字。
        """
        # 尝试匹配常见的主题 section
        pattern = re.compile(
            r"##\s*(?:今日主题|核心方向|主题|方向)[^\n]*\n+(.+?)(?:\n##|\Z)",
            re.DOTALL,
        )
        m = pattern.search(plan_text)
        if m:
            text = m.group(1).strip()
            # 取前两行
            first_lines = "\n".join(text.splitlines()[:2])
            return first_lines[:150]

        # 回退：文件前 200 字（去掉 markdown 标题符号）
        clean = re.sub(r"[#*_`>]", "", plan_text)
        return clean.strip()[:150].replace("\n", " ")
