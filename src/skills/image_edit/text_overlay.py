"""
Skill: text_overlay
在图片上叠加文字（封面标题、说明等）。
基于 Pillow。支持自动换行、多行文字、背景色条。
"""

from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


@dataclass
class TextOverlayResult:
    file_path: str
    width: int
    height: int


def text_overlay(
    input_path: str,
    output_path: str,
    text: str,
    position: str = "bottom",
    font_size: int = 56,
    font_color: tuple[int, int, int] = (255, 255, 255),
    bg_color: tuple[int, int, int, int] = (0, 0, 0, 160),
    padding: int = 30,
    font_path: str | None = None,
    max_width_ratio: float = 0.85,
) -> TextOverlayResult:
    """
    在图片上叠加文字。

    Args:
        input_path:      原始图片
        output_path:     输出路径
        text:            要叠加的文字
        position:        文字位置："top" | "bottom" | "center"
        font_size:       字体大小（px）
        font_color:      字体颜色 RGB
        bg_color:        背景色条 RGBA（含透明度）
        padding:         文字区域内边距（px）
        font_path:       自定义字体路径（None 则使用系统默认）
        max_width_ratio: 文字最大宽度占图片宽度比例（超出自动换行）

    Returns:
        TextOverlayResult
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path).convert("RGBA") as img:
        w, h = img.size

        # 加载字体
        try:
            font = (
                ImageFont.truetype(font_path, font_size)
                if font_path
                else ImageFont.truetype(_find_cjk_font(), font_size)
            )
        except (IOError, OSError):
            font = ImageFont.load_default()

        # 自动换行
        max_text_width = int(w * max_width_ratio)
        lines = _wrap_text(text, font, max_text_width)

        # 计算文字区域高度
        line_height = font_size + 8
        text_block_h = len(lines) * line_height + padding * 2

        # 创建半透明背景层
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if position == "bottom":
            bar_top = h - text_block_h
            bar_bottom = h
        elif position == "top":
            bar_top = 0
            bar_bottom = text_block_h
        else:  # center
            bar_top = (h - text_block_h) // 2
            bar_bottom = bar_top + text_block_h

        draw.rectangle([(0, bar_top), (w, bar_bottom)], fill=bg_color)

        # 绘制文字
        y = bar_top + padding
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (w - line_w) // 2
            draw.text((x, y), line, font=font, fill=font_color)
            y += line_height

        # 合并图层
        result = Image.alpha_composite(img, overlay).convert("RGB")
        result.save(output_path, quality=95)

    return TextOverlayResult(
        file_path=output_path,
        width=w,
        height=h,
    )


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """将文字按最大宽度自动换行。"""
    # 尝试整行，如果超宽则逐字符拆分（中文友好）
    dummy_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_img)

    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _find_cjk_font() -> str:
    """尝试找到系统中可用的 CJK 字体。"""
    candidates = [
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for path in candidates:
        try:
            ImageFont.truetype(path, 10)
            return path
        except (IOError, OSError):
            continue
    raise IOError("No CJK font found. Please specify font_path manually.")
