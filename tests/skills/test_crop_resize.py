"""单元测试：crop_resize Skill（无需外部依赖）"""

import pytest
from pathlib import Path
from PIL import Image
from src.skills.image_edit.crop_resize import crop_resize, PLATFORM_SIZES


@pytest.fixture
def sample_image(tmp_path) -> str:
    """生成一张 800x600 的测试图片。"""
    img_path = str(tmp_path / "sample.jpg")
    Image.new("RGB", (800, 600), color=(100, 149, 237)).save(img_path)
    return img_path


def test_center_crop_to_xiaohongshu_34(sample_image, tmp_path):
    output = str(tmp_path / "out.jpg")
    result = crop_resize(sample_image, output, "xiaohongshu_34", crop_mode="center")
    assert result.width == 1080
    assert result.height == 1440
    assert Path(output).exists()
    with Image.open(output) as img:
        assert img.size == (1080, 1440)


def test_center_crop_to_xiaohongshu_11(sample_image, tmp_path):
    output = str(tmp_path / "out_11.jpg")
    result = crop_resize(sample_image, output, "xiaohongshu_11")
    assert result.width == 1080
    assert result.height == 1080


def test_fit_resize(sample_image, tmp_path):
    output = str(tmp_path / "out_fit.jpg")
    result = crop_resize(sample_image, output, (400, 300), crop_mode="fit")
    with Image.open(output) as img:
        w, h = img.size
        assert w <= 400 and h <= 300


def test_custom_tuple_size(sample_image, tmp_path):
    output = str(tmp_path / "out_custom.jpg")
    result = crop_resize(sample_image, output, (720, 960))
    assert result.width == 720
    assert result.height == 960


def test_invalid_platform_key(sample_image, tmp_path):
    with pytest.raises(ValueError, match="Unknown platform size key"):
        crop_resize(sample_image, str(tmp_path / "x.jpg"), "unknown_platform")


def test_invalid_crop_mode(sample_image, tmp_path):
    with pytest.raises(ValueError, match="Unknown crop_mode"):
        crop_resize(sample_image, str(tmp_path / "x.jpg"), (1080, 1440), crop_mode="stretch")
