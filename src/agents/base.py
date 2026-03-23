"""
BaseAgent — 所有 Agent 的抽象基类。

每个具体 Agent 继承此类并实现 run() 方法。
Agent 的职责只是：读取上下文 → 调用 LLM（可能多轮 Debate）→ 写输出文件 → 返回 AgentOutput。
"""

from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.llm.base import BaseLLMClient


@dataclass
class AgentContext:
    """
    Agent 运行所需的所有上下文信息。
    由 Orchestrator 在调用每个 Agent 前构建并传入。
    """
    # 当前 campaign 根目录（e.g. campaigns/MyApp/）
    campaign_root: Path

    # 当日工作目录（e.g. campaigns/MyApp/daily/2026-03-17/）
    daily_folder: Path

    # 当日日期
    run_date: date

    # 产品名称
    product_name: str

    # 产品 PRD 路径（可选，首次运行时提供）
    prd_path: Path | None = None

    # 用户当日额外输入（临时想法、特殊要求等 / today_note）
    user_note: str = ""

    # 产品级永久需求描述（创建项目时写，每次 Pipeline 均传入）
    user_brief: str = ""

    # 文案是否抑制版本号（默认 True）
    suppress_version_in_copy: bool = True

    # 额外的键值对，供特定 Agent 使用
    extra: dict = field(default_factory=dict)

    @property
    def asset_library_root(self) -> Path:
        return self.campaign_root / "asset_library"

    @property
    def strategy_path(self) -> Path:
        """
        Per-day Strategist output (and Planner input) for this run.
        Path: daily/{date}/strategy/strategy_suggestion.md
        """
        return self.daily_folder / "strategy" / "strategy_suggestion.md"

    @property
    def strategy_latest_mirror_path(self) -> Path:
        """Product-level copy of the latest strategy (convenience for tools / humans)."""
        return self.campaign_root / "strategy_suggestion.md"

    def subdir(self, *parts: str) -> Path:
        """获取 daily_folder 下的子目录，不存在则创建。"""
        p = self.daily_folder.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def attempt_id(self) -> str:
        """Current attempt label, e.g. attempt_00."""
        return str(self.extra.get("attempt_id", "attempt_00"))

    def stage_attempt_dir(self, stage: str) -> Path:
        """daily/{stage}/attempts/{attempt_id}/"""
        p = self.daily_folder / stage / "attempts" / self.attempt_id
        p.mkdir(parents=True, exist_ok=True)
        return p


@dataclass
class AgentOutput:
    """Agent 运行的结果。"""
    # 主要输出文件路径（Markdown 计划书、JSON 结果等）
    output_path: Path

    # 一句话摘要，供下一个 Agent 在 context.extra 中引用
    summary: str

    # 是否成功
    success: bool = True

    # 失败原因（success=False 时填写）
    error: str = ""

    # 可选：额外的结构化数据（供 Orchestrator 传递给下游 Agent）
    data: dict = field(default_factory=dict)

    def read_text(self) -> str:
        """读取主输出文件内容。"""
        return self.output_path.read_text(encoding="utf-8")

    def to_context_extra(self, key: str) -> dict:
        """将此 output 打包为 AgentContext.extra 的一个条目。"""
        return {key: {"path": str(self.output_path), "summary": self.summary}}


class BaseAgent(ABC):
    """
    所有 Agent 的基类。

    子类必须实现：
        run(context: AgentContext) -> AgentOutput

    建议的实现模式：
        1. 从 context 中读取前置 Agent 的输出文件
        2. 构建 LLM messages
        3. 调用 self.llm_client.chat() 或 debate_and_synthesize()
        4. 将结果写入 context.daily_folder 下的约定路径
        5. 返回 AgentOutput
    """

    def __init__(self, name: str, llm_client: BaseLLMClient, role_description: str = ""):
        self.name = name
        self.llm_client = llm_client
        self.role_description = role_description

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentOutput:
        """执行 Agent 的核心逻辑。"""
        ...

    # ── 辅助方法 ─────────────────────────────────────────────────────────────

    def _write_output(self, path: Path, content: str) -> None:
        """写文本输出文件（自动创建父目录）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_json(self, path: Path, data: dict | list) -> None:
        """写 JSON 输出文件（自动创建父目录）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_optional(self, path: Path, default: str = "") -> str:
        """读取文件内容，文件不存在时返回 default。"""
        if path and path.exists():
            return path.read_text(encoding="utf-8")
        return default

    def _copy_attempt_file(self, src: Path, dst: Path) -> None:
        """Copy a produced file into attempt archive path."""
        if not src.exists() or not src.is_file():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} llm={self.llm_client.model_name()!r}>"
