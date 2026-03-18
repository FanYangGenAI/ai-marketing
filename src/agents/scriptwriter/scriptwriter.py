"""
Scriptwriter Agent — 文案创作团队。

角色构成（Debate→Synthesize）：
  ScriptwriterA (GPT-4o)     ：叙事结构设计（故事线、钩子、节奏）
  ScriptwriterB (Gemini)     ：视觉指令描述（配图方向、画面感）
  ScriptwriterC (GPT-4o)     ：小红书口语化文案（标题、正文、话题标签）
  Moderator     (Claude Opus)：综合收敛，输出可执行脚本

输出：{daily_folder}/script/daily_marketing_script.md
"""

from __future__ import annotations

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient
from src.orchestrator.debate import DebateAgent, debate_and_synthesize
from src.orchestrator.platform_adapter import PlatformAdapter


# ── 系统 Prompt 常量 ──────────────────────────────────────────────────────────

_SW_A_SYSTEM = """你是一名内容叙事策略师（ScriptwriterA）。
你的职责：根据今日营销计划，设计内容的叙事结构——故事线、情绪钩子、信息节奏。
输出格式：
- 叙事框架（3-5个步骤，说明每步的功能）
- 开头钩子设计（前3秒/前10字吸引眼球的方式）
- 情绪节奏（平静→共鸣→惊喜→行动）
避免空泛，每个建议都要具体到可操作的程度。"""

_SW_B_SYSTEM = """你是一名视觉内容导演（ScriptwriterB）。
你的职责：根据叙事结构，为每一张配图提供精确的视觉指令。
输出格式：
- 封面图视觉方向（构图、主体、配色、情绪）
- 正文配图列表（每张图的画面内容描述，中文 + English prompt）
- 整体视觉基调（风格词 3-5 个）
注意：图片描述要足够具体，可以直接用于调用 AI 图像生成工具。"""

_SW_C_SYSTEM = """你是一名小红书爆款文案专家（ScriptwriterC）。
你的职责：根据叙事结构和视觉方向，写出符合平台风格的完整文案。
输出格式：
- 标题（5个候选，不超过20字，含表情符号，使用钩子词）
- 正文（500-1000字，口语化，分段清晰，含情绪共鸣点）
- 话题标签（5-8个，格式：#话题）
- CTA（引导互动的结尾句）
必须遵守平台规范，避免使用绝对化表述。"""

_MODERATOR_SYSTEM = """你是一名内容总编辑（ScriptwriterModerator）。
你的职责：综合叙事策略师、视觉导演、文案专家三方的内容，
输出一份完整、可执行的营销脚本。

脚本格式必须严格如下：

# 营销脚本 - {date}

## 封面
- **推荐标题**：（最终选定 1 个，≤20字）
- **封面图指令**：（给 AI 图像生成工具的精确描述，中英双语）

## 正文
（完整的小红书正文，500-1000字）

## 话题标签
#标签1 #标签2 #标签3 ...（5-8个）

## 配图列表
| 序号 | 画面描述（中文） | Image Prompt（English） | 尺寸 |
|------|----------------|------------------------|------|
| 1    | ...            | ...                    | 3:4  |

## 视觉风格关键词
（3-5个，供 Director 调用图像生成时使用）

确保脚本内容与今日营销计划高度一致，文案自然流畅，配图指令精确可执行。"""


class ScriptwriterAgent(BaseAgent):
    """
    Scriptwriter Agent：通过三个子 Agent Debate→Synthesize，输出营销脚本。
    """

    def __init__(
        self,
        openai_client: BaseLLMClient,    # ScriptwriterA + ScriptwriterC
        gemini_client: BaseLLMClient,    # ScriptwriterB
        claude_client: BaseLLMClient,    # Moderator
        platform: str = "xiaohongshu",
    ):
        super().__init__(
            name="Scriptwriter",
            llm_client=claude_client,
            role_description="文案创作团队，输出完整的营销脚本和配图指令",
        )
        self._openai = openai_client
        self._gemini = gemini_client
        self._platform_adapter = PlatformAdapter(platform)

    async def run(self, context: AgentContext) -> AgentOutput:
        output_path = context.subdir("script") / "daily_marketing_script.md"
        date_str = context.run_date.strftime("%Y-%m-%d")

        # ── 读取前置输入 ──────────────────────────────────────────────────────
        plan_path = context.daily_folder / "plan" / "daily_marketing_plan.md"
        plan_text = self._read_optional(plan_path, "（暂无计划书，请先运行 Planner）")
        prd_text = self._read_optional(context.prd_path)
        platform_spec = self._platform_adapter.build_spec_prompt()

        # ── 共享上下文 ────────────────────────────────────────────────────────
        shared_context = "\n\n".join(filter(None, [
            f"# 今日文案任务 — {date_str}",
            f"## 今日营销计划\n{plan_text}",
            f"## 产品信息\n{prd_text[:2000]}" if prd_text else "",
            f"\n{platform_spec}",
        ]))

        # ── Debate Agents ─────────────────────────────────────────────────────
        sw_a = DebateAgent("ScriptwriterA（叙事）", _SW_A_SYSTEM, self._openai)
        sw_b = DebateAgent("ScriptwriterB（视觉）", _SW_B_SYSTEM, self._gemini)
        sw_c = DebateAgent("ScriptwriterC（文案）", _SW_C_SYSTEM, self._openai)

        moderator_system = _MODERATOR_SYSTEM.replace("{date}", date_str)

        # ── Debate→Synthesize ─────────────────────────────────────────────────
        result = await debate_and_synthesize(
            agents=[sw_a, sw_b, sw_c],
            moderator_client=self.llm_client,
            context=shared_context,
            moderator_system=moderator_system,
            max_rounds=3,
        )

        self._write_output(output_path, result.final_synthesis)

        summary = self._extract_title(result.final_synthesis)
        return AgentOutput(
            output_path=output_path,
            summary=summary,
            data={"rounds": result.rounds_completed},
        )

    @staticmethod
    def _extract_title(script_text: str) -> str:
        import re
        m = re.search(r"\*\*推荐标题\*\*[：:]\s*(.+)", script_text)
        if m:
            return m.group(1).strip()[:80]
        return "营销脚本已生成"
