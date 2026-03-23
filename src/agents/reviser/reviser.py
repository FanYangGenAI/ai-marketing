"""
ReviserAgent — 审计失败路由器。

职责：
  1. 读取 audit_result.json，收集所有 passed=false 的条目
  2. 按各条目的 route_on_fail 字段，取最上游阶段作为 route_to
  3. 使用 LLM 生成 revision_instructions（对应阶段的具体修改要求）
  4. 将失败条目写入 LessonMemory（长期记忆）
  5. 检查 retry_count（从 context.extra 读取）：
     - < MAX_RETRIES（默认 2）→ 写入 audit/revision_plan.json
     - ≥ MAX_RETRIES         → 写入 audit/human_review_required.json，停止自动重跑
  6. 返回 route_to 供 Pipeline 决定续跑起点

路由优先级（越靠前 = 越上游）：
  planner > scriptwriter > director > creator
"""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.lesson_memory import LessonMemory

MAX_RETRIES = 2

# 路由优先级：越靠前越上游
ROUTE_PRIORITY = ["planner", "scriptwriter", "director", "creator"]

_REVISER_SYSTEM = """你是一名内容修订指令生成专员（Reviser）。
你将收到一份内容审核失败报告（包含未通过的条目列表和具体原因）。

你的任务：生成一份简洁、可执行的修订指令，指导对应阶段的 Agent 进行修改。

要求：
- 针对每个失败条目给出具体的修改动作（不是泛泛而谈）
- 使用编号列表，每条不超过 50 字
- 语气直接，直接说"请修改……"或"请避免……"
- 不需要解释审核逻辑，只说要做什么"""


class ReviserAgent(BaseAgent):
    def __init__(
        self,
        gemini_client: BaseLLMClient,
        platform: str = "xiaohongshu",
    ):
        super().__init__(
            name="Reviser",
            llm_client=gemini_client,
            role_description="审计失败分类路由，生成修订指令并写入长期记忆",
        )
        self._platform = platform

    async def run(self, context: AgentContext) -> AgentOutput:
        date_str = context.run_date.strftime("%Y-%m-%d")
        audit_dir = context.subdir("audit")
        attempt_dir = context.stage_attempt_dir("audit")
        audit_result_path = audit_dir / "audit_result.json"
        revision_plan_path = audit_dir / "revision_plan.json"
        human_review_path = audit_dir / "human_review_required.json"

        retry_count = context.extra.get("retry_count", 0)

        # ── 读取 audit 结果 ───────────────────────────────────────────────────
        if not audit_result_path.exists():
            return AgentOutput(
                output_path=audit_dir / "reviser_error.txt",
                summary="❌ 找不到 audit_result.json",
                success=False,
                error="audit_result.json 不存在",
            )

        audit_result = json.loads(audit_result_path.read_text(encoding="utf-8"))
        all_items = audit_result.get("items", []) + audit_result.get("visual_items", [])
        failed_items = [item for item in all_items if not item.get("passed", True)]

        if not failed_items:
            return AgentOutput(
                output_path=revision_plan_path,
                summary="✅ 无失败条目，无需修订",
                success=True,
                data={"route_to": None},
            )

        # ── 确定路由目标（最上游阶段）────────────────────────────────────────
        route_to = self._determine_route(failed_items)

        # ── 生成修订指令 ──────────────────────────────────────────────────────
        revision_instructions = await self._generate_instructions(failed_items, route_to)

        # ── 写入 LessonMemory ─────────────────────────────────────────────────
        lesson_memory = LessonMemory(context.campaign_root, self._platform)
        lesson_memory.write_lessons(failed_items)

        # ── RetryGuard：检查重试次数 ──────────────────────────────────────────
        if retry_count >= MAX_RETRIES:
            # 超限，写入 human_review_required.json
            payload = {
                "status": "requires_human_review",
                "retry_count": retry_count,
                "date": date_str,
                "failed_items": [item.get("id") or item.get("check_id", "?") for item in failed_items],
                "last_audit_result": str(audit_result_path),
                "note": (
                    f"已自动重试 {retry_count} 次，仍未通过。"
                    "请人工审查后决定是否发布或放弃。"
                ),
            }
            self._write_json(human_review_path, payload)
            self._copy_attempt_file(human_review_path, attempt_dir / "human_review_required.json")
            summary = (
                f"🛑 已重试 {retry_count} 次，超出上限。"
                f"已写入 human_review_required.json，等待人工介入。"
            )
            return AgentOutput(
                output_path=human_review_path,
                summary=summary,
                success=False,
                error="超出最大重试次数",
                data={"route_to": None, "requires_human_review": True},
            )

        # ── 正常重试：写入 revision_plan.json ────────────────────────────────
        new_retry_count = retry_count + 1
        payload = {
            "route_to": route_to,
            "retry_count": new_retry_count,
            "failed_items": [item.get("id") or item.get("check_id", "?") for item in failed_items],
            "failed_details": [
                {
                    "id": item.get("id") or item.get("check_id", "?"),
                    "category": item.get("category", ""),
                    "route_on_fail": item.get("route_on_fail", ""),
                    "reason": item.get("reason", ""),
                }
                for item in failed_items
            ],
            "revision_instructions": revision_instructions,
        }
        self._write_json(revision_plan_path, payload)
        self._copy_attempt_file(revision_plan_path, attempt_dir / "revision_plan.json")

        summary = (
            f"📋 修订计划已生成：路由到 {route_to}，"
            f"{len(failed_items)} 个条目需修复（第 {new_retry_count} 次重试）"
        )
        return AgentOutput(
            output_path=revision_plan_path,
            summary=summary,
            success=True,
            data={
                "route_to": route_to,
                "retry_count": new_retry_count,
                "revision_instructions": revision_instructions,
                "requires_human_review": False,
                "attempt_artifacts": [str(attempt_dir / "revision_plan.json")],
            },
        )

    async def _generate_instructions(
        self, failed_items: list[dict], route_to: str
    ) -> str:
        """使用 LLM 生成针对 route_to 阶段的具体修订指令。"""
        failed_summary = "\n".join(
            f"- [{item.get('id') or item.get('check_id', '?')}] {item.get('description', '')}：{item.get('reason', '')}"
            for item in failed_items
        )
        user_msg = f"""以下审核条目未通过，需要在「{route_to}」阶段进行修改：

{failed_summary}

请生成修订指令（针对 {route_to} 阶段的 Agent）："""

        messages = [LLMMessage(role="user", content=user_msg)]
        try:
            response = await self.llm_client.chat(
                messages=messages,
                system=_REVISER_SYSTEM,
                max_tokens=1024,
                temperature=0.3,
            )
            return response.content.strip()
        except Exception as e:
            # 降级：直接列出失败原因作为指令
            lines = [f"（LLM 生成指令失败，使用原始失败原因）"]
            for item in failed_items:
                lines.append(f"- [{item.get('id') or item.get('check_id', '?')}] {item.get('reason', item.get('description', ''))}")
            return "\n".join(lines)

    @staticmethod
    def _determine_route(failed_items: list[dict]) -> str:
        """取所有失败条目中最上游的 route_on_fail 阶段。"""
        routes_in_items = {item.get("route_on_fail", "creator") for item in failed_items}
        for stage in ROUTE_PRIORITY:
            if stage in routes_in_items:
                return stage
        return "creator"
