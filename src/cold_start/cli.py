"""CLI entry for cold-start understanding job (subprocess from FastAPI)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure repo root on path when run as -m src.cold_start.cli
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.cold_start.understanding import run_cold_start_understanding


def main() -> None:
    parser = argparse.ArgumentParser(description="Cold-start product understanding")
    parser.add_argument(
        "--campaign-root",
        type=Path,
        required=True,
        help="Absolute path to campaigns/{product}",
    )
    args = parser.parse_args()
    asyncio.run(run_cold_start_understanding(args.campaign_root))


if __name__ == "__main__":
    main()
