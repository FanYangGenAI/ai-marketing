"""单元测试：privacy-mask Skill scripts/privacy_mask.py（通过 subprocess 调用 CLI）"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


SCRIPT = Path(__file__).parent.parent.parent / "src" / "skills" / "privacy-mask" / "scripts" / "privacy_mask.py"


@pytest.fixture
def sample_image(tmp_path) -> str:
    """生成一张含多色"敏感区域"的测试图片（非均匀颜色，便于验证马赛克效果）。"""
    img = Image.new("RGB", (1080, 1440), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    # 绘制左半红色、右半蓝色，确保区域颜色不均匀
    draw.rectangle([100, 200, 250, 280], fill=(255, 0, 0))
    draw.rectangle([250, 200, 400, 280], fill=(0, 0, 255))
    path = str(tmp_path / "sample.png")
    img.save(path)
    return path


def run_script(*args) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_single_region_mosaic(sample_image, tmp_path):
    output = str(tmp_path / "out_mosaic.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--regions", "100,200,300,80",
    )
    assert result.returncode == 0, result.stderr
    assert "✅" in result.stdout
    assert Path(output).exists()
    # 打码后原来的红色区域应该不再是纯红
    with Image.open(output) as img:
        pixel = img.getpixel((250, 240))
        assert pixel != (255, 0, 0)


def test_multiple_regions(sample_image, tmp_path):
    output = str(tmp_path / "out_multi.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--regions", "100,200,300,80", "500,800,200,60",
    )
    assert result.returncode == 0, result.stderr
    assert "2 region(s)" in result.stdout


def test_custom_block_size(sample_image, tmp_path):
    output = str(tmp_path / "out_block.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--regions", "100,200,300,80",
        "--block-size", "5",
    )
    assert result.returncode == 0, result.stderr
    assert Path(output).exists()


def test_region_clamped_to_bounds(sample_image, tmp_path):
    """区域超出图片边界时应自动 clamp，不报错。"""
    output = str(tmp_path / "out_clamp.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--regions", "900,1300,500,500",  # 超出 1080x1440
    )
    assert result.returncode == 0, result.stderr
    assert Path(output).exists()


def test_invalid_region_format(sample_image, tmp_path):
    output = str(tmp_path / "x.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--regions", "invalid",
    )
    assert result.returncode != 0
    assert "❌" in result.stderr or "Error" in result.stderr


def test_invalid_block_size(sample_image, tmp_path):
    output = str(tmp_path / "x.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--regions", "100,200,300,80",
        "--block-size", "1",  # 必须 >= 2
    )
    assert result.returncode != 0
