"""
AlternativePlanMemory — 备选方案记忆池。

职责：
  - 每次对抗辩论结束后，将未被选中的备选方案存档
  - 下次辩论 Round 1 开始前，将高复用潜力的历史备选方案注入上下文
  - 与 LessonMemory 完全分离（LessonMemory 记录成功/失败教训；本模块记录策略资产）

存储路径：
  campaigns/{product}/memory/alt_plans_{platform}_{step}.json

文件结构：
  {
    "platform": "xiaohongshu",
    "step": "strategist",
        "sessions": [
      {
        "date": "2026-04-07",
        "attempt_id": "attempt_01",
        "debate_rounds_conducted": 1,
        "selected": {
          "source_agent": "DataAnalyst",
          "source_plan_label": "B",
          "core_claim": "...",
          "selection_reason": "..."
        },
        "alternatives": [
          {
            "source_agent": "CreativeStrategist",
            "source_plan_label": "A",
            "core_claim": "...",
            "why_not_selected": "...",
            "avg_score": 6.5,
            "reuse_potential": "high"
          }
        ]
      }
    ]
  }
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SelectedPlanRecord:
    source_agent: str
    source_plan_label: str      # "A" / "B" / "C"
    core_claim: str
    selection_reason: str


@dataclass
class AlternativePlanRecord:
    source_agent: str
    source_plan_label: str      # "A" / "B" / "C"
    core_claim: str
    why_not_selected: str
    avg_score: float            # 0-10，来自 Round 3 对手评分均值
    reuse_potential: str        # "high" / "medium" / "low"


class AlternativePlanMemory:
    """
    管理单个产品 + 平台 + 步骤的备选方案记忆池。

    用法：
        mem = AlternativePlanMemory(campaign_root, "xiaohongshu", "strategist")
        mem.save_session(date_str, selected, alternatives, attempt_id="attempt_01", debate_rounds_conducted=1)
        context_block = mem.inject_context(n=3)   # 注入到 Round 1 背景
    """

    def __init__(self, campaign_root: Path, platform: str, step: str):
        self._platform = platform
        self._step = step
        self._path = campaign_root / "memory" / f"alt_plans_{platform}_{step}.json"

    # ── 读取 ──────────────────────────────────────────────────────────────────

    def load_sessions(self) -> list[dict]:
        """加载所有历史 session，文件不存在时返回空列表。"""
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data.get("sessions", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def load_recent_alternatives(
        self,
        n: int = 5,
        min_reuse_potential: str = "medium",
    ) -> list[dict]:
        """
        返回最近 n 条满足复用潜力阈值的备选方案。

        Args:
            n: 最多返回条数
            min_reuse_potential: 最低复用潜力阈值（"high" / "medium" / "low"）
        """
        _rank = {"high": 2, "medium": 1, "low": 0}
        min_rank = _rank.get(min_reuse_potential, 1)

        results: list[dict] = []
        for session in reversed(self.load_sessions()):  # 从最新开始
            for alt in session.get("alternatives", []):
                potential = alt.get("reuse_potential", "low")
                if _rank.get(potential, 0) >= min_rank:
                    results.append({
                        **alt,
                        "date": session.get("date", ""),
                        "attempt_id": session.get("attempt_id", ""),
                    })
                if len(results) >= n:
                    return results
        return results

    # ── 注入 ──────────────────────────────────────────────────────────────────

    def inject_context(self, n: int = 3) -> str:
        """
        生成注入到 Round 1 背景中的「历史备选方案参考」段落。
        返回空字符串表示无历史数据。
        """
        alts = self.load_recent_alternatives(n=n, min_reuse_potential="medium")
        if not alts:
            return ""

        lines = [
            "## 历史备选方案参考（来自往期辩论，复用潜力较高，可作为灵感来源）",
            "（这些方案当时未被选中，但被评估为有价值，可在本次重新考虑）\n",
        ]
        for alt in alts:
            date_str = alt.get("date", "")
            att = alt.get("attempt_id", "")
            att_tag = f" attempt={att}" if att else ""
            agent = alt.get("source_agent", "")
            label = alt.get("source_plan_label", "")
            claim = alt.get("core_claim", "")
            why_not = alt.get("why_not_selected", "")
            potential = alt.get("reuse_potential", "")
            lines.append(
                f"- [{date_str}]{att_tag}[{agent} 方案{label}] {claim}\n"
                f"  当时未选原因：{why_not}  复用潜力：{potential}"
            )
        return "\n".join(lines)

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def save_session(
        self,
        date: str,
        selected: SelectedPlanRecord,
        alternatives: list[AlternativePlanRecord],
        *,
        attempt_id: str | None = None,
        debate_rounds_conducted: int | None = None,
    ) -> dict:
        """
        保存本次辩论的选定方案和备选归档。

        Args:
            date: 运行日期字符串，如 "2026-04-07"
            selected: 被选中的方案记录
            alternatives: 未被选中的备选方案列表
            attempt_id: 若提供，写入 session 并额外落盘
                memory/alt_plans_{platform}_{step}_{attempt_id}.json 便于按次对比
            debate_rounds_conducted: 对抗辩论实际执行轮次（来自 AdversarialDebateResult）

        Returns:
            本次追加的 session 字典（便于写入 attempt 目录快照）
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        sessions = self.load_sessions()

        new_session: dict = {
            "date": date,
            "selected": asdict(selected),
            "alternatives": [asdict(a) for a in alternatives],
        }
        if attempt_id:
            new_session["attempt_id"] = attempt_id
        if debate_rounds_conducted is not None:
            new_session["debate_rounds_conducted"] = debate_rounds_conducted

        sessions.append(new_session)
        self._save(sessions)

        if attempt_id:
            attempt_path = self._path.parent / f"{self._path.stem}_{attempt_id}.json"
            attempt_path.write_text(
                json.dumps(
                    {
                        "platform": self._platform,
                        "step": self._step,
                        "attempt_id": attempt_id,
                        "session": new_session,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        return new_session

    # ── 私有辅助 ──────────────────────────────────────────────────────────────

    def _save(self, sessions: list[dict]) -> None:
        data = {
            "platform": self._platform,
            "step": self._step,
            "sessions": sessions,
        }
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
