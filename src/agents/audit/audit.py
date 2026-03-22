"""
Audit Agent v2 — 共享清单 × 3 Gemini 并行投票。

设计原则：
  1. 共享审计清单：从 src/config/audit_checklist.json 动态加载条目。
  2. 独立并行审核：3 个 Gemini 实例同时对每个条目给出 {id, passed, reason}。
  3. 按条目多数投票：每条目 2/3 通过 → 该条目 ✅；全部条目通过 → 整体通过。
  4. StructuredOutput：使用 response_schema 强制 JSON 输出，消除解析错误。

输出：
  - {daily_folder}/audit/audit_result.json   — 每条目三票明细 + 整体结论
  - {daily_folder}/audit/audit_raw.md        — 各 Auditor 原始 JSON 日志
  - {daily_folder}/output/final/             — 整体通过时拷贝 creator/ 下所有文件
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.platform_adapter import PlatformAdapter

# ── 常量 ──────────────────────────────────────────────────────────────────────

_CHECKLIST_PATH = Path(__file__).parent.parent.parent / "config" / "audit_checklist.json"

# Gemini StructuredOutput schema：每个 Auditor 返回一个数组，每项对应一个清单条目
_AUDIT_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id":     {"type": "STRING"},
            "passed": {"type": "BOOLEAN"},
            "reason": {"type": "STRING"},
        },
        "required": ["id", "passed", "reason"],
    },
}

_AUDITOR_SYSTEM = """你是一名严格的内容审核员。
你将收到一份待发布的小红书图文帖子，以及一份审核清单（JSON 数组）。

请对清单中的每一个条目独立判断是否通过，输出完整的评审结果。
规则：
- 只要内容明确违反该条目要求，passed 设为 false
- 通过时也需提供简短 reason（≤ 50 字）
- reason 中禁止使用英文双引号，改用「」或不引用原文
- 必须对清单中的每一个条目都给出判断，不可遗漏"""


class AuditAgent(BaseAgent):
    def __init__(
        self,
        gemini_client: BaseLLMClient,
        platform: str = "xiaohongshu",
    ):
        super().__init__(
            name="Audit",
            llm_client=gemini_client,
            role_description="共享清单 × 3 Gemini 并行投票审核",
        )
        self._platform_adapter = PlatformAdapter(platform)
        self._checklist = self._load_checklist()

    @staticmethod
    def _load_checklist() -> list[dict]:
        if _CHECKLIST_PATH.exists():
            return json.loads(_CHECKLIST_PATH.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"审计清单未找到：{_CHECKLIST_PATH}")

    async def run(self, context: AgentContext) -> AgentOutput:
        date_str = context.run_date.strftime("%Y-%m-%d")
        audit_dir = context.subdir("audit")
        result_path = audit_dir / "audit_result.json"
        raw_log_path = audit_dir / "audit_raw.md"
        final_dir = context.subdir("output", "final")
        creator_dir = context.daily_folder / "creator"

        # ── 读取待审内容 ──────────────────────────────────────────────────────
        prd_text = self._read_optional(context.prd_path)
        package_text = self._read_optional(creator_dir / "post_package.json")
        content_text = self._read_optional(creator_dir / "post_content.md")
        platform_spec = self._platform_adapter.build_spec_prompt()

        audit_input = self._build_audit_input(
            date_str, package_text, content_text, prd_text, platform_spec
        )

        # ── 3 个 Gemini 并行投票 ──────────────────────────────────────────────
        votes_list: list[list[dict]] = await asyncio.gather(
            self._single_audit(audit_input),
            self._single_audit(audit_input),
            self._single_audit(audit_input),
        )

        # ── 按条目汇总投票 ────────────────────────────────────────────────────
        item_results = self._tally_votes(votes_list)
        overall_passed = all(item["passed"] for item in item_results)

        # ── 构建输出 JSON ─────────────────────────────────────────────────────
        audit_result = {
            "date": date_str,
            "passed": overall_passed,
            "items": item_results,
            "summary_failed": [
                item["id"] for item in item_results if not item["passed"]
            ],
        }
        self._write_json(result_path, audit_result)

        # ── 写入原始日志 ──────────────────────────────────────────────────────
        self._write_raw_log(raw_log_path, votes_list, audit_input, date_str)

        # ── 通过则拷贝到 final/ ───────────────────────────────────────────────
        if overall_passed and creator_dir.exists():
            for f in creator_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, final_dir / f.name)

        failed_count = len(audit_result["summary_failed"])
        status = "✅ 审核通过" if overall_passed else f"❌ 审核未通过（{failed_count} 条不通过）"
        return AgentOutput(
            output_path=result_path,
            summary=status,
            success=overall_passed,
            error="" if overall_passed else f"未通过条目：{', '.join(audit_result['summary_failed'])}",
            data=audit_result,
        )

    async def _single_audit(self, audit_input: str) -> list[dict]:
        """单次调用 Gemini StructuredOutput，返回每个清单条目的投票结果。"""
        # 将清单条目注入 user message
        checklist_text = json.dumps(
            [{"id": item["id"], "description": item["description"]} for item in self._checklist],
            ensure_ascii=False, indent=2,
        )
        user_content = f"{audit_input}\n\n## 审核清单\n```json\n{checklist_text}\n```"
        messages = [LLMMessage(role="user", content=user_content)]

        try:
            result = await self.llm_client.chat_structured(
                messages=messages,
                response_schema=_AUDIT_RESPONSE_SCHEMA,
                system=_AUDITOR_SYSTEM,
                max_tokens=2048,
                temperature=0.1,
            )
            # 确保结果是 list，且每项都有必要字段
            if not isinstance(result, list):
                result = []
            return result
        except Exception as e:
            # 返回所有条目 failed 的降级结果
            return [
                {"id": item["id"], "passed": False, "reason": f"Auditor 异常：{e}"}
                for item in self._checklist
            ]

    def _tally_votes(self, votes_list: list[list[dict]]) -> list[dict]:
        """
        按条目 id 汇总 3 个 Auditor 的投票，2/3 多数决定每条目结论。
        返回每条目的详细结果，含 3 票明细。
        """
        # 构建 id → checklist item 映射
        checklist_map = {item["id"]: item for item in self._checklist}

        # 汇总每个 id 的投票
        id_to_votes: dict[str, list[dict]] = {item["id"]: [] for item in self._checklist}
        for auditor_votes in votes_list:
            for vote in auditor_votes:
                vid = vote.get("id", "")
                if vid in id_to_votes:
                    id_to_votes[vid].append(vote)

        item_results = []
        for checklist_item in self._checklist:
            cid = checklist_item["id"]
            votes = id_to_votes[cid]
            pass_count = sum(1 for v in votes if v.get("passed", False))
            majority_passed = pass_count >= 2  # 2/3 多数

            # 取失败票的 reason 作为代表原因（优先展示问题）
            fail_reasons = [v["reason"] for v in votes if not v.get("passed", True) and v.get("reason")]
            pass_reasons = [v["reason"] for v in votes if v.get("passed", False) and v.get("reason")]
            representative_reason = (fail_reasons or pass_reasons or ["无"])[0]

            item_results.append({
                "id": cid,
                "category": checklist_item["category"],
                "description": checklist_item["description"],
                "route_on_fail": checklist_item["route_on_fail"],
                "passed": majority_passed,
                "votes": {"pass": pass_count, "fail": len(votes) - pass_count},
                "reason": representative_reason,
                "all_reasons": [v.get("reason", "") for v in votes],
            })

        return item_results

    @staticmethod
    def _build_audit_input(
        date_str: str,
        package_text: str,
        content_text: str,
        prd_text: str,
        platform_spec: str,
    ) -> str:
        return f"""## 待审内容（{date_str}）

### 发布包（JSON）
{package_text or "（未找到 post_package.json）"}

### 可读版本
{content_text or "（未找到 post_content.md）"}

### 产品 PRD（参考，用于核实事实准确性）
{prd_text[:2000] if prd_text else "（无 PRD）"}

{platform_spec}"""

    @staticmethod
    def _write_raw_log(
        log_path: Path,
        votes_list: list[list[dict]],
        audit_input: str,
        date_str: str,
    ) -> None:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# Audit 原始输出日志 — {date_str}\n\n")
            f.write("## 审核输入\n\n")
            f.write(audit_input)
            f.write("\n\n---\n\n")
            for i, votes in enumerate(votes_list, 1):
                f.write(f"## Auditor {i} 投票结果\n\n")
                f.write("```json\n")
                f.write(json.dumps(votes, ensure_ascii=False, indent=2))
                f.write("\n```\n\n---\n\n")
