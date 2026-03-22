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

_PER_IMAGE_CHECKS = [
    {
        "check_id": "visual_matches_caption",
        "description": "图片的底层视觉场景/内容是否合理支撑 caption 所描述的含义（忽略 overlay 文字，只看画面本身）。失败条件：底图是完全无关的场景（如 caption 说展示翻译结果，但底图是海边日落）",
        "route_on_fail": "scriptwriter",
    },
    {
        "check_id": "no_misleading_overlay",
        "description": "overlay 文字（如有）是否与底图视觉产生明显矛盾或误导。失败条件：overlay 声称某产品功能，但底图展示的是完全不同的事物，二者放在一起会引起用户误解",
        "route_on_fail": "director",
    },
    {
        "check_id": "product_ui_when_claimed",
        "description": "若 caption 声称此图展示产品界面/截图，底图是否确实包含产品 UI 元素。若 caption 未声称展示产品界面，此项自动通过（passed: true）。失败条件：声称是产品截图，但底图是 AI 生成的插画或无关图片",
        "route_on_fail": "director",
    },
]

_HOLISTIC_CHECKS = [
    {
        "check_id": "visual_narrative_coherent",
        "description": "多图底层视觉放在一起是否讲述有逻辑、有层次的故事或演示。单张图自动视为连贯（passed: true）。失败条件：多图之间视觉风格/主题完全割裂",
        "route_on_fail": "director",
    },
    {
        "check_id": "product_accurately_represented",
        "description": "从这组图片的整体视觉印象来看，用户能否正确理解该产品/服务的核心价值。失败条件：整组图片给出了错误的产品印象（如翻译 App 的配图全是旅游风景，完全看不出与语言/翻译相关）",
        "route_on_fail": "scriptwriter",
    },
]

_SINGLE_VISUAL_AUDIT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "per_image": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "image_order": {"type": "INTEGER"},
                    "checks": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "check_id": {"type": "STRING"},
                                "passed":   {"type": "BOOLEAN"},
                                "reason":   {"type": "STRING"},
                            },
                            "required": ["check_id", "passed", "reason"],
                        },
                    },
                },
                "required": ["image_order", "checks"],
            },
        },
        "holistic": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "check_id": {"type": "STRING"},
                    "passed":   {"type": "BOOLEAN"},
                    "reason":   {"type": "STRING"},
                },
                "required": ["check_id", "passed", "reason"],
            },
        },
    },
    "required": ["per_image", "holistic"],
}

_VISUAL_AUDITOR_SYSTEM = """你是一名专业的社交媒体内容审核员，专注于图文一致性审核。
请【忽略图片上的文字叠加层】，只评估图片的底层视觉内容（场景、人物、物体、氛围）。
通过时也需提供简短 reason（≤ 50 字）。
必须对每张图的每个 per-image 条目，以及所有 holistic 条目，逐一给出判断，不可遗漏。"""

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

        votes_list, visual_results = await asyncio.gather(
            asyncio.gather(
                self._single_audit(audit_input),
                self._single_audit(audit_input),
                self._single_audit(audit_input),
            ),
            self._visual_audit(images, post_text=content_text or ""),
        )

        # ── 按条目汇总投票 ────────────────────────────────────────────────────
        item_results = self._tally_votes(votes_list)

        overall_passed = (
            all(item["passed"] for item in item_results)
            and all(item["passed"] for item in visual_results)
        )

        # ── 构建输出 JSON ─────────────────────────────────────────────────────
        all_failed = (
            [item["id"] for item in item_results if not item["passed"]]
            + [item["check_id"] for item in visual_results if not item["passed"]]
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
        """两层视觉审核：per-image × 3 checks + holistic × 2 checks，均 3-way 投票。"""
        if not images or not hasattr(self.llm_client, "chat_structured_with_images"):
            return []

        valid_images = [img for img in images if img.get("path") and Path(img["path"]).exists()]
        if not valid_images:
            return []

        image_paths = [Path(img["path"]) for img in valid_images]

        # 构造 prompt：包含每张图的 caption + 帖子正文摘要
        captions_lines = "\n".join(
            f"图{img.get('order', i + 1)} caption：{img.get('caption', '（无 caption）')}"
            for i, img in enumerate(valid_images)
        )
        post_section = f"\n## 帖子正文摘要\n{post_text[:500]}\n" if post_text else ""

        per_checks_desc = "\n".join(
            f"- {c['check_id']}：{c['description']}" for c in _PER_IMAGE_CHECKS
        )
        holistic_checks_desc = "\n".join(
            f"- {c['check_id']}：{c['description']}" for c in _HOLISTIC_CHECKS
        )

        prompt = (
            f"以上是本次帖子的 {len(image_paths)} 张配图（按顺序排列）。\n\n"
            f"## 图片信息\n{captions_lines}\n"
            f"{post_section}\n"
            f"## Per-image 审核（对每张图独立评估，image_order 从 1 开始）\n{per_checks_desc}\n\n"
            f"## Holistic 审核（对所有图片整体评估）\n{holistic_checks_desc}\n"
        )

        try:
            raw_results = await asyncio.gather(
                self._single_visual_audit(image_paths, prompt),
                self._single_visual_audit(image_paths, prompt),
                self._single_visual_audit(image_paths, prompt),
            )
        except Exception as e:
            logger.warning(f"视觉审核失败（跳过）：{e}")
            return []

        return self._tally_visual_votes(list(raw_results), valid_images)

    async def _single_visual_audit(self, image_paths: list[Path], prompt: str) -> dict:
        """单次多模态调用，返回 {per_image: [...], holistic: [...]} 原始结果。"""
        try:
            result = await self.llm_client.chat_structured_with_images(
                text=prompt,
                image_paths=image_paths,
                response_schema=_SINGLE_VISUAL_AUDIT_SCHEMA,
                system=_VISUAL_AUDITOR_SYSTEM,
                max_tokens=8192,
            )
            if isinstance(result, dict) and "per_image" in result and "holistic" in result:
                return result
            return {"per_image": [], "holistic": []}
        except Exception as e:
            logger.warning(f"单次视觉审核异常：{e}")
            return {"per_image": [], "holistic": []}

    def _tally_visual_votes(self, raw_results: list[dict], valid_images: list[dict]) -> list[dict]:
        """汇总 3 轮视觉审核投票，生成最终 visual_items 列表。"""
        visual_items = []

        # Per-image 投票
        for img in valid_images:
            order = img.get("order", 1)
            for check in _PER_IMAGE_CHECKS:
                cid = check["check_id"]
                full_id = f"img_{order}_{cid}"
                votes, reasons = [], []
                for result in raw_results:
                    img_entry = next(
                        (x for x in result.get("per_image", []) if x.get("image_order") == order),
                        None,
                    )
                    if img_entry:
                        vote_item = next(
                            (c for c in img_entry.get("checks", []) if c.get("check_id") == cid),
                            None,
                        )
                        if vote_item:
                            votes.append(bool(vote_item.get("passed", True)))
                            reasons.append(vote_item.get("reason", ""))

                passed = sum(votes) >= 2 if votes else True
                fail_reasons = [r for v, r in zip(votes, reasons) if not v and r]
                pass_reasons = [r for v, r in zip(votes, reasons) if v and r]
                visual_items.append({
                    "check_id": full_id,
                    "category": "visual_per_image",
                    "route_on_fail": check["route_on_fail"],
                    "passed": passed,
                    "votes": votes,
                    "reason": (fail_reasons or pass_reasons or ["（无说明）"])[0],
                })

        # Holistic 投票
        for check in _HOLISTIC_CHECKS:
            cid = check["check_id"]
            full_id = f"holistic_{cid}"
            votes, reasons = [], []
            for result in raw_results:
                vote_item = next(
                    (c for c in result.get("holistic", []) if c.get("check_id") == cid),
                    None,
                )
                if vote_item:
                    votes.append(bool(vote_item.get("passed", True)))
                    reasons.append(vote_item.get("reason", ""))

            passed = sum(votes) >= 2 if votes else True
            fail_reasons = [r for v, r in zip(votes, reasons) if not v and r]
            pass_reasons = [r for v, r in zip(votes, reasons) if v and r]
            visual_items.append({
                "check_id": full_id,
                "category": "visual_holistic",
                "route_on_fail": check["route_on_fail"],
                "passed": passed,
                "votes": votes,
                "reason": (fail_reasons or pass_reasons or ["（无说明）"])[0],
            })

        return visual_items

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
