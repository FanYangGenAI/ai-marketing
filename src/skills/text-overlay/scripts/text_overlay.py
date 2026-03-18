#!/usr/bin/env python3
"""
text-overlay Skill — 文字叠加脚本
由 Director Agent 通过 bash 调用。
用法见 SKILL.md。
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def parse_color(hex_color: str) -> tuple[int, int, int, int]:
    """
    解析十六进制颜色字符串，返回 RGBA 元组。
    支持 #RGB、#RRGGBB、#RRGGBBAA 格式。
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    if len(hex_color) == 6:
        hex_color += "FF"
    if len(hex_color) != 8:
        raise ValueError(f"无效颜色格式: #{hex_color}，请使用 #RRGGBB 或 #RRGGBBAA")
    r, g, b, a = (int(hex_color[i:i+2], 16) for i in (0, 2, 4, 6))
    return r, g, b, a


def load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """加载字体，若路径无效则回退到 Pillow 默认字体。"""
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            print(f"⚠️  字体文件未找到: {font_path}，使用默认字体", file=sys.stderr)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Pillow < 10.0 的 load_default 不支持 size 参数
        return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """将文字按最大宽度自动换行。"""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = list(paragraph)  # 中文按字符分割
        current_line = ""
        for char in words:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
    return lines


def calculate_text_block_size(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    draw: ImageDraw.ImageDraw,
    line_spacing: int,
) -> tuple[int, int]:
    """计算多行文字块的总宽高。"""
    max_w = 0
    total_h = 0
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_w = max(max_w, w)
        total_h += h
        if i < len(lines) - 1:
            total_h += line_spacing
    return max_w, total_h


def overlay_text(
    input_path: str,
    output_path: str,
    text: str,
    position: str,
    font_path: str | None,
    font_size: int,
    color: str,
    bg_color: str,
    padding: int,
    line_spacing: int,
    max_width: int | None,
) -> None:
    img = Image.open(input_path).convert("RGBA")
    img_w, img_h = img.size

    effective_max_width = max_width if max_width else (img_w - 2 * padding)

    font = load_font(font_path, font_size)
    text_color = parse_color(color)
    bg_rgba = parse_color(bg_color)

    # 创建透明绘图层（用于文字及背景）
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    lines = wrap_text(text, font, effective_max_width, draw)
    text_w, text_h = calculate_text_block_size(lines, font, draw, line_spacing)

    # 计算文字块起始位置
    x = (img_w - text_w) // 2
    if position == "top":
        y = padding
    elif position == "bottom":
        y = img_h - text_h - padding * 2
    elif position == "center":
        y = (img_h - text_h) // 2
    else:
        raise ValueError(f"无效的 --position 值: '{position}'，请使用 top / bottom / center")

    # 绘制半透明背景矩形
    bg_x1 = x - padding
    bg_y1 = y - padding // 2
    bg_x2 = x + text_w + padding
    bg_y2 = y + text_h + padding // 2
    draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=bg_rgba)

    # 逐行绘制文字
    cursor_y = y
    for line in lines:
        draw.text((x, cursor_y), line, font=font, fill=text_color)
        bbox = draw.textbbox((0, 0), line, font=font)
        line_h = bbox[3] - bbox[1]
        cursor_y += line_h + line_spacing

    # 合并到原图
    result = Image.alpha_composite(img, overlay).convert("RGB")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)
    print(f"✅ Text overlay saved: {output_path} ({result.size[0]}x{result.size[1]}px)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Overlay text on an image")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--position", default="top", choices=["top", "bottom", "center"])
    parser.add_argument("--font", default=None)
    parser.add_argument("--font-size", type=int, default=48)
    parser.add_argument("--color", default="#FFFFFF")
    parser.add_argument("--bg-color", default="#00000080")
    parser.add_argument("--padding", type=int, default=20)
    parser.add_argument("--line-spacing", type=int, default=8)
    parser.add_argument("--max-width", type=int, default=None)
    args = parser.parse_args()

    try:
        overlay_text(
            input_path=args.input,
            output_path=args.output,
            text=args.text,
            position=args.position,
            font_path=args.font,
            font_size=args.font_size,
            color=args.color,
            bg_color=args.bg_color,
            padding=args.padding,
            line_spacing=args.line_spacing,
            max_width=args.max_width,
        )
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
