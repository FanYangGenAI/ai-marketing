"""
StrategistAgent — 每次 Pipeline 的强制第一步。

职责：
  1. 读取 user_brief（产品级永久需求）和 today_note（本次特殊要求）
  2. 读取 LessonMemory 正向/负向经验信号
  3. 判断冷/热启动：LessonMemory 中有正向经验 → 热启动，否则 → 冷启动
  4. 通过 Debate→Synthesize 生成策略建议文档
  5. 输出到 daily/{date}/strategy/strategy_suggestion.md（当日专属）；
     并镜像到 campaigns/{product}/strategy_suggestion.md（全局「最新一份」）

Debate 组成：
  DataAnalyst       ：分析历史经验数据、市场规律（模型见 llm_config strategy_analyst）
  StrategyReviewer  ：创意策略方向建议（strategy_reviewer）
  StrategyModerator   ：综合输出策略建议（moderator 或 strategy_moderator）
"""

from __future__ import annotations

from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient
from src.cold_start.retrieval import load_product_context_for_agents
from src.orchestrator.debate import DebateAgent, debate_and_synthesize
from src.orchestrator.lesson_memory import LessonMemory
from src.orchestrator.llm_temperatures import DEBATE_STRATEGIST_PLANNER


# ── System Prompts ─────────────────────────────────────────────────────────────

_ANALYST_SYSTEM = """你是一名内容策略数据分析师（DataAnalyst）。
你的职责：分析提供的历史运营数据和市场经验，识别规律、总结发现。
请输出一份「数据洞察报告」，包含：
- 历史成功内容的共同特征（如有）
- 已知的违规/失败规律（如有）
- 同品类市场上的内容规律建议
分析要具体，用数据和案例说话，避免空泛。"""

_REVIEWER_SYSTEM = """你是一名创意内容策略顾问（StrategyReviewer）。
你的职责：基于产品信息和数据分析，提出差异化的内容策略方向。
请输出「策略方向建议」，包含：
- 3-5个具体的内容策略方向（含理由）
- 推荐的内容调性和叙事风格
- 建议本次聚焦的核心卖点
建议要有创意，同时考虑平台特性和目标用户。"""

_MODERATOR_SYSTEM = """你是一名营销策略总监（StrategyModerator）。
你的职责：综合数据分析和策略建议，输出一份简洁可执行的策略建议文档，供今日营销策划使用。

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


class StrategistAgent(BaseAgent):
    """
    Strategist Agent：每次 Pipeline 强制第一步。
    通过多角色讨论，生成本次营销的策略建议文档。
    """

    def __init__(
        self,
        analyst_client: BaseLLMClient,
        reviewer_client: BaseLLMClient,
        moderator_client: BaseLLMClient,
        platform: str = "xiaohongshu",
    ):
        super().__init__(
            name="Strategist",
            llm_client=moderator_client,
            role_description="策略反思团队，每次 Pipeline 第一步，生成内容策略建议",
        )
        self._analyst = analyst_client
        self._reviewer = reviewer_client
        self._platform = platform

    async def run(self, context: AgentContext) -> AgentOutput:
        output_path = context.strategy_path
        attempt_dir = context.stage_attempt_dir("strategy")
        date_str = context.run_date.strftime("%Y-%m-%d")

        # ── 读取输入 ──────────────────────────────────────────────────────────
        user_brief = context.user_brief
        today_note = context.user_note  # 本次运行的特殊要求

        # ── 读取 LessonMemory ─────────────────────────────────────────────────
        lesson_memory = LessonMemory(context.campaign_root, self._platform)
        all_lessons = lesson_memory.load()

        positive_lessons = [l for l in all_lessons if l.get("signal") == "positive"]
        negative_lessons = [l for l in all_lessons if l.get("signal") == "negative"
                            or "signal" not in l]  # 兼容旧格式（无signal字段默认负向）

        is_cold_start = len(positive_lessons) == 0
        start_mode = "冷启动" if is_cold_start else f"热启动（{len(positive_lessons)} 个成功经验）"

        # ── 构建共享上下文 ─────────────────────────────────────────────────────
        shared_context = self._build_context(
            date_str=date_str,
            user_brief=user_brief,
            today_note=today_note,
            positive_lessons=positive_lessons,
            negative_lessons=negative_lessons,
            is_cold_start=is_cold_start,
            campaign_root=context.campaign_root,
        )

        # ── Debate Agents ─────────────────────────────────────────────────────
        analyst = DebateAgent("DataAnalyst（数据分析）", _ANALYST_SYSTEM, self._analyst)
        reviewer = DebateAgent("StrategyReviewer（策略建议）", _REVIEWER_SYSTEM, self._reviewer)

        moderator_system = _MODERATOR_SYSTEM.replace("{date}", date_str)

        # ── Debate → Synthesize ───────────────────────────────────────────────
        # Debate log lives under the same daily folder (no date in filename)
        log_path = context.daily_folder / "strategy" / "strategy_debate.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        result = await debate_and_synthesize(
            agents=[analyst, reviewer],
            moderator_client=self.llm_client,
            context=shared_context,
            moderator_system=moderator_system,
            max_rounds=2,  # 策略讨论 2 轮足够
            log_path=log_path,
            temperature=DEBATE_STRATEGIST_PLANNER,
        )

        # ── 写入输出 ──────────────────────────────────────────────────────────
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_output(output_path, result.final_output)
        # Mirror at campaign root for a stable "latest strategy" path
        self._write_output(context.strategy_latest_mirror_path, result.final_output)
        self._copy_attempt_file(output_path, attempt_dir / "strategy_suggestion.md")
        self._copy_attempt_file(log_path, attempt_dir / "strategy_debate.md")

        summary = f"{start_mode} | 策略建议已生成（{len(result.final_output)} 字）"
        return AgentOutput(
            output_path=output_path,
            summary=summary,
            data={
                "start_mode": start_mode,
                "is_cold_start": is_cold_start,
                "rounds": result.rounds,
                "attempt_artifacts": [
                    str(attempt_dir / "strategy_suggestion.md"),
                    str(attempt_dir / "strategy_debate.md"),
                ],
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
    ) -> str:
        parts = [f"# 今日策略任务 — {date_str}\n启动模式：{'冷启动（首次运营）' if is_cold_start else '热启动（有历史数据）'}"]

        if user_brief:
            parts.append(f"## 产品需求描述（user_brief）\n{user_brief}")

        if today_note:
            parts.append(f"## 今日特殊要求（today_note）\n{today_note}")

        # 正向经验
        if positive_lessons:
            lines = ["## 历史成功内容（已被用户接受）"]
            for lesson in positive_lessons[-5:]:  # 最近 5 条
                title = lesson.get("title", "")
                theme = lesson.get("theme", "")
                note = lesson.get("note", "")
                date_val = lesson.get("date", "")
                lines.append(f"- [{date_val}] {theme or title}: {note}")
            parts.append("\n".join(lines))
        else:
            parts.append("## 历史成功内容\n暂无（首次运营，参考同品类最佳实践）")

        # 负向经验
        if negative_lessons:
            lines = ["## 已知违规/失败规律"]
            for lesson in negative_lessons[-5:]:  # 最近 5 条
                rule = lesson.get("rule", "")
                item_id = lesson.get("checklist_item", lesson.get("id", ""))
                source = lesson.get("source", "audit_failure")
                source_label = "用户拒绝" if source == "user_rejection" else "审核失败"
                lines.append(f"- [{source_label}] [{item_id}] {rule}")
            parts.append("\n".join(lines))
        else:
            parts.append("## 已知违规/失败规律\n暂无（首次运营）")

        # 冷启动补充
        if is_cold_start:
            parts.append(
                "## 冷启动参考原则\n"
                "- 首帖以「真实体验」为主，避免过度商业感\n"
                "- 封面图要有强视觉冲击，文字大且清晰\n"
                "- 前几帖聚焦 1-2 个核心功能，不要贪多\n"
                "- 混合大流量话题(100w+)与垂直话题(10-50w)，比例 3:3\n"
                "- 发布时间：工作日 18:00-22:00，周末 10:00-12:00 或 20:00-22:00"
            )

        product_ctx = load_product_context_for_agents(campaign_root)
        if product_ctx.strip():
            parts.append(product_ctx)

        return "\n\n".join(parts)
