"""单元测试：text-overlay Skill scripts/text_overlay.py（通过 subprocess 调用 CLI）"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


SCRIPT = Path(__file__).parent.parent.parent / "src" / "skills" / "text-overlay" / "scripts" / "text_overlay.py"


@pytest.fixture
def sample_image(tmp_path) -> str:
    img_path = str(tmp_path / "sample.png")
    Image.new("RGB", (1080, 1440), color=(30, 30, 30)).save(img_path)
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


def test_bottom_overlay(sample_image, tmp_path):
    output = str(tmp_path / "out_bottom.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--text", "亲测好用！强烈推荐", "--position", "bottom",
    )
    assert result.returncode == 0, result.stderr
    assert "✅" in result.stdout
    assert Path(output).exists()
    with Image.open(output) as img:
        assert img.size == (1080, 1440)


def test_top_overlay(sample_image, tmp_path):
    output = str(tmp_path / "out_top.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--text", "封面标题", "--position", "top",
    )
    assert result.returncode == 0, result.stderr
    assert Path(output).exists()


def test_center_overlay(sample_image, tmp_path):
    output = str(tmp_path / "out_center.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--text", "居中文字", "--position", "center",
    )
    assert result.returncode == 0, result.stderr
    assert Path(output).exists()


def test_long_text_wraps(sample_image, tmp_path):
    """超长文字应自动换行，不报错。"""
    output = str(tmp_path / "out_long.png")
    long_text = "这是一段很长很长的文字，用来测试自动换行功能是否正常工作，不会超出图片边界范围"
    result = run_script(
        "--input", sample_image, "--output", output,
        "--text", long_text,
    )
    assert result.returncode == 0, result.stderr
    assert Path(output).exists()


def test_output_size_unchanged(sample_image, tmp_path):
    """叠加文字后图片尺寸不变。"""
    output = str(tmp_path / "out.png")
    result = run_script(
        "--input", sample_image, "--output", output,
        "--text", "测试",
    )
    assert result.returncode == 0, result.stderr
    with Image.open(output) as img:
        assert img.size == (1080, 1440)
