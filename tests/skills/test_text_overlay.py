"""单元测试：text_overlay Skill（无需外部依赖）"""

import pytest
from pathlib import Path
from PIL import Image
from src.skills.image_edit.text_overlay import text_overlay


@pytest.fixture
def sample_image(tmp_path) -> str:
    img_path = str(tmp_path / "sample.jpg")
    Image.new("RGB", (1080, 1440), color=(30, 30, 30)).save(img_path)
    return img_path


def test_bottom_overlay(sample_image, tmp_path):
    output = str(tmp_path / "out_bottom.jpg")
    result = text_overlay(sample_image, output, text="亲测好用！强烈推荐", position="bottom")
    assert Path(output).exists()
    assert result.width == 1080
    assert result.height == 1440


def test_top_overlay(sample_image, tmp_path):
    output = str(tmp_path / "out_top.jpg")
    result = text_overlay(sample_image, output, text="封面标题", position="top")
    assert Path(output).exists()


def test_center_overlay(sample_image, tmp_path):
    output = str(tmp_path / "out_center.jpg")
    result = text_overlay(sample_image, output, text="居中文字", position="center")
    assert Path(output).exists()


def test_long_text_wraps(sample_image, tmp_path):
    """超长文字应自动换行，不抛出异常。"""
    output = str(tmp_path / "out_long.jpg")
    long_text = "这是一段很长很长的文字，用来测试自动换行功能是否正常工作，不会超出图片边界"
    result = text_overlay(sample_image, output, text=long_text)
    assert Path(output).exists()


def test_output_size_unchanged(sample_image, tmp_path):
    """叠加文字后图片尺寸不变。"""
    output = str(tmp_path / "out.jpg")
    text_overlay(sample_image, output, text="测试")
    with Image.open(output) as img:
        assert img.size == (1080, 1440)
