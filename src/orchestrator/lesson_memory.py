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
        包含负向（需避免）和正向（可参考）两类信号。
        如果没有任何 lessons，返回空字符串。
        """
        lessons = self.load()
        if not lessons:
            return ""

        negative = [l for l in lessons if l.get("signal") != "positive"]
        positive = [l for l in lessons if l.get("signal") == "positive"]

        lines = []

        if negative:
            lines += [
                "\n\n## 历史创作经验（请严格遵守）",
                "### 需要避免的规则（来自审核失败或用户拒绝）\n",
            ]
            for lesson in negative:
                rule = lesson.get("rule", "")
                example = lesson.get("offending_example", "")
                count = lesson.get("fail_count", 1)
                item_id = lesson.get("checklist_item", lesson.get("id", ""))
                source = lesson.get("source", "audit_failure")
                source_label = "用户拒绝" if source == "user_rejection" else "审核失败"
                count_note = f"（已违规 {count} 次）" if count > 1 else ""
                lines.append(f"- [{source_label}][{item_id}] {rule}{count_note}")
                if example:
                    lines.append(f"  反例：{example}")

        if positive:
            lines += [
                "\n### 成功经验参考（来自用户已接受的内容）\n",
            ]
            for lesson in positive[-3:]:  # 最近 3 条正向经验
                theme = lesson.get("theme", "")
                title = lesson.get("title", "")
                note = lesson.get("note", "")
                date_val = lesson.get("date", "")
                lines.append(f"- [{date_val}] {theme or title}: {note}")

        return "\n".join(lines) if lines else ""

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
        self._save(list(existing_map.values()))

    def write_acceptance(self, title: str, theme: str, note: str = "") -> None:
        """
        记录用户接受反馈（正向信号）。

        Args:
            title: 帖子标题
            theme: 内容主题/方向
            note: 补充说明（如有）
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.load()

        today_str = date.today().strftime("%Y-%m-%d")
        lesson_id = f"lesson_{len(existing) + 1:03d}"

        new_lesson = {
            "id": lesson_id,
            "signal": "positive",
            "source": "user_acceptance",
            "date": today_str,
            "title": title,
            "theme": theme,
            "note": note,
            "category": "content",
        }
        existing.append(new_lesson)
        self._save(existing)

    def write_rejection(self, reason: str) -> None:
        """
        记录用户拒绝反馈（负向信号）。

        Args:
            reason: 用户填写的拒绝原因
        """
        if not reason:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.load()
        existing_map = {l.get("checklist_item", l.get("id", "")): l for l in existing}

        today_str = date.today().strftime("%Y-%m-%d")
        rejection_key = f"user_rejection_{today_str}"

        if rejection_key in existing_map:
            existing_map[rejection_key]["rule"] = reason
            existing_map[rejection_key]["date"] = today_str
            existing_map[rejection_key]["fail_count"] = existing_map[rejection_key].get("fail_count", 1) + 1
        else:
            lesson_id = f"lesson_{len(existing_map) + 1:03d}"
            new_lesson = {
                "id": lesson_id,
                "signal": "negative",
                "source": "user_rejection",
                "date": today_str,
                "checklist_item": rejection_key,
                "category": "content",
                "rejection_reason": reason,
                "rule": f"用户拒绝原因：{reason}",
                "fail_count": 1,
            }
            existing_map[rejection_key] = new_lesson

        self._save(list(existing_map.values()))

    def _save(self, lessons: list[dict]) -> None:
        """保存 lessons 列表到文件。"""
        data = {"platform": self._platform, "lessons": lessons}
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
