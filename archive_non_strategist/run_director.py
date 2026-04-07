#!/usr/bin/env python3
"""
单独运行 Director Agent，便于逐步验收。
用法：python run_director.py --product 原语
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

import io
handler = logging.StreamHandler(
    stream=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
)
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
))
logging.basicConfig(level=logging.INFO, handlers=[handler])
log = logging.getLogger("run_director")

for noisy in ("httpx", "httpcore", "openai._base_client", "anthropic._base_client"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", default="原语")
    args = parser.parse_args()

    import json

    from src.agents.director.director import DirectorAgent
    from src.agents.base import AgentContext
    from src.llm.client_factory import build_llm_client

    cfg_path = Path(__file__).parent / "src" / "config" / "llm_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    director_model = cfg.get("director", "gemini-2.5-flash")
    log.info("初始化 Director LLM（%s）...", director_model)
    llm = build_llm_client(director_model)

    product = args.product
    run_date = date.today()
    campaign_root = Path("campaigns") / product
    daily_folder = campaign_root / "daily" / run_date.strftime("%Y-%m-%d")
    daily_folder.mkdir(parents=True, exist_ok=True)

    context = AgentContext(
        campaign_root=campaign_root,
        daily_folder=daily_folder,
        run_date=run_date,
        product_name=product,
    )

    log.info(f"\n{'='*60}")
    log.info(f"启动 Director  产品={product}  日期={run_date}")
    log.info(f"输出目录={daily_folder}")
    log.info(f"{'='*60}\n")

    agent = DirectorAgent(llm_client=llm)
    output = await agent.run(context)

    print(f"\n{'='*60}")
    print(f"{'✅' if output.success else '❌'}  Director 完成")
    print(f"  摘要: {output.summary}")
    if output.output_path:
        print(f"  结果: {output.output_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
