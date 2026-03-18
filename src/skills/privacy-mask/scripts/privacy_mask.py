#!/usr/bin/env python3
"""
privacy-mask Skill — 隐私马赛克脚本
由 Director Agent 通过 bash 调用。
用法见 SKILL.md。
"""

import argparse
import sys
from pathlib import Path

from PIL import Image


def parse_region(region_str: str) -> tuple[int, int, int, int]:
    """解析 'x,y,width,height' 格式的区域字符串。"""
    parts = region_str.split(",")
    if len(parts) != 4:
        raise ValueError(
            f"区域格式错误: '{region_str}'，应为 'x,y,width,height'（如 '120,80,200,60'）"
        )
    try:
        x, y, w, h = (int(p.strip()) for p in parts)
    except ValueError:
        raise ValueError(f"区域坐标必须是整数: '{region_str}'")
    if w <= 0 or h <= 0:
        raise ValueError(f"区域宽高必须大于 0: '{region_str}'")
    return x, y, w, h


def mosaic_region(img: Image.Image, x: int, y: int, w: int, h: int, block_size: int) -> Image.Image:
    """
    对图片指定区域应用马赛克效果（缩小再放大）。
    坐标会自动 clamp 到图片边界内。
    """
    img_w, img_h = img.size

    # Clamp 到图片边界
    x1 = max(0, min(x, img_w))
    y1 = max(0, min(y, img_h))
    x2 = max(0, min(x + w, img_w))
    y2 = max(0, min(y + h, img_h))

    if x2 <= x1 or y2 <= y1:
        return img  # 区域完全在图外，跳过

    region = img.crop((x1, y1, x2, y2))
    region_w, region_h = region.size

    # 防止缩小后尺寸为 0
    small_w = max(1, region_w // block_size)
    small_h = max(1, region_h // block_size)

    small = region.resize((small_w, small_h), Image.BOX)
    mosaic = small.resize((region_w, region_h), Image.NEAREST)

    result = img.copy()
    result.paste(mosaic, (x1, y1))
    return result


def process(
    input_path: str,
    output_path: str,
    regions: list[str],
    block_size: int,
) -> None:
    img = Image.open(input_path).convert("RGB")
    masked_count = 0

    for region_str in regions:
        x, y, w, h = parse_region(region_str)
        img = mosaic_region(img, x, y, w, h, block_size)
        masked_count += 1
        print(f"  ✓ 遮挡区域: ({x}, {y}, {w}x{h})")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    print(
        f"✅ Privacy mask applied: {output_path} "
        f"({masked_count} region(s), block_size={block_size})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply mosaic privacy mask to image regions")
    parser.add_argument("--input", required=True, help="原始图片路径")
    parser.add_argument("--output", required=True, help="输出路径")
    parser.add_argument(
        "--regions",
        required=True,
        nargs="+",
        metavar="x,y,w,h",
        help="一个或多个区域，格式 x,y,width,height",
    )
    parser.add_argument("--block-size", type=int, default=15, help="马赛克块大小，默认 15")
    args = parser.parse_args()

    if args.block_size < 2:
        print("❌ --block-size 必须 >= 2", file=sys.stderr)
        sys.exit(1)

    try:
        process(args.input, args.output, args.regions, args.block_size)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
