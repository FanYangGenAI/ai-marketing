"""
Skill: watermark
对图片中的隐私区域进行打码（马赛克/模糊/纯色遮挡）。
用于截图中遮挡用户姓名、手机号、邮箱等敏感信息。
基于 Pillow + OpenCV。
"""

from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageFilter


@dataclass
class Region:
    """需要打码的区域（像素坐标）。"""
    x: int       # 左上角 x
    y: int       # 左上角 y
    width: int
    height: int


@dataclass
class WatermarkResult:
    file_path: str
    regions_count: int


def privacy_mask(
    input_path: str,
    output_path: str,
    regions: list[Region],
    method: str = "blur",
    blur_radius: int = 20,
    mosaic_block: int = 15,
    fill_color: tuple[int, int, int] = (180, 180, 180),
) -> WatermarkResult:
    """
    对指定区域进行隐私打码。

    Args:
        input_path:    原始图片
        output_path:   输出路径
        regions:       需要打码的区域列表
        method:        打码方式："blur"（高斯模糊）| "mosaic"（马赛克）| "fill"（纯色填充）
        blur_radius:   模糊半径（method="blur" 时有效）
        mosaic_block:  马赛克块大小 px（method="mosaic" 时有效）
        fill_color:    填充颜色 RGB（method="fill" 时有效）

    Returns:
        WatermarkResult
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if method == "blur":
        _blur_regions(input_path, output_path, regions, blur_radius)
    elif method == "mosaic":
        _mosaic_regions(input_path, output_path, regions, mosaic_block)
    elif method == "fill":
        _fill_regions(input_path, output_path, regions, fill_color)
    else:
        raise ValueError(f"Unknown method: {method}. Use 'blur', 'mosaic', or 'fill'.")

    return WatermarkResult(file_path=output_path, regions_count=len(regions))


# ── 实现方法 ──────────────────────────────────────────────────────────────────

def _blur_regions(
    input_path: str, output_path: str, regions: list[Region], radius: int
) -> None:
    """高斯模糊打码。"""
    with Image.open(input_path).convert("RGB") as img:
        for r in regions:
            box = (r.x, r.y, r.x + r.width, r.y + r.height)
            region_img = img.crop(box)
            blurred = region_img.filter(ImageFilter.GaussianBlur(radius=radius))
            img.paste(blurred, box)
        img.save(output_path, quality=95)


def _mosaic_regions(
    input_path: str, output_path: str, regions: list[Region], block_size: int
) -> None:
    """马赛克打码（Pillow 实现，缩小再放大）。"""
    with Image.open(input_path).convert("RGB") as img:
        for r in regions:
            box = (r.x, r.y, r.x + r.width, r.y + r.height)
            roi = img.crop(box)
            w, h = roi.size
            if w == 0 or h == 0:
                continue
            # 缩小再放大 → 马赛克效果
            small_w = max(1, w // block_size)
            small_h = max(1, h // block_size)
            small = roi.resize((small_w, small_h), Image.NEAREST)
            mosaic = small.resize((w, h), Image.NEAREST)
            img.paste(mosaic, box)
        img.save(output_path, quality=95)


def _fill_regions(
    input_path: str, output_path: str, regions: list[Region], color: tuple[int, int, int]
) -> None:
    """纯色矩形填充。"""
    from PIL import ImageDraw
    with Image.open(input_path).convert("RGB") as img:
        draw = ImageDraw.Draw(img)
        for r in regions:
            draw.rectangle(
                [r.x, r.y, r.x + r.width, r.y + r.height],
                fill=color,
            )
        img.save(output_path, quality=95)
