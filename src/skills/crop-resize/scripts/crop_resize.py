#!/usr/bin/env python3
"""
crop-resize Skill — 图片裁剪缩放脚本
由 Director Agent 通过 bash 调用。
用法见 SKILL.md。
"""

import argparse
import sys
from pathlib import Path

from PIL import Image

PLATFORM_PRESETS = {
    "xiaohongshu_34": (1080, 1440),
    "xiaohongshu_11": (1080, 1080),
    "douyin": (1080, 1920),
    "tiktok": (1080, 1920),
}


def parse_size(size_str: str) -> tuple[int, int]:
    """解析 --size 参数：平台 key 或 '宽x高' 格式。"""
    if size_str in PLATFORM_PRESETS:
        return PLATFORM_PRESETS[size_str]
    if "x" in size_str:
        parts = size_str.lower().split("x")
        if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
            return int(parts[0].strip()), int(parts[1].strip())
    raise ValueError(
        f"无效的 --size 值: '{size_str}'。"
        f"请使用平台 key（{list(PLATFORM_PRESETS)}）或 '宽x高' 格式（如 1080x1440）。"
    )


def crop_center(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """先缩放使图片覆盖目标尺寸，再居中裁剪。"""
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def fit_scale(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """等比缩放至目标尺寸内，不裁剪，可能有留白（白色背景）。"""
    orig_w, orig_h = img.size
    scale = min(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return canvas


def process(input_path: str, output_path: str, size_str: str, mode: str) -> None:
    target_w, target_h = parse_size(size_str)

    img = Image.open(input_path).convert("RGB")

    if mode == "center":
        result = crop_center(img, target_w, target_h)
    elif mode == "fit":
        result = fit_scale(img, target_w, target_h)
    else:
        raise ValueError(f"无效的 --mode 值: '{mode}'。请使用 'center' 或 'fit'。")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)
    print(f"✅ Cropped image saved: {output_path} ({result.size[0]}x{result.size[1]}px)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop and resize image to platform dimensions")
    parser.add_argument("--input", required=True, help="原始图片路径")
    parser.add_argument("--output", required=True, help="输出路径")
    parser.add_argument(
        "--size",
        required=True,
        help="平台 key（xiaohongshu_34/xiaohongshu_11/douyin/tiktok）或 '宽x高'",
    )
    parser.add_argument(
        "--mode",
        default="center",
        choices=["center", "fit"],
        help="裁剪模式：center（居中裁剪，默认）/ fit（等比缩放留白）",
    )
    args = parser.parse_args()

    try:
        process(args.input, args.output, args.size, args.mode)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
