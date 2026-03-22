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

import logging

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.platform_adapter import PlatformAdapter

logger = logging.getLogger(__name__)

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

_VISUAL_CHECKLIST = [
    {
        "id": "image_complete",
        "description": "每张图片的核心主体完整可辨：人物头部/面部、产品主体、关键 UI 界面未被切掉一半或大半。注意：主体自然填满画面并接触边缘是正常构图，仅当核心内容明显缺失（如人物只剩半个头、产品只剩一角）才判为不通过。",
        "route_on_fail": "director",
    },
    {
        "id": "image_layout",
        "description": "多对象横向并排构图（如步骤图、对比图、多手机并列）未被竖版裁切，左右内容均完整可见",
        "route_on_fail": "director",
    },
    {
        "id": "image_readable",
        "description": "产品实际截图中的 UI 文字和界面元素清晰可读。注意：AI 生成的概念插图中出现模糊的手机屏幕、装饰性文字或艺术化处理属于正常现象，不算不通过；此条仅针对真实产品截图。",
        "route_on_fail": "director",
    },
    {
        "id": "image_content_match",
        "description": "图片画面内容与帖子文案所描述的使用场景或功能方向整体一致，无明显偏差。注意：如果下方未提供帖子文案，此条直接判为通过。",
        "route_on_fail": "scriptwriter",
    },
]

_VISUAL_AUDIT_SCHEMA = {
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

_VISUAL_AUDITOR_SYSTEM = """你是一名严格的视觉素材质量审核员。
你将收到若干张图片素材（小红书帖子配图）以及一份视觉质量清单。
请仔细观察每一张图片，然后对清单中的每个条目做出整体判断。
规则：
- 只要有任意一张图片明确违反该条目，passed 设为 false
- 通过时也需提供简短 reason（≤ 50 字）
- 必须对清单中的每一个条目都给出判断，不可遗漏"""

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

        # ── 3 个 Gemini 并行投票（文字审核）+ 视觉审核 并行 ────────────────────
        package = json.loads(package_text) if package_text else {}
        images = package.get("images", [])

        votes_list, visual_raw = await asyncio.gather(
            asyncio.gather(
                self._single_audit(audit_input),
                self._single_audit(audit_input),
                self._single_audit(audit_input),
            ),
            self._visual_audit(images, post_text=content_text or ""),
        )

        # ── 按条目汇总投票 ────────────────────────────────────────────────────
        item_results = self._tally_votes(votes_list)
        visual_results = self._finalize_visual(visual_raw)

        overall_passed = (
            all(item["passed"] for item in item_results)
            and all(item["passed"] for item in visual_results)
        )

        # ── 构建输出 JSON ─────────────────────────────────────────────────────
        all_failed = (
            [item["id"] for item in item_results if not item["passed"]]
            + [item["id"] for item in visual_results if not item["passed"]]
        )
        audit_result = {
            "date": date_str,
            "passed": overall_passed,
            "items": item_results,
            "visual_items": visual_results,
            "summary_failed": all_failed,
        }
        self._write_json(result_path, audit_result)

        # ── 写入原始日志 ──────────────────────────────────────────────────────
        self._write_raw_log(raw_log_path, votes_list, audit_input, date_str)

        # ── 通过则拷贝到 final/ ───────────────────────────────────────────────
        if overall_passed and creator_dir.exists():
            # 1. 文案文件（post_package.json / post_content.md / creator_raw.md）
            for f in creator_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, final_dir / f.name)
            # 2. post_package.json 中引用的最终图片（按发布顺序编号）
            package_path = creator_dir / "post_package.json"
            if package_path.exists():
                try:
                    package = json.loads(package_path.read_text(encoding="utf-8"))
                    for img in package.get("images", []):
                        src = Path(img["path"])
                        if src.exists():
                            dst_name = f"img_{img['order']:02d}_{src.name}"
                            shutil.copy2(src, final_dir / dst_name)
                except Exception:
                    pass  # 图片拷贝失败不影响主流程

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
                max_tokens=8192,
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

    async def _visual_audit(self, images: list[dict], post_text: str = "") -> list[dict]:
        """多模态视觉审核：把图片传给 Gemini，对 _VISUAL_CHECKLIST 逐项判断。"""
        if not images or not hasattr(self.llm_client, "chat_structured_with_images"):
            return []

        image_paths = [Path(img["path"]) for img in images if img.get("path") and Path(img["path"]).exists()]
        if not image_paths:
            return []

        checklist_text = json.dumps(
            [{"id": item["id"], "description": item["description"]} for item in _VISUAL_CHECKLIST],
            ensure_ascii=False, indent=2,
        )
        post_section = f"\n## 帖子文案（供 image_content_match 判断用）\n{post_text[:1000]}\n" if post_text else ""
        prompt = (
            f"以上是本次帖子的 {len(image_paths)} 张配图。"
            f"{post_section}\n"
            f"## 视觉审核清单\n```json\n{checklist_text}\n```\n\n"
            "请对每个条目做出整体判断（只要有一张图明确违反即为 false）。"
        )

        try:
            result = await self.llm_client.chat_structured_with_images(
                text=prompt,
                image_paths=image_paths,
                response_schema=_VISUAL_AUDIT_SCHEMA,
                system=_VISUAL_AUDITOR_SYSTEM,
                max_tokens=4096,
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning(f"视觉审核失败（跳过）：{e}")
            return []

    def _finalize_visual(self, raw: list[dict]) -> list[dict]:
        """将视觉审核原始结果补充 checklist 元数据，缺失条目标记为跳过。"""
        raw_map = {item.get("id"): item for item in raw}
        results = []
        for checklist_item in _VISUAL_CHECKLIST:
            cid = checklist_item["id"]
            if cid in raw_map:
                results.append({
                    "id": cid,
                    "category": "visual",
                    "description": checklist_item["description"],
                    "route_on_fail": checklist_item["route_on_fail"],
                    "passed": raw_map[cid].get("passed", True),
                    "reason": raw_map[cid].get("reason", ""),
                })
            else:
                # 模型未返回该条目，视为跳过（不计入失败）
                results.append({
                    "id": cid,
                    "category": "visual",
                    "description": checklist_item["description"],
                    "route_on_fail": checklist_item["route_on_fail"],
                    "passed": True,
                    "reason": "（视觉审核未覆盖此条目）",
                })
        return results

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
