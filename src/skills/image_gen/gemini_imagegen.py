"""
Skill: gemini_imagegen
三级降级策略生成图片：
  Level 1 (首选): Playwright 操作 Gemini Web
  Level 2 (降级): Gemini CLI
  Level 3 (兜底): Gemini API (google-generativeai)
"""

import os
import asyncio
import subprocess
import base64
import logging
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ImageGenMethod(Enum):
    WEB = "gemini_web"
    CLI = "gemini_cli"
    API = "gemini_api"


@dataclass
class ImageGenResult:
    file_path: str
    method: ImageGenMethod
    prompt: str
    width: int
    height: int


async def gemini_imagegen(
    prompt: str,
    output_path: str,
    size: str = "1080x1440",
    style_hint: str = "小红书风格，高质量，真实感强",
) -> ImageGenResult:
    """
    调用 Gemini 生成图片，自动降级。

    Args:
        prompt:      图片描述
        output_path: 保存路径（含文件名，如 .../assets/raw/gen_01.png）
        size:        目标尺寸，格式 "宽x高"（最终由 crop_resize 保证）
        style_hint:  风格补充描述

    Returns:
        ImageGenResult
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    full_prompt = f"{prompt}，{style_hint}"
    width, height = (int(x) for x in size.split("x"))

    # Level 1: Gemini Web via Playwright
    try:
        result = await _gemini_web(full_prompt, output_path)
        logger.info(f"[gemini_imagegen] Level 1 (Web) succeeded: {output_path}")
        return ImageGenResult(
            file_path=output_path,
            method=ImageGenMethod.WEB,
            prompt=full_prompt,
            width=width,
            height=height,
        )
    except Exception as e:
        logger.warning(f"[gemini_imagegen] Level 1 (Web) failed: {e}. Falling back to CLI.")

    # Level 2: Gemini CLI
    try:
        result = await _gemini_cli(full_prompt, output_path)
        logger.info(f"[gemini_imagegen] Level 2 (CLI) succeeded: {output_path}")
        return ImageGenResult(
            file_path=output_path,
            method=ImageGenMethod.CLI,
            prompt=full_prompt,
            width=width,
            height=height,
        )
    except Exception as e:
        logger.warning(f"[gemini_imagegen] Level 2 (CLI) failed: {e}. Falling back to API.")

    # Level 3: Gemini API
    await _gemini_api(full_prompt, output_path)
    logger.info(f"[gemini_imagegen] Level 3 (API) succeeded: {output_path}")
    return ImageGenResult(
        file_path=output_path,
        method=ImageGenMethod.API,
        prompt=full_prompt,
        width=width,
        height=height,
    )


# ── Level 1: Playwright 操作 Gemini Web ──────────────────────────────────────

async def _gemini_web(prompt: str, output_path: str) -> None:
    """通过 Playwright 操作 Gemini Web 生成图片并下载。"""
    from playwright.async_api import async_playwright

    auth_state = os.environ.get(
        "GEMINI_AUTH_STATE", "src/config/gemini_auth.json"
    )
    if not Path(auth_state).exists():
        raise FileNotFoundError(
            f"Gemini auth state not found: {auth_state}. "
            "Run `python scripts/gemini_login.py` to create it."
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=auth_state)
        page = await context.new_page()

        await page.goto("https://gemini.google.com/app", wait_until="networkidle")
        await asyncio.sleep(2)

        # 输入 prompt
        input_box = page.locator("rich-textarea .ql-editor").first
        await input_box.click()
        await input_box.fill(f"请生成一张图片：{prompt}")
        await page.keyboard.press("Enter")

        # 等待图片出现（最多 90 秒）
        img_locator = page.locator("img.generated-image, img[data-imageid]").first
        await img_locator.wait_for(state="visible", timeout=90000)
        await asyncio.sleep(1)

        # 下载图片
        img_url = await img_locator.get_attribute("src")
        if not img_url:
            raise ValueError("Generated image src is empty")

        response = await context.request.get(img_url)
        with open(output_path, "wb") as f:
            f.write(await response.body())

        await browser.close()


# ── Level 2: Gemini CLI ───────────────────────────────────────────────────────

async def _gemini_cli(prompt: str, output_path: str) -> None:
    """通过 gemini CLI 命令生成图片。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    cmd = [
        "gemini", "generate-image",
        "--prompt", prompt,
        "--output", output_path,
        "--api-key", api_key,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"gemini CLI failed: {stderr.decode()}")
    if not Path(output_path).exists():
        raise FileNotFoundError(f"CLI did not produce output: {output_path}")


# ── Level 3: Gemini API ───────────────────────────────────────────────────────

async def _gemini_api(prompt: str, output_path: str) -> None:
    """通过 google-generativeai SDK 生成图片。"""
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.0-flash-exp-image-generation")

    response = await asyncio.to_thread(
        model.generate_content,
        [prompt],
        generation_config=genai.types.GenerationConfig(
            response_modalities=["image", "text"]
        ),
    )

    for part in response.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(part.inline_data.data))
            return

    raise ValueError("Gemini API returned no image data")
