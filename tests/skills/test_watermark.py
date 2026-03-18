"""单元测试：watermark Skill（无需外部依赖）"""

import pytest
from pathlib import Path
from PIL import Image
from src.skills.image_edit.watermark import privacy_mask, Region


@pytest.fixture
def sample_image(tmp_path) -> str:
    img = Image.new("RGB", (1080, 1440), color=(200, 200, 200))
    # 画一个"敏感区域"（红色矩形）
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 200, 400, 280], fill=(255, 0, 0))
    path = str(tmp_path / "sample.jpg")
    img.save(path)
    return path


def test_blur_mask(sample_image, tmp_path):
    output = str(tmp_path / "out_blur.jpg")
    region = Region(x=100, y=200, width=300, height=80)
    result = privacy_mask(sample_image, output, [region], method="blur")
    assert Path(output).exists()
    assert result.regions_count == 1
    # 打码后原来的红色区域应该不再是纯红
    with Image.open(output) as img:
        pixel = img.getpixel((250, 240))  # 区域中心
        assert pixel != (255, 0, 0)


def test_mosaic_mask(sample_image, tmp_path):
    output = str(tmp_path / "out_mosaic.jpg")
    region = Region(x=100, y=200, width=300, height=80)
    result = privacy_mask(sample_image, output, [region], method="mosaic")
    assert Path(output).exists()


def test_fill_mask(sample_image, tmp_path):
    output = str(tmp_path / "out_fill.jpg")
    region = Region(x=100, y=200, width=300, height=80)
    fill_color = (180, 180, 180)
    result = privacy_mask(sample_image, output, [region], method="fill", fill_color=fill_color)
    assert Path(output).exists()
    with Image.open(output) as img:
        pixel = img.getpixel((250, 240))
        assert pixel == fill_color


def test_multiple_regions(sample_image, tmp_path):
    output = str(tmp_path / "out_multi.jpg")
    regions = [
        Region(x=10, y=10, width=100, height=50),
        Region(x=500, y=800, width=200, height=60),
    ]
    result = privacy_mask(sample_image, output, regions, method="fill")
    assert result.regions_count == 2


def test_invalid_method(sample_image, tmp_path):
    with pytest.raises(ValueError, match="Unknown method"):
        privacy_mask(
            sample_image,
            str(tmp_path / "x.jpg"),
            [Region(0, 0, 10, 10)],
            method="pixelate",
        )
