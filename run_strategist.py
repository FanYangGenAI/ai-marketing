"""
Strategist 全链路 runner。
用法：python run_strategist.py
"""

import asyncio
import io
import json
import sys
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from src.agents.base import AgentContext, next_attempt_id
from src.agents.strategist.strategist import StrategistAgent
from src.llm.client_factory import build_llm_client

CAMPAIGN_ROOT = Path("campaigns/原语")
RUN_DATE = date.today()
TODAY_NOTE = "聚焦跨文化沟通痛点，尝试用真实场景故事切入"

# ── 模型配置 ──────────────────────────────────────────────────────────────────
# Strategist A   → gemini-2.5-flash
# Strategist B   → gpt-4.1
# Moderator      → gemini-2.5-pro    (更强推理，裁定用)
# 注：用户提到 "gemini-3.1"，该版本目前不存在，使用 gemini-2.5-pro 代替。
MODEL_ANALYST    = "gemini-2.5-flash"
MODEL_CREATIVE   = "gpt-4.1"
MODEL_MODERATOR  = "gemini-2.5-flash"   # gemini-2.5-pro 目前 503，暂用 flash
ROUND1_TEMPERATURE = 1.0
DISCUSSION_TEMPERATURE = 0.0


async def main() -> None:
    cfg = json.loads((CAMPAIGN_ROOT / "config" / "product_config.json").read_text(encoding="utf-8"))

    daily_folder = CAMPAIGN_ROOT / "daily" / RUN_DATE.strftime("%Y-%m-%d")
    daily_folder.mkdir(parents=True, exist_ok=True)

    attempts_dir = daily_folder / "strategy" / "attempts"
    attempt_id = next_attempt_id(attempts_dir)

    context = AgentContext(
        campaign_root=CAMPAIGN_ROOT,
        daily_folder=daily_folder,
        run_date=RUN_DATE,
        product_name="原语",
        user_brief=cfg.get("user_brief", ""),
        user_note=TODAY_NOTE,
        extra={"attempt_id": attempt_id},
    )

    agent = StrategistAgent(
        strategist_a_client=build_llm_client(MODEL_ANALYST),
        strategist_b_client=build_llm_client(MODEL_CREATIVE),
        moderator_client=build_llm_client(MODEL_MODERATOR),
        platform="xiaohongshu",
        round1_temperature=ROUND1_TEMPERATURE,
        discussion_temperature=DISCUSSION_TEMPERATURE,
    )

    print(f"Models  : analyst={MODEL_ANALYST} | creative={MODEL_CREATIVE} | moderator={MODEL_MODERATOR}")
    print(f"Temp    : round1={ROUND1_TEMPERATURE} | discussion={DISCUSSION_TEMPERATURE}")
    print(f"Date    : {RUN_DATE}")
    print(f"Attempt : {attempt_id} -> {attempts_dir / attempt_id}")
    print(f"Note    : {TODAY_NOTE}\n")

    result = await agent.run(context)

    print("=" * 60)
    print(f"Summary : {result.summary}")
    print(f"Data    : {json.dumps(result.data, ensure_ascii=False, indent=2)}")
    print("=" * 60)
    print(f"\nStrategy → {result.output_path}\n")
    print(result.read_text())


if __name__ == "__main__":
    asyncio.run(main())
