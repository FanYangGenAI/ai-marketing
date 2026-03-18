"""
Skill: crop_resize
将图片裁剪并缩放到平台规范尺寸（如小红书 3:4 = 1080x1440）。
基于 Pillow。
"""

from dataclasses import dataclass
from pathlib import Path
from PIL import Image


# 平台预设尺寸
PLATFORM_SIZES = {
    "xiaohongshu_34": (1080, 1440),   # 3:4 竖版
    "xiaohongshu_11": (1080, 1080),   # 1:1 方图
    "douyin":         (1080, 1920),   # 9:16
    "tiktok":         (1080, 1920),   # 9:16
}


@dataclass
class CropResizeResult:
    file_path: str
    width: int
    height: int
    original_size: tuple[int, int]


def crop_resize(
    input_path: str,
    output_path: str,
    target_size: tuple[int, int] | str,
    crop_mode: str = "center",
) -> CropResizeResult:
    """
    裁剪并缩放图片到目标尺寸。

    Args:
        input_path:  原始图片路径
        output_path: 输出路径
        target_size: 目标尺寸 (width, height) 或平台预设 key
                     (如 "xiaohongshu_34")
        crop_mode:   裁剪模式
                     "center" — 居中裁剪（保持比例，裁去多余部分）
                     "fit"    — 等比缩放至目标尺寸内，不裁剪（可能留白）

    Returns:
        CropResizeResult
    """
    if isinstance(target_size, str):
        if target_size not in PLATFORM_SIZES:
            raise ValueError(
                f"Unknown platform size key: {target_size}. "
                f"Available: {list(PLATFORM_SIZES.keys())}"
            )
        target_size = PLATFORM_SIZES[target_size]

    target_w, target_h = target_size
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as img:
        original_size = img.size
        img = img.convert("RGB")

        if crop_mode == "center":
            img = _center_crop(img, target_w, target_h)
        elif crop_mode == "fit":
            img = _fit_resize(img, target_w, target_h)
        else:
            raise ValueError(f"Unknown crop_mode: {crop_mode}")

        img.save(output_path, quality=95)

    return CropResizeResult(
        file_path=output_path,
        width=target_w,
        height=target_h,
        original_size=original_size,
    )


def _center_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """先等比缩放使图片最小边 >= 目标边，再居中裁剪。"""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _fit_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """等比缩放，不裁剪，结果尺寸可能小于目标尺寸。"""
    img.thumbnail((target_w, target_h), Image.LANCZOS)
    return img
