#!/usr/bin/env python3
"""
单独运行 Planner Agent，便于逐步验收。
用法：python run_planner.py --product 原语 --prd docs/PRD_v3.1.md
"""
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(override=True)

# ── 日志：显示所有层级（含 Debate 的每一轮）──────────────────────────────────
import io
handler = logging.StreamHandler(
    stream=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
)
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
))
logging.basicConfig(level=logging.DEBUG, handlers=[handler])
log = logging.getLogger("run_planner")

# 屏蔽 httpx / httpcore 的噪音
for noisy in ("httpx", "httpcore", "openai._base_client", "anthropic._base_client"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", default="原语")
    parser.add_argument("--prd", default="docs/PRD_v3.1.md")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    from src.llm.claude_client import ClaudeClient
    from src.llm.gemini_client import GeminiClient
    from src.llm.openai_client import OpenAIClient
    from src.agents.planner.planner import PlannerAgent
    from src.agents.base import AgentContext

    log.info("初始化 LLM 客户端...")
    gemini = GeminiClient()
    claude = ClaudeClient()
    openai_ = OpenAIClient()
    log.info(f"  PlannerA → {gemini.model_name()}")
    log.info(f"  PlannerB → {claude.model_name()}")
    log.info(f"  PlannerC → {openai_.model_name()}")
    log.info(f"  Moderator → {claude.model_name()}")

    product = args.product
    prd_path = Path(args.prd)
    run_date = date.today()
    campaign_root = Path("campaigns") / product
    daily_folder = campaign_root / "daily" / run_date.strftime("%Y-%m-%d")
    daily_folder.mkdir(parents=True, exist_ok=True)

    context = AgentContext(
        campaign_root=campaign_root,
        daily_folder=daily_folder,
        run_date=run_date,
        product_name=product,
        prd_path=prd_path if prd_path.exists() else None,
        user_note=args.note,
    )

    log.info(f"\n{'='*60}")
    log.info(f"启动 Planner  产品={product}  日期={run_date}")
    log.info(f"PRD={'已加载 ' + str(prd_path) if context.prd_path else '未提供'}")
    log.info(f"输出目录={daily_folder}")
    log.info(f"{'='*60}\n")

    agent = PlannerAgent(gemini_client=gemini, claude_client=claude, openai_client=openai_)
    output = await agent.run(context)

    # ── 打印成果物 ────────────────────────────────────────────────────────────
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"✅  Planner 完成")
    print(f"  成果物路径  : {output.output_path}")
    print(f"  今日主题摘要: {output.summary}")
    print(f"  辩论轮次    : {output.data.get('rounds', '?')}")
    print(f"  提前收敛    : {output.data.get('agreement', False)}")
    print(sep)

    print(f"\n{'─'*60}")
    print(f"[daily_marketing_plan.md 内容预览]")
    print(f"{'─'*60}")
    plan = output.output_path.read_text(encoding="utf-8")
    print(plan)


if __name__ == "__main__":
    asyncio.run(main())
