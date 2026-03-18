#!/usr/bin/env python3
"""
AI Marketing Multi-Agent System — CLI 入口

用法示例：
  # 运行今天的完整流程
  python main.py --product MyApp --prd docs/prd.md

  # 指定日期
  python main.py --product MyApp --date 2026-03-17 --prd docs/prd.md

  # 从某个阶段续跑（跳过已完成阶段）
  python main.py --product MyApp --date 2026-03-17 --from-step scriptwriter

  # 仅打印执行计划，不实际运行
  python main.py --product MyApp --dry-run

  # 带用户备注
  python main.py --product MyApp --note "今天重点推新功能 XX"
"""

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

# Windows UTF-8 兼容：确保 stdout/stderr 可以输出中文和 emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent))

# 加载 .env（override=True 确保 .env 的值覆盖系统中的同名空变量）
from dotenv import load_dotenv
load_dotenv(override=True)

from src.orchestrator.pipeline import Pipeline, STEPS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Marketing Multi-Agent System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--product", required=True,
        help="产品名称（对应 campaigns/{product}/ 目录）"
    )
    parser.add_argument(
        "--date", default=None,
        help="执行日期，格式 YYYY-MM-DD，默认今天"
    )
    parser.add_argument(
        "--prd", default=None, type=Path,
        help="产品 PRD 文件路径（.md 或 .txt）"
    )
    parser.add_argument(
        "--note", default="",
        help="用户当日备注（临时想法、特殊要求等）"
    )
    parser.add_argument(
        "--from-step", default=None, choices=STEPS,
        help=f"从指定阶段开始，跳过前置阶段。可选：{STEPS}"
    )
    parser.add_argument(
        "--platform", default="xiaohongshu",
        help="目标发布平台，默认 xiaohongshu"
    )
    parser.add_argument(
        "--campaigns-root", default="campaigns", type=Path,
        help="campaigns 根目录，默认 ./campaigns"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅打印执行计划，不实际运行"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="显示详细日志"
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # 日志配置（强制 UTF-8，兼容 Windows 控制台）
    import io
    level = logging.DEBUG if args.verbose else logging.INFO
    handler = logging.StreamHandler(
        stream=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    )
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.basicConfig(level=level, handlers=[handler])
    log = logging.getLogger("main")

    # 解析日期
    run_date = date.today()
    if args.date:
        try:
            run_date = date.fromisoformat(args.date)
        except ValueError:
            log.error(f"日期格式错误: {args.date}，请使用 YYYY-MM-DD")
            sys.exit(1)

    # 验证 PRD 路径
    prd_path = None
    if args.prd:
        prd_path = args.prd.resolve()
        if not prd_path.exists():
            log.warning(f"PRD 文件未找到: {prd_path}，将跳过 PRD 读取")
            prd_path = None

    log.info(f"🚀 启动 AI Marketing Pipeline")
    log.info(f"   产品：{args.product}")
    log.info(f"   日期：{run_date}")
    log.info(f"   平台：{args.platform}")
    if prd_path:
        log.info(f"   PRD：{prd_path}")

    # 初始化并运行 Pipeline
    pipeline = Pipeline(
        product_name=args.product,
        campaigns_root=args.campaigns_root,
        platform=args.platform,
    )

    try:
        results = await pipeline.run(
            run_date=run_date,
            prd_path=prd_path,
            user_note=args.note,
            from_step=args.from_step,
            dry_run=args.dry_run,
        )
    except Exception as e:
        log.error(f"Pipeline 执行失败：{e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    if not args.dry_run:
        # 打印汇总
        print(f"\n{'='*60}")
        print(f"Pipeline 执行完毕 — {run_date}")
        for step, output in results.items():
            icon = "✅" if output.success else "⚠️"
            print(f"  {icon} {step:<14} {output.summary}")
        print(f"{'='*60}")

        # 检查最终输出
        final_dir = args.campaigns_root / args.product / "daily" / run_date.strftime("%Y-%m-%d") / "output" / "final"
        if final_dir.exists() and any(final_dir.iterdir()):
            print(f"\n📦 最终物料目录：{final_dir}")
        else:
            print(f"\n⚠️  最终物料未生成（可能审核未通过），请查看 audit_result.json")


if __name__ == "__main__":
    asyncio.run(main())
