"""
LessonMemory — 长期经验记忆模块。

职责：
  - 将每次 Audit 失败的具体原因写入 campaigns/{product}/memory/lessons_{platform}.json
  - 供 Planner / Scriptwriter / Creator 启动时读取，注入到 system prompt，避免重复犯错

文件结构：
  {
    "platform": "xiaohongshu",
    "lessons": [
      {
        "id": "lesson_001",
        "date": "2026-03-22",
        "checklist_item": "title_length",
        "category": "platform",
        "route_on_fail": "creator",
        "rule": "标题必须严格控制在20字以内（含标点），超出会被平台截断",
        "offending_example": "「用这款App，你的待办再也不会被遗忘，效率提升300%」（25字）",
        "fail_count": 1
      }
    ]
  }
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class LessonMemory:
    """
    管理单个产品 + 平台的长期审计失败经验。

    用法：
        lm = LessonMemory(campaign_root, platform="xiaohongshu")
        lm.write_lessons(failed_items)       # ReviserAgent 调用
        prompt_suffix = lm.inject_prompt()   # 各 Agent 调用
    """

    def __init__(self, campaign_root: Path, platform: str = "xiaohongshu"):
        self._platform = platform
        self._path = campaign_root / "memory" / f"lessons_{platform}.json"

    # ── 读取 ──────────────────────────────────────────────────────────────────

    def load(self) -> list[dict]:
        """加载当前平台所有 lessons，文件不存在时返回空列表。"""
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data.get("lessons", [])
        except (json.JSONDecodeError, KeyError):
            return []

    # ── 注入 ──────────────────────────────────────────────────────────────────

    def inject_prompt(self) -> str:
        """
        生成注入到 Agent system prompt 末尾的「历史创作经验」段落。
        如果没有任何 lessons，返回空字符串。
        """
        lessons = self.load()
        if not lessons:
            return ""

        lines = [
            "\n\n## 历史创作经验（来自过去审计失败，请严格遵守）",
            "以下规则是真实发生过的违规案例，本次创作必须避免：\n",
        ]
        for lesson in lessons:
            rule = lesson.get("rule", "")
            example = lesson.get("offending_example", "")
            count = lesson.get("fail_count", 1)
            item_id = lesson.get("checklist_item", "")
            count_note = f"（已违规 {count} 次）" if count > 1 else ""
            lines.append(f"- [{item_id}] {rule}{count_note}")
            if example:
                lines.append(f"  反例：{example}")

        return "\n".join(lines)

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def write_lessons(self, failed_items: list[dict]) -> None:
        """
        将 audit 失败条目写入 lessons 文件。

        Args:
            failed_items: AuditAgent 输出的 item_results 中 passed=False 的条目列表。
                          每项包含 id, category, route_on_fail, reason, description 等字段。
        """
        if not failed_items:
            return

        # 确保目录存在
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # 加载已有 lessons
        existing = self.load()
        existing_map = {lesson["checklist_item"]: lesson for lesson in existing}

        today_str = date.today().strftime("%Y-%m-%d")

        for item in failed_items:
            item_id = item.get("id", "")
            if not item_id:
                continue

            reason = item.get("reason", "")
            rule = self._reason_to_rule(item_id, item.get("description", ""), reason)
            offending_example = self._extract_example(reason)

            if item_id in existing_map:
                # 更新已有 lesson：更新日期、累计失败次数、更新 reason
                lesson = existing_map[item_id]
                lesson["date"] = today_str
                lesson["fail_count"] = lesson.get("fail_count", 1) + 1
                lesson["rule"] = rule
                if offending_example:
                    lesson["offending_example"] = offending_example
            else:
                # 新增 lesson
                lesson_id = f"lesson_{len(existing_map) + 1:03d}"
                new_lesson = {
                    "id": lesson_id,
                    "date": today_str,
                    "checklist_item": item_id,
                    "category": item.get("category", ""),
                    "route_on_fail": item.get("route_on_fail", ""),
                    "rule": rule,
                    "offending_example": offending_example,
                    "fail_count": 1,
                }
                existing_map[item_id] = new_lesson

        # 保存
        data = {
            "platform": self._platform,
            "lessons": list(existing_map.values()),
        }
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 私有辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _reason_to_rule(item_id: str, description: str, reason: str) -> str:
        """
        将清单条目描述 + 失败原因转化为一条可供下次遵守的规则。
        优先使用 description（准确），reason 作为补充细节。
        """
        rule = description
        if reason and len(reason) < 100:
            rule = f"{description}。具体违规：{reason}"
        return rule

    @staticmethod
    def _extract_example(reason: str) -> str:
        """从失败原因中提取具体的违规内容示例（截取前 80 字）。"""
        if not reason:
            return ""
        # 截取合理长度，避免过长
        return reason[:80] if len(reason) > 80 else reason
