"""
StrategistAgent — 每次 Pipeline 的强制第一步。

职责：
  1. 读取 user_brief 和 today_note
  2. 读取 LessonMemory 正向/负向经验信号
  3. 读取 AlternativePlanMemory 历史备选方案
  4. 判断冷/热启动
  5. 辩论前执行一次联网搜索（A/B 同源摘要，分别注入各自 prompt）
  6. 通过对抗辩论生成策略建议文档
  7. 将备选方案归档到 AlternativePlanMemory

Debate 组成（两方对抗）：
  Strategist A         ：通用策略师
  Strategist B         ：通用策略师
  StrategyModerator    ：综合裁定，选出唯一执行方案
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient
from src.orchestrator.adversarial_debate import DebateAgent, adversarial_debate
from src.orchestrator.alternative_plan_memory import AlternativePlanMemory
from src.orchestrator.lesson_memory import LessonMemory
from src.skills.search import search_for_agent

logger = logging.getLogger(__name__)

# ── Moderator System Prompt ────────────────────────────────────────────────────

_MODERATOR_SYSTEM = """你是一名营销策略总监（StrategyModerator）。
你的职责：综合对抗辩论的全部讨论记录，选出最优策略方向，输出一份简洁可执行的策略建议文档，供今日营销策划使用。

文档格式必须严格如下：

# 策略建议 - {date}

## 产品定位
（1-2句话，本产品的核心价值主张）

## 今日特殊要求
（如无特殊要求，写"无"）

## 推荐内容策略（选 1-2 个方向）
### 方向一：{名称}
- 核心思路：
- 叙事切入点：
- 建议调性：

### 方向二：{名称}（可选）
- 核心思路：
- 叙事切入点：
- 建议调性：

## 成功经验参考
（列出已验证有效的内容特征，如无则写"暂无历史数据"）

## 需要避免的陷阱
（列出已知的违规规律和失败模式，如无则写"暂无历史数据"）

保持文档简洁（500字以内），确保 Planner 能直接使用这份建议。"""

# ── Agent Role Descriptions ────────────────────────────────────────────────────

_STRATEGIST_ROLE = (
    "独立营销策略师（Strategist）。"
    "你需要输出结构化、可执行、可验证的营销策略。"
    "在辩论中保持对抗性思维，优先暴露假设漏洞和执行风险。"
)

# Single web search per run: A/B share role + product summary, so one query avoids duplicate API use.
_SHARED_WEB_SEARCH_HEADER = (
    "## 联网搜索结果（本 run 仅执行一次检索；以下内容只注入你方 prompt，对方在各自调用中不可见）\n\n"
)


class StrategistAgent(BaseAgent):
    """
    Strategist Agent：每次 Pipeline 强制第一步。
    通过两方对抗辩论生成策略建议文档，并归档备选方案。
    """

    def __init__(
        self,
        strategist_a_client: BaseLLMClient,
        strategist_b_client: BaseLLMClient,
        moderator_client: BaseLLMClient,
        platform: str = "xiaohongshu",
        round1_temperature: float = 1.0,
        discussion_temperature: float = 0.0,
    ):
        super().__init__(
            name="Strategist",
            llm_client=moderator_client,
            role_description="策略反思团队，每次 Pipeline 第一步，生成内容策略建议",
        )
        self._strategist_a = strategist_a_client
        self._strategist_b = strategist_b_client
        self._platform = platform
        self._round1_temperature = round1_temperature
        self._discussion_temperature = discussion_temperature

    async def run(self, context: AgentContext) -> AgentOutput:
        output_path = context.strategy_path
        attempt_dir = context.stage_attempt_dir("strategy")
        date_str = context.run_date.strftime("%Y-%m-%d")

        # ── 读取 LessonMemory ─────────────────────────────────────────────────
        lesson_memory = LessonMemory(context.campaign_root, self._platform)
        all_lessons = lesson_memory.load()
        positive_lessons = [l for l in all_lessons if l.get("signal") == "positive"]
        negative_lessons = [
            l for l in all_lessons
            if l.get("signal") == "negative" or "signal" not in l
        ]
        is_cold_start = len(positive_lessons) == 0
        start_mode = "冷启动" if is_cold_start else f"热启动（{len(positive_lessons)} 个成功经验）"

        # ── 读取 AlternativePlanMemory ────────────────────────────────────────
        alt_memory = AlternativePlanMemory(context.campaign_root, self._platform, "strategist")

        # ── 构建共享上下文 ─────────────────────────────────────────────────────
        shared_context = self._build_context(
            date_str=date_str,
            user_brief=context.user_brief,
            today_note=context.user_note,
            positive_lessons=positive_lessons,
            negative_lessons=negative_lessons,
            is_cold_start=is_cold_start,
            campaign_root=context.campaign_root,
            alt_memory=alt_memory,
        )

        # ── 搜索摘要输入（不读取 asset_library/index.json）────────────────────
        # Strategist 阶段仅使用用户输入与已整理上下文，不注入资产库索引信息。
        product_summary = context.user_brief.strip()
        if not product_summary:
            product_summary = shared_context[:4000]

        # ── 单次联网搜索（A/B 角色与摘要相同，重复检索浪费资源；结果分别注入两方专属上下文）──
        logger.info("[Strategist] Running pre-debate web search (once per run, shared by both strategists)...")
        shared_search = await search_for_agent(
            "Strategist", _STRATEGIST_ROLE, product_summary, self._platform
        )
        agent_contexts: dict[str, str] = {}
        if shared_search:
            block = _SHARED_WEB_SEARCH_HEADER + shared_search
            agent_contexts["Strategist A"] = block
            agent_contexts["Strategist B"] = block

        # ── Per-attempt web search archive (single file; same source for both agents) ─
        self._write_output(
            attempt_dir / "web_search_shared.md",
            shared_search.strip() if shared_search else "(no search results)\n",
        )

        # ── Debate Agents ─────────────────────────────────────────────────────
        strategist_a = DebateAgent("Strategist A", _STRATEGIST_ROLE, self._strategist_a)
        strategist_b = DebateAgent("Strategist B", _STRATEGIST_ROLE, self._strategist_b)
        moderator_system = _MODERATOR_SYSTEM.replace("{date}", date_str)

        # ── 对抗辩论（日志写入当前 attempt 子目录，便于多次测试留档）───────────────
        log_path = attempt_dir / "strategy_debate.md"

        result = await adversarial_debate(
            agents=[strategist_a, strategist_b],
            moderator_client=self.llm_client,
            context=shared_context,
            moderator_system=moderator_system,
            max_extra_rounds=1,
            log_path=log_path,
            round1_temperature=self._round1_temperature,
            discussion_temperature=self._discussion_temperature,
            agent_contexts=agent_contexts,
        )

        # ── Prepend human-visible run metadata to debate log (full detail in run_config.json)
        _debate_preamble = (
            "<!--\n"
            f"Strategist run metadata | full JSON: run_config.json in this attempt folder\n"
            f"attempt_id: {context.attempt_id}\n"
            f"date: {date_str}\n"
            f"round1_temperature: {self._round1_temperature}\n"
            f"discussion_temperature: {self._discussion_temperature}\n"
            f"moderator_temperature_in_debate: 0.0\n"
            f"models: strategist_a={self._strategist_a.model_name()}; "
            f"strategist_b={self._strategist_b.model_name()}; "
            f"moderator={self.llm_client.model_name()}\n"
            f"debate_rounds_conducted: {result.rounds_conducted}\n"
            "web_search_file: web_search_shared.md\n"
            "alt_plans: alt_plans_session.json; "
            f"memory/alt_plans_{self._platform}_strategist_{context.attempt_id}.json\n"
            "-->\n\n"
        )
        log_path.write_text(_debate_preamble + log_path.read_text(encoding="utf-8"), encoding="utf-8")

        # ── 归档备选方案（全局 JSON 带 attempt_id；memory 下另有按 attempt 分文件）──
        alt_session = alt_memory.save_session(
            date_str,
            result.selected_plan,
            result.alternative_plans,
            attempt_id=context.attempt_id,
            debate_rounds_conducted=result.rounds_conducted,
        )
        self._write_json(attempt_dir / "alt_plans_session.json", alt_session)

        # ── 写入输出（先写入 attempt，再同步到当日 canonical 路径）───────────────
        suggestion_attempt = attempt_dir / "strategy_suggestion.md"
        self._write_output(suggestion_attempt, result.selected_plan_full_text)
        self._copy_attempt_file(suggestion_attempt, output_path)
        self._copy_attempt_file(suggestion_attempt, context.strategy_latest_mirror_path)
        debate_canonical = context.daily_folder / "strategy" / "strategy_debate.md"
        self._copy_attempt_file(log_path, debate_canonical)

        memory_attempt_file = (
            context.campaign_root
            / "memory"
            / f"alt_plans_{self._platform}_strategist_{context.attempt_id}.json"
        )
        run_config = {
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "date": date_str,
            "attempt_id": context.attempt_id,
            "platform": self._platform,
            "temperatures": {
                "round1": self._round1_temperature,
                "discussion": self._discussion_temperature,
                "moderator_in_debate": 0.0,
            },
            "models": {
                "strategist_a": self._strategist_a.model_name(),
                "strategist_b": self._strategist_b.model_name(),
                "moderator": self.llm_client.model_name(),
            },
            "debate": {
                "max_extra_rounds": 1,
                "rounds_conducted": result.rounds_conducted,
            },
            "artifacts_relative_to_campaign_root": {
                "strategy_suggestion": str(suggestion_attempt.relative_to(context.campaign_root)),
                "strategy_debate": str(log_path.relative_to(context.campaign_root)),
                "web_search_shared": str(
                    (attempt_dir / "web_search_shared.md").relative_to(context.campaign_root)
                ),
                "alt_plans_session": str(
                    (attempt_dir / "alt_plans_session.json").relative_to(context.campaign_root)
                ),
                "global_alt_plans": str(
                    (context.campaign_root / "memory" / f"alt_plans_{self._platform}_strategist.json")
                    .relative_to(context.campaign_root)
                ),
                "alt_plans_by_attempt": str(memory_attempt_file.relative_to(context.campaign_root)),
            },
        }
        self._write_json(attempt_dir / "run_config.json", run_config)

        summary = (
            f"{start_mode} | 策略建议已生成（{len(result.selected_plan_full_text)} 字）"
            f" | 备选归档 {len(result.alternative_plans)} 条"
            f" | 辩论轮次 {result.rounds_conducted}"
        )
        return AgentOutput(
            output_path=output_path,
            summary=summary,
            data={
                "start_mode": start_mode,
                "is_cold_start": is_cold_start,
                "rounds_conducted": result.rounds_conducted,
                "selected_plan": {
                    "source_agent": result.selected_plan.source_agent,
                    "plan_label": result.selected_plan.source_plan_label,
                    "core_claim": result.selected_plan.core_claim,
                },
                "alternative_plans_archived": len(result.alternative_plans),
                "search_used": {"shared_web_search": bool(shared_search)},
                "attempt_artifacts": [
                    str(attempt_dir / "run_config.json"),
                    str(attempt_dir / "web_search_shared.md"),
                    str(attempt_dir / "alt_plans_session.json"),
                    str(attempt_dir / "strategy_suggestion.md"),
                    str(attempt_dir / "strategy_debate.md"),
                ],
                "alt_plans_memory_by_attempt": str(memory_attempt_file),
            },
        )

    def _build_context(
        self,
        date_str: str,
        user_brief: str,
        today_note: str,
        positive_lessons: list[dict],
        negative_lessons: list[dict],
        is_cold_start: bool,
        campaign_root: Path,
        alt_memory: AlternativePlanMemory,
    ) -> str:
        parts = [
            f"# 今日策略任务 — {date_str}\n"
            f"启动模式：{'冷启动（首次运营）' if is_cold_start else '热启动（有历史数据）'}"
        ]
        if user_brief:
            parts.append(f"## 产品需求描述（user_brief）\n{user_brief}")
        if today_note:
            parts.append(f"## 今日特殊要求（today_note）\n{today_note}")

        if positive_lessons:
            lines = ["## 历史成功内容（已被用户接受）"]
            for l in positive_lessons[-5:]:
                lines.append(f"- [{l.get('date','')}] {l.get('theme') or l.get('title','')}: {l.get('note','')}")
            parts.append("\n".join(lines))
        else:
            parts.append("## 历史成功内容\n暂无（首次运营，参考同品类最佳实践）")

        if negative_lessons:
            lines = ["## 已知违规/失败规律"]
            for l in negative_lessons[-5:]:
                source_label = "用户拒绝" if l.get("source") == "user_rejection" else "审核失败"
                item_id = l.get("checklist_item", l.get("id", ""))
                lines.append(f"- [{source_label}] [{item_id}] {l.get('rule','')}")
            parts.append("\n".join(lines))
        else:
            parts.append("## 已知违规/失败规律\n暂无（首次运营）")

        if is_cold_start:
            parts.append(
                "## 冷启动参考原则\n"
                "- 首帖以「真实体验」为主，避免过度商业感\n"
                "- 封面图要有强视觉冲击，文字大且清晰\n"
                "- 前几帖聚焦 1-2 个核心功能，不要贪多\n"
                "- 混合大流量话题(100w+)与垂直话题(10-50w)，比例 3:3\n"
                "- 发布时间：工作日 18:00-22:00，周末 10:00-12:00 或 20:00-22:00"
            )

        alt_context = alt_memory.inject_context(n=3)
        if alt_context:
            parts.append(alt_context)

        return "\n\n".join(parts)
