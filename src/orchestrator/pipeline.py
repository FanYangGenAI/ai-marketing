"""
Pipeline — Orchestrator 主流程。

串联顺序：
  Planner → Scriptwriter → Director → Creator → Audit

Strategist 按需运行（--run-strategist 标志或冷启动时）。

支持断点续跑：每个阶段完成后写入 {daily_folder}/.pipeline_state.json，
重启时从上次中断的阶段继续。
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from src.agents.audit.audit import AuditAgent
from src.agents.base import AgentContext, AgentOutput
from src.agents.creator.creator import CreatorAgent
from src.agents.director.director import DirectorAgent
from src.agents.planner.planner import PlannerAgent
from src.agents.scriptwriter.scriptwriter import ScriptwriterAgent
from src.llm.claude_client import ClaudeClient
from src.llm.gemini_client import GeminiClient
from src.llm.openai_client import OpenAIClient

log = logging.getLogger(__name__)


# 阶段顺序定义（key 名称用于断点记录）
STEPS = ["planner", "scriptwriter", "director", "creator", "audit"]


class Pipeline:
    """
    完整的每日内容生成 Pipeline。

    用法：
        pipeline = Pipeline(product_name="MyApp")
        await pipeline.run(run_date=date.today(), prd_path=Path("docs/prd.md"))
    """

    def __init__(
        self,
        product_name: str,
        campaigns_root: Path = Path("campaigns"),
        platform: str = "xiaohongshu",
    ):
        self.product_name = product_name
        self.campaigns_root = campaigns_root
        self.platform = platform

        # 初始化 LLM 客户端（每个都从环境变量读取 API Key）
        self._claude = ClaudeClient()
        self._openai = OpenAIClient()
        self._gemini = GeminiClient()

        # 初始化 Agents
        self._planner = PlannerAgent(self._gemini, self._claude, self._openai)
        self._scriptwriter = ScriptwriterAgent(self._openai, self._gemini, self._claude, platform)
        self._director = DirectorAgent(self._gemini, platform)
        self._creator = CreatorAgent(self._claude, platform)
        self._audit = AuditAgent(self._openai, self._claude, platform)

    async def run(
        self,
        run_date: date | None = None,
        prd_path: Path | None = None,
        user_note: str = "",
        from_step: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, AgentOutput]:
        """
        执行完整 Pipeline。

        Args:
            run_date:   执行日期，默认今天
            prd_path:   产品 PRD 文件路径
            user_note:  用户当日备注
            from_step:  从哪个阶段开始（跳过已完成阶段），如 "scriptwriter"
            dry_run:    仅打印执行计划，不实际运行
        """
        run_date = run_date or date.today()
        campaign_root = self.campaigns_root / self.product_name
        daily_folder = campaign_root / "daily" / run_date.strftime("%Y-%m-%d")
        daily_folder.mkdir(parents=True, exist_ok=True)

        context = AgentContext(
            campaign_root=campaign_root,
            daily_folder=daily_folder,
            run_date=run_date,
            product_name=self.product_name,
            prd_path=prd_path,
            user_note=user_note,
        )

        # 确定起始阶段
        start_idx = 0
        if from_step and from_step in STEPS:
            start_idx = STEPS.index(from_step)
            log.info(f"从阶段 '{from_step}' 开始（跳过前 {start_idx} 个阶段）")

        # 加载已有状态
        state = self._load_state(daily_folder)

        if dry_run:
            self._print_dry_run(context, STEPS[start_idx:])
            return {}

        results: dict[str, AgentOutput] = {}

        # 按顺序执行
        steps_to_run = STEPS[start_idx:]
        for step in steps_to_run:
            log.info(f"▶ 开始阶段：{step}")
            try:
                output = await self._run_step(step, context)
                results[step] = output
                state[step] = {
                    "done": True,
                    "output_path": str(output.output_path),
                    "summary": output.summary,
                    "success": output.success,
                }
                self._save_state(daily_folder, state)

                status_icon = "✅" if output.success else "⚠️"
                log.info(f"{status_icon} {step} 完成：{output.summary}")

                # Audit 不通过时停止流程
                if step == "audit" and not output.success:
                    log.warning(f"⚠️ 审核未通过，流程终止。修改意见已写入 audit_result.json")
                    break

            except Exception as e:
                log.error(f"❌ 阶段 '{step}' 执行失败：{e}")
                state[step] = {"done": False, "error": str(e)}
                self._save_state(daily_folder, state)
                raise

        return results

    async def _run_step(self, step: str, context: AgentContext) -> AgentOutput:
        agent_map = {
            "planner": self._planner,
            "scriptwriter": self._scriptwriter,
            "director": self._director,
            "creator": self._creator,
            "audit": self._audit,
        }
        return await agent_map[step].run(context)

    # ── 断点状态管理 ──────────────────────────────────────────────────────────

    @staticmethod
    def _state_path(daily_folder: Path) -> Path:
        return daily_folder / ".pipeline_state.json"

    def _load_state(self, daily_folder: Path) -> dict:
        p = self._state_path(daily_folder)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {}

    def _save_state(self, daily_folder: Path, state: dict) -> None:
        self._state_path(daily_folder).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _print_dry_run(context: AgentContext, steps: list[str]) -> None:
        print(f"\n{'='*60}")
        print(f"[DRY RUN] Pipeline 执行计划")
        print(f"  产品：{context.product_name}")
        print(f"  日期：{context.run_date}")
        print(f"  日期目录：{context.daily_folder}")
        print(f"  PRD：{context.prd_path or '未提供'}")
        print(f"  待执行阶段：{' → '.join(steps)}")
        print(f"{'='*60}\n")
