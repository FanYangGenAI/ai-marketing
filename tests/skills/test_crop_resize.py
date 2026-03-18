"""单元测试：crop-resize Skill scripts/crop_resize.py（通过 subprocess 调用 CLI）"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


SCRIPT = Path(__file__).parent.parent.parent / "src" / "skills" / "crop-resize" / "scripts" / "crop_resize.py"


@pytest.fixture
def sample_image(tmp_path) -> str:
    """生成一张 800x600 的测试图片。"""
    img_path = str(tmp_path / "sample.jpg")
    Image.new("RGB", (800, 600), color=(100, 149, 237)).save(img_path)
    return img_path


def run_script(*args) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_center_crop_to_xiaohongshu_34(sample_image, tmp_path):
    output = str(tmp_path / "out_34.jpg")
    result = run_script("--input", sample_image, "--output", output, "--size", "xiaohongshu_34")
    assert result.returncode == 0, result.stderr
    assert "✅" in result.stdout
    with Image.open(output) as img:
        assert img.size == (1080, 1440)


def test_center_crop_to_xiaohongshu_11(sample_image, tmp_path):
    output = str(tmp_path / "out_11.jpg")
    result = run_script("--input", sample_image, "--output", output, "--size", "xiaohongshu_11")
    assert result.returncode == 0, result.stderr
    with Image.open(output) as img:
        assert img.size == (1080, 1080)


def test_fit_mode(sample_image, tmp_path):
    output = str(tmp_path / "out_fit.jpg")
    result = run_script(
        "--input", sample_image, "--output", output, "--size", "1080x1440", "--mode", "fit"
    )
    assert result.returncode == 0, result.stderr
    with Image.open(output) as img:
        assert img.size == (1080, 1440)


def test_custom_size(sample_image, tmp_path):
    output = str(tmp_path / "out_custom.jpg")
    result = run_script("--input", sample_image, "--output", output, "--size", "720x960")
    assert result.returncode == 0, result.stderr
    with Image.open(output) as img:
        assert img.size == (720, 960)


def test_invalid_platform_key(sample_image, tmp_path):
    output = str(tmp_path / "x.jpg")
    result = run_script("--input", sample_image, "--output", output, "--size", "unknown_platform")
    assert result.returncode != 0
    assert "❌" in result.stderr or "Error" in result.stderr


def test_invalid_mode(sample_image, tmp_path):
    output = str(tmp_path / "x.jpg")
    result = run_script(
        "--input", sample_image, "--output", output, "--size", "xiaohongshu_34", "--mode", "stretch"
    )
    # argparse 会直接拒绝无效的 choices
    assert result.returncode != 0
