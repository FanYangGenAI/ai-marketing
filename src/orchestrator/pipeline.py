"""
Pipeline — Orchestrator 主流程。

串联顺序：
  Strategist → Planner → Scriptwriter → Director → Creator → Audit → (ReviserAgent → 续跑)

Strategist 是每次 Pipeline 的强制第一步（冷/热启动自动判断）。

支持断点续跑：每个阶段完成后写入 {daily_folder}/.pipeline_state.json，
重启时从上次中断的阶段继续。

Audit 失败回路：
  Audit 未通过 → ReviserAgent 分析 → revision_plan.json 存在则从 route_to 续跑
  超出最大重试次数 → human_review_required.json → 流程终止
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput
from src.orchestrator.lesson_memory import LessonMemory

log = logging.getLogger(__name__)

# 阶段顺序定义（key 名称用于断点记录）
STEPS = ["strategist", "planner", "scriptwriter", "director", "creator", "audit"]


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

        # LLM 客户端与 Agent 延迟初始化（仅在真正 run() 时才 import SDK）
        self._agents_initialized = False

    def _init_agents(self) -> None:
        """首次运行时延迟初始化所有 LLM 客户端和 Agent。"""
        if self._agents_initialized:
            return
        from src.llm.client_factory import build_llm_client, resolve_moderator_model
        from src.agents.audit.audit import AuditAgent
        from src.agents.creator.creator import CreatorAgent
        from src.agents.director.director import DirectorAgent
        from src.agents.planner.planner import PlannerAgent
        from src.agents.reviser.reviser import ReviserAgent
        from src.agents.scriptwriter.scriptwriter import ScriptwriterAgent
        from src.agents.strategist.strategist import StrategistAgent

        cfg = self._load_llm_config()
        b = build_llm_client

        self._strategist = StrategistAgent(
            analyst_client=b(cfg.get("strategy_analyst", "gemini-2.5-flash")),
            reviewer_client=b(cfg.get("strategy_reviewer", "gpt-5-nano")),
            moderator_client=b(resolve_moderator_model(cfg, "strategy")),
            platform=self.platform,
        )
        self._planner = PlannerAgent(
            planner_a_client=b(cfg.get("planner_a", "gemini-2.5-flash")),
            planner_b_client=b(cfg.get("planner_b", "gemini-2.5-flash")),
            planner_c_client=b(cfg.get("planner_c", "gpt-5-nano")),
            moderator_client=b(resolve_moderator_model(cfg, "planner")),
            platform=self.platform,
        )
        self._scriptwriter = ScriptwriterAgent(
            scriptwriter_a_client=b(cfg.get("scriptwriter_a", "gpt-5-nano")),
            scriptwriter_b_client=b(cfg.get("scriptwriter_b", "gemini-2.5-flash")),
            scriptwriter_c_client=b(cfg.get("scriptwriter_c", "gpt-5-nano")),
            moderator_client=b(resolve_moderator_model(cfg, "scriptwriter")),
            platform=self.platform,
        )
        self._director = DirectorAgent(
            llm_client=b(cfg.get("director", "gemini-2.5-flash")),
            platform=self.platform,
        )
        self._creator = CreatorAgent(
            llm_client=b(cfg.get("creator", "gemini-2.5-flash")),
            platform=self.platform,
        )
        self._audit = AuditAgent(
            llm_client=b(cfg.get("auditor", "gemini-2.5-flash")),
            platform=self.platform,
        )
        self._reviser = ReviserAgent(
            llm_client=b(cfg.get("reviser", "gemini-2.5-flash")),
            platform=self.platform,
        )

        self._agents_initialized = True

    @staticmethod
    def _load_llm_config() -> dict:
        config_path = Path(__file__).parent.parent / "config" / "llm_config.json"
        if config_path.exists():
            return json.loads(config_path.read_text(encoding="utf-8"))
        return {}

    @staticmethod
    def _load_product_config(campaign_root: Path) -> dict:
        cfg_path = campaign_root / "config" / "product_config.json"
        if cfg_path.exists():
            try:
                return json.loads(cfg_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    async def run(
        self,
        run_date: date | None = None,
        prd_path: Path | None = None,
        user_note: str = "",
        from_step: str | None = None,
        to_step: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, AgentOutput]:
        """
        执行完整 Pipeline。

        Args:
            run_date:   执行日期，默认今天
            prd_path:   产品 PRD 文件路径
            user_note:  用户当日备注
            from_step:  从哪个阶段开始（跳过已完成阶段），如 "scriptwriter"
            to_step:    到哪个阶段为止（含），如 "creator"
            dry_run:    仅打印执行计划，不实际运行
        """
        run_date = run_date or date.today()
        campaign_root = self.campaigns_root / self.product_name
        daily_folder = campaign_root / "daily" / run_date.strftime("%Y-%m-%d")
        daily_folder.mkdir(parents=True, exist_ok=True)

        # ── 读取 product_config.json ──────────────────────────────────────────
        product_cfg = self._load_product_config(campaign_root)
        user_brief = product_cfg.get("user_brief", "")
        suppress_version = product_cfg.get("suppress_version_in_copy", True)

        # dry_run 不需要真实 SDK，跳过 Agent 初始化
        if not dry_run:
            self._init_agents()

        # 确定起始/结束阶段
        start_idx = 0
        if from_step and from_step in STEPS:
            start_idx = STEPS.index(from_step)
            log.info(f"从阶段 '{from_step}' 开始（跳过前 {start_idx} 个阶段）")
        end_idx = len(STEPS)
        if to_step and to_step in STEPS:
            end_idx = STEPS.index(to_step) + 1
            log.info(f"到阶段 '{to_step}' 为止（共执行 {end_idx - start_idx} 个阶段）")

        # 加载已有状态
        state = self._load_state(daily_folder)
        # 手动指定 from_step 时视为全新尝试，重置重试计数
        if from_step:
            state.pop("_retry_count", None)

        if dry_run:
            context = AgentContext(
                campaign_root=campaign_root,
                daily_folder=daily_folder,
                run_date=run_date,
                product_name=self.product_name,
                prd_path=prd_path,
                user_note=user_note,
            )
            self._print_dry_run(context, STEPS[start_idx:end_idx])
            return {}

        results: dict[str, AgentOutput] = {}

        # ── 注入 LessonMemory 到 user_note ────────────────────────────────────
        lesson_memory = LessonMemory(campaign_root, self.platform)
        lesson_injection = lesson_memory.inject_prompt()
        effective_user_note = user_note
        if lesson_injection:
            effective_user_note = user_note + lesson_injection
            log.info(f"ℹ️  已注入历史经验记忆（{len(lesson_memory.load())} 条 lessons）")

        context = AgentContext(
            campaign_root=campaign_root,
            daily_folder=daily_folder,
            run_date=run_date,
            product_name=self.product_name,
            prd_path=prd_path,
            user_note=effective_user_note,
            user_brief=user_brief,
            suppress_version_in_copy=suppress_version,
        )

        # ── 主执行循环（支持 Audit 失败回路）────────────────────────────────
        retry_count = state.get("_retry_count", 0)
        steps_to_run = STEPS[start_idx:end_idx]
        history = self._load_run_history(daily_folder)
        attempt_seq = len(history.get("attempts", []))

        log.info(
            "[Pipeline] run start product=%s daily=%s start_idx=%s end_idx=%s "
            "steps_to_run=%s _retry_count=%s attempt_seq=%s",
            self.product_name,
            daily_folder,
            start_idx,
            end_idx,
            steps_to_run,
            retry_count,
            attempt_seq,
        )

        while True:
            attempt_id = f"attempt_{attempt_seq:02d}"
            attempt_record = {
                "attempt_id": attempt_id,
                "retry_count": retry_count,
                "started_at": self._iso_now(),
                "steps": [],
            }
            history.setdefault("attempts", []).append(attempt_record)
            self._save_run_history(daily_folder, history)
            context.extra["attempt_id"] = attempt_id

            log.info(
                "[Pipeline] attempt begin attempt_id=%s retry_count=%s steps=%s",
                attempt_id,
                retry_count,
                steps_to_run,
            )

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
                    attempt_record["steps"].append(
                        {
                            "step": step,
                            "success": output.success,
                            "summary": output.summary,
                            "output_path": str(output.output_path),
                            "artifacts": list(output.data.get("attempt_artifacts", [])),
                        }
                    )
                    self._save_run_history(daily_folder, history)

                    status_icon = "✅" if output.success else "⚠️"
                    log.info(f"{status_icon} {step} 完成：{output.summary}")

                except Exception as e:
                    log.error(f"❌ 阶段 '{step}' 执行失败：{e}")
                    state[step] = {"done": False, "error": str(e)}
                    self._save_state(daily_folder, state)
                    attempt_record["steps"].append(
                        {"step": step, "success": False, "error": str(e)}
                    )
                    attempt_record["ended_at"] = self._iso_now()
                    self._save_run_history(daily_folder, history)
                    raise

            # ── 检查是否包含 audit 步骤且审核未通过 ──────────────────────────
            audit_output = results.get("audit")
            if audit_output is None or audit_output.success:
                # 没有跑 audit 或者 audit 通过，正常结束
                log.info(
                    "[Pipeline] audit finished: pass or skipped (no failure loop). "
                    "attempt_id=%s has_audit=%s audit_success=%s",
                    attempt_id,
                    audit_output is not None,
                    audit_output.success if audit_output else None,
                )
                attempt_record["audit_passed"] = True
                attempt_record["ended_at"] = self._iso_now()
                self._save_run_history(daily_folder, history)
                break
            attempt_record["audit_passed"] = False
            attempt_record["failed_items"] = list(audit_output.data.get("summary_failed", []))

            log.warning(
                "[Pipeline] audit not passed attempt_id=%s failed_items=%s summary=%s",
                attempt_id,
                attempt_record["failed_items"],
                audit_output.summary,
            )

            # ── Audit 未通过 → 运行 ReviserAgent ────────────────────────────
            log.warning("⚠️ 审核未通过，调用 ReviserAgent 分析问题...")
            reviser_context = AgentContext(
                campaign_root=campaign_root,
                daily_folder=daily_folder,
                run_date=run_date,
                product_name=self.product_name,
                prd_path=prd_path,
                user_note=effective_user_note,
                extra={"retry_count": retry_count, "attempt_id": attempt_id},
            )
            reviser_output = await self._reviser.run(reviser_context)
            results["reviser"] = reviser_output
            log.info(f"📋 Reviser：{reviser_output.summary}")
            log.info(
                "[Pipeline] reviser done attempt_id=%s success=%s route_to=%s "
                "requires_human_review=%s retry_count_in=%s",
                attempt_id,
                reviser_output.success,
                reviser_output.data.get("route_to"),
                bool(reviser_output.data.get("requires_human_review")),
                retry_count,
            )
            attempt_record["reviser"] = {
                "success": reviser_output.success,
                "summary": reviser_output.summary,
                "route_to": reviser_output.data.get("route_to"),
                "revision_instructions": reviser_output.data.get("revision_instructions", ""),
                "artifacts": list(reviser_output.data.get("attempt_artifacts", [])),
                "requires_human_review": bool(reviser_output.data.get("requires_human_review")),
            }

            # ── 检查是否需要人工介入 ─────────────────────────────────────────
            if reviser_output.data.get("requires_human_review"):
                log.error(
                    "[Pipeline] stopping: requires_human_review attempt_id=%s state._retry_count=%s",
                    attempt_id,
                    state.get("_retry_count"),
                )
                log.error("🛑 超出最大重试次数，需要人工介入。流程终止。")
                attempt_record["ended_at"] = self._iso_now()
                self._save_run_history(daily_folder, history)
                break

            if not reviser_output.success or not reviser_output.data.get("route_to"):
                log.warning(
                    "[Pipeline] stopping: reviser invalid attempt_id=%s success=%s route_to=%s",
                    attempt_id,
                    reviser_output.success,
                    reviser_output.data.get("route_to"),
                )
                log.warning("⚠️ ReviserAgent 未返回有效路由，流程终止。")
                attempt_record["ended_at"] = self._iso_now()
                self._save_run_history(daily_folder, history)
                break

            # ── 准备重跑 ─────────────────────────────────────────────────────
            route_to = reviser_output.data["route_to"]
            revision_instructions = reviser_output.data.get("revision_instructions", "")
            retry_count = reviser_output.data.get("retry_count", retry_count + 1)

            state["_retry_count"] = retry_count
            self._save_state(daily_folder, state)

            log.info(f"🔄 第 {retry_count} 次重试，从阶段 '{route_to}' 开始...")
            log.info(
                "[Pipeline] retry scheduled attempt_id=%s -> next_attempt_seq=%s "
                "new_retry_count=%s route_to=%s revision_chars=%s",
                attempt_id,
                attempt_seq + 1,
                retry_count,
                route_to,
                len(revision_instructions or ""),
            )

            # 将修订指令注入 user_note，让下游 Agent 感知
            revised_note = effective_user_note
            if revision_instructions:
                revised_note = (
                    effective_user_note
                    + f"\n\n## 本次修订指令（来自上轮审核失败，请严格执行）\n{revision_instructions}"
                )

            context = AgentContext(
                campaign_root=campaign_root,
                daily_folder=daily_folder,
                run_date=run_date,
                product_name=self.product_name,
                prd_path=prd_path,
                user_note=revised_note,
                user_brief=user_brief,
                suppress_version_in_copy=suppress_version,
                extra={"retry_count": retry_count},
            )

            # 重跑范围：route_to → audit
            route_idx = STEPS.index(route_to)
            audit_idx = STEPS.index("audit") + 1
            steps_to_run = STEPS[route_idx:audit_idx]
            log.info(
                "[Pipeline] next loop will run steps=%s (slice [%s:%s])",
                steps_to_run,
                route_idx,
                audit_idx,
            )
            attempt_record["ended_at"] = self._iso_now()
            self._save_run_history(daily_folder, history)
            attempt_seq += 1

        log.info("[Pipeline] run end product=%s daily=%s", self.product_name, daily_folder)
        return results

    async def _run_step(self, step: str, context: AgentContext) -> AgentOutput:
        agent_map = {
            "strategist": self._strategist,
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
    def _history_path(daily_folder: Path) -> Path:
        return daily_folder / ".run_history.json"

    def _load_run_history(self, daily_folder: Path) -> dict:
        p = self._history_path(daily_folder)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("attempts"), list):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return {"attempts": []}

    def _save_run_history(self, daily_folder: Path, data: dict) -> None:
        self._history_path(daily_folder).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _print_dry_run(context: AgentContext, steps: list[str]) -> None:
        W = 62
        div = "─" * W

        print(f"\n╔{'═'*W}╗")
        print(f"║{'  [DRY RUN] Pipeline 执行计划':^{W}}║")
        print(f"╚{'═'*W}╝")

        # ── 基本信息 ──────────────────────────────────────────────────────────
        print(f"\n{'▌ 基本信息':}")
        print(f"  产品名称    {context.product_name}")
        print(f"  执行日期    {context.run_date}")
        print(f"  发布平台    xiaohongshu")
        print(f"  日期目录    {context.daily_folder}")

        # ── PRD 摘要 ──────────────────────────────────────────────────────────
        print(f"\n▌ PRD")
        if context.prd_path and context.prd_path.exists():
            prd_text = context.prd_path.read_text(encoding="utf-8", errors="replace")
            lines = [l.strip() for l in prd_text.splitlines() if l.strip()]
            print(f"  文件：{context.prd_path.name}（{len(prd_text)} 字）")
            for line in lines[:5]:
                print(f"  │ {line[:70]}")
            if len(lines) > 5:
                print(f"  │ ...（共 {len(lines)} 行）")
        else:
            print(f"  ⚠️  未提供 PRD 文件")

        # ── 阶段详情 ──────────────────────────────────────────────────────────
        _STEP_DETAIL = {
            "strategist": {
                "icon": "🎯",
                "label": "Strategist — 策略反思（第一步，强制）",
                "agents": ["DataAnalyst/Gemini（经验分析）", "StrategyReviewer/GPT（策略建议）", "StrategyModerator/Claude（综合输出）"],
                "mechanism": "Debate → Synthesize（2 轮）",
                "output": "{daily}/strategy/strategy_suggestion.md（+ {campaign}/strategy_suggestion.md 镜像）",
            },
            "planner": {
                "icon": "🧠",
                "label": "Planner — 每日营销策划",
                "agents": ["PlannerA/Gemini（热点搜索）", "PlannerB/Claude（产品亮点）", "PlannerC/GPT（用户洞察）"],
                "mechanism": "Debate → Synthesize（最多 3 轮）",
                "output": "{daily}/plan/daily_marketing_plan.md",
            },
            "scriptwriter": {
                "icon": "✍️",
                "label": "Scriptwriter — 文案创作",
                "agents": ["ScriptwriterA/GPT（叙事结构）", "ScriptwriterB/Gemini（视觉指令）", "ScriptwriterC/GPT（口语文案）"],
                "mechanism": "Debate → Synthesize（最多 3 轮）",
                "output": "{daily}/script/daily_marketing_script.md",
            },
            "director": {
                "icon": "🎬",
                "label": "Director — 素材编排",
                "agents": ["Director/Gemini（规划 task_list）"],
                "mechanism": "LLM 规划 → 调用 Skills（imagegen / screenshot / crop / overlay / mask）",
                "output": "{daily}/director/ + director_task_result.json",
            },
            "creator": {
                "icon": "📦",
                "label": "Creator — 物料组装",
                "agents": ["Creator/Claude（组装发布包）"],
                "mechanism": "文案 + 素材路径 → post_package.json",
                "output": "{daily}/creator/post_package.json",
            },
            "audit": {
                "icon": "🔍",
                "label": "Audit — 合规审核（v2）",
                "agents": ["Auditor × 3 / Gemini（共享清单，并行投票）"],
                "mechanism": "StructuredOutput × 3 → per-item 2/3 多数投票",
                "output": "{daily}/audit/audit_result.json → output/final/（通过时）",
            },
        }

        print(f"\n▌ 待执行阶段（{len(steps)} 个）\n")
        for i, step in enumerate(steps, 1):
            d = _STEP_DETAIL.get(step, {})
            icon = d.get("icon", "▶")
            label = d.get("label", step)
            print(f"  {i}. {icon}  {label}")
            if d.get("agents"):
                for a in d["agents"]:
                    print(f"       · {a}")
            if d.get("mechanism"):
                print(f"       ⚙  {d['mechanism']}")
            if d.get("output"):
                print(f"       → {d['output']}")
            if i < len(steps):
                print(f"       {'↓':>5}")

        # ── 预计产出 ──────────────────────────────────────────────────────────
        daily_str = context.run_date.strftime("%Y-%m-%d")
        base = f"campaigns/{context.product_name}/daily/{daily_str}"
        print(f"\n▌ 预计产出文件")
        outputs = [
            f"{base}/plan/daily_marketing_plan.md",
            f"{base}/script/daily_marketing_script.md",
            f"{base}/director/director_task_result.json",
            f"{base}/creator/post_package.json",
            f"{base}/audit/audit_result.json",
            f"{base}/output/final/         （审核通过后）",
        ]
        for o in outputs:
            print(f"  {o}")

        print(f"\n  运行真实 Pipeline：")
        print(f"  python main.py --product {context.product_name} --prd {context.prd_path or 'docs/prd.md'}")
        print(f"\n{div}\n")
