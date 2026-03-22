"""
Planner Agent — 每日营销策划团队。

角色构成（Debate→Synthesize）：
  PlannerA  (Gemini)        ：热点搜索 + 趋势分析
  PlannerB  (Claude Opus)   ：产品亮点深挖
  PlannerC  (GPT-4o)        ：用户视角洞察
  Moderator (Claude Opus)   ：综合收敛，输出计划书

输出：{daily_folder}/plan/daily_marketing_plan.md
"""

from __future__ import annotations

from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.agents.planner.campaign_memory import CampaignMemory
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.debate import DebateAgent, debate_and_synthesize


# ── 系统 Prompt 常量 ──────────────────────────────────────────────────────────

_PLANNER_A_SYSTEM = """你是一名内容营销趋势分析师（PlannerA）。
你的职责：通过搜索工具获取今日热点，分析行业趋势、竞品动态、社会热点，
找出与产品相关的最佳内容切入点。
请输出一份简洁的「热点洞察报告」，重点列出 3-5 个可用的内容方向，说明每个方向的热点来源和可借势的理由。"""

_PLANNER_B_SYSTEM = """你是一名产品深度分析师（PlannerB）。
你的职责：精读产品 PRD，挖掘最具传播力的功能亮点和差异化卖点。
请输出一份「产品亮点清单」，重点列出 3-5 个最适合在小红书等社交平台传播的产品特性，
说明每个亮点的目标人群和传播角度。"""

_PLANNER_C_SYSTEM = """你是一名用户洞察专家（PlannerC）。
你的职责：从目标用户的真实需求和情感出发，评估哪个内容方向最有共鸣感。
请输出一份「用户视角洞察」，重点分析目标用户的痛点、期望和内容消费习惯，
推荐 3-5 个最容易引发共鸣的内容角度。"""

_MODERATOR_SYSTEM = """你是一名营销内容总策划（PlannerModerator）。
你的职责：综合趋势分析师、产品分析师、用户洞察专家三方的观点，
制定一份完整、可执行的每日内容营销计划书。

计划书必须包含以下章节：
# 每日营销计划 - {date}

## 今日主题
（1-2句话，概括今日内容核心）

## 核心方向（选 1-2 个）
（每个方向包含：方向名称、切入角度、目标人群、借势热点）

## 内容形式建议
（图文/短视频/图片轮播；图片数量；视觉风格关键词）

## 文案方向
（标题钩子词建议；正文情绪基调；推荐话题标签 5-8 个）

## 禁止事项
（今日需刻意避开的话题/词语，包括与历史内容重复的方向）

请确保计划书具体、可执行，避免空泛的策略描述。"""


class PlannerAgent(BaseAgent):
    """
    Planner Agent：通过三个子 Agent Debate→Synthesize，输出每日营销计划书。
    """

    def __init__(
        self,
        gemini_client: BaseLLMClient,    # PlannerA
        claude_client: BaseLLMClient,    # PlannerB + Moderator
        openai_client: BaseLLMClient,    # PlannerC
    ):
        # 基类 llm_client 设为 Moderator（Claude）
        super().__init__(
            name="Planner",
            llm_client=claude_client,
            role_description="每日营销策划团队，通过多角色讨论制定内容方向",
        )
        self._gemini = gemini_client
        self._openai = openai_client
        self._memory = CampaignMemory

    async def run(self, context: AgentContext) -> AgentOutput:
        output_path = context.subdir("plan") / "daily_marketing_plan.md"
        log_path = context.subdir("plan") / "debate_raw.md"

        # ── 读取上下文资料 ────────────────────────────────────────────────────
        prd_text = self._read_optional(context.prd_path)
        strategy_text = self._read_optional(context.strategy_path)
        memory_summary = CampaignMemory(context.campaign_root).build_summary(context.run_date)
        date_str = context.run_date.strftime("%Y-%m-%d")

        # ── 构建共享背景上下文（所有 Agent 都会读到）────────────────────────────
        shared_context = self._build_shared_context(
            date_str, prd_text, strategy_text, memory_summary, context.user_note
        )

        # ── 构建 Debate Agents ────────────────────────────────────────────────
        planner_a = DebateAgent(
            name="PlannerA（趋势分析）",
            role_description=_PLANNER_A_SYSTEM,
            client=self._gemini,
        )
        planner_b = DebateAgent(
            name="PlannerB（产品视角）",
            role_description=_PLANNER_B_SYSTEM,
            client=self.llm_client,
        )
        planner_c = DebateAgent(
            name="PlannerC（用户视角）",
            role_description=_PLANNER_C_SYSTEM,
            client=self._openai,
        )

        moderator_system = _MODERATOR_SYSTEM.replace("{date}", date_str)

        # ── 执行 Debate→Synthesize ───────────────────────────────────────────
        result = await debate_and_synthesize(
            agents=[planner_a, planner_b, planner_c],
            moderator_client=self.llm_client,
            context=shared_context,
            moderator_system=moderator_system,
            max_rounds=3,
            log_path=log_path,
        )

        # ── 写入输出文件 ──────────────────────────────────────────────────────
        self._write_output(output_path, result.final_output)

        # 提取今日主题作为摘要
        summary = self._extract_theme(result.final_output, date_str)

        # 判断是否提前收敛（Round 2 开始存在 agree 信息）
        reached_agreement = (
            result.rounds > 1
            and len(result.opinions) > 1
            and all(op.agree for op in result.opinions[-1])
        )

        return AgentOutput(
            output_path=output_path,
            summary=summary,
            data={"rounds": result.rounds, "agreement": reached_agreement},
        )

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    def _build_shared_context(
        self,
        date_str: str,
        prd_text: str,
        strategy_text: str,
        memory_summary: str,
        user_note: str,
    ) -> str:
        parts = [f"# 今日策划任务 — {date_str}\n"]

        if strategy_text:
            parts.append(f"## 策略建议（来自 Strategist）\n{strategy_text[:2000]}")

        if prd_text:
            parts.append(f"## 产品 PRD（节选）\n{prd_text[:3000]}")

        parts.append(f"## 历史内容记忆\n{memory_summary}")

        if user_note:
            parts.append(f"## 用户今日备注\n{user_note}")

        return "\n\n".join(parts)

    @staticmethod
    def _extract_theme(plan_text: str, date_str: str) -> str:
        import re
        m = re.search(r"##\s*今日主题[^\n]*\n+(.+?)(?:\n##|\Z)", plan_text, re.DOTALL)
        if m:
            return m.group(1).strip()[:120]
        return f"{date_str} 每日营销计划（已生成）"
