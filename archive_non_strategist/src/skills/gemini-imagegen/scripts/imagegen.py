#!/usr/bin/env python3
"""
gemini-imagegen Skill — 图片生成脚本（三级降级 + 双后端）
由 Director Agent 通过 bash 调用。
用法见 SKILL.md。

SDK 说明：
  使用 google-genai（新 SDK），不再使用已弃用的 google-generativeai。
  安装：pip install google-genai
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# 尺寸字符串 → Gemini/Imagen API 接受的 aspect_ratio
_SIZE_TO_ASPECT = {
    "1080x1440": "3:4",
    "1080x1080": "1:1",
    "1080x1920": "9:16",
    "1440x1080": "4:3",
    "1920x1080": "16:9",
}


def _size_to_aspect(size: str) -> str:
    """将 '宽x高' 或 'W:H' 格式转为 API 接受的 aspect_ratio 字符串。"""
    if size in _SIZE_TO_ASPECT:
        return _SIZE_TO_ASPECT[size]
    if ":" in size:  # 已经是比例格式
        return size
    # 尝试计算
    if "x" in size:
        w, h = size.lower().split("x")
        return f"{w.strip()}:{h.strip()}"
    return "3:4"  # fallback


async def run(args: argparse.Namespace) -> None:
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    full_prompt = f"{args.prompt}，{args.style}"
    aspect = _size_to_aspect(args.size)

    if args.level in ("auto", "web"):
        try:
            await _level1_web(full_prompt, args.output)
            print(f"✅ [Web] Image saved: {args.output}")
            return
        except Exception as e:
            if args.level == "web":
                print(f"❌ Level 1 (Web) failed: {e}", file=sys.stderr)
                sys.exit(1)
            log.warning(f"Level 1 (Web) failed: {e} → trying CLI")

    if args.level in ("auto", "cli"):
        try:
            await _level2_cli(full_prompt, args.output)
            print(f"✅ [CLI] Image saved: {args.output}")
            return
        except Exception as e:
            if args.level == "cli":
                print(f"❌ Level 2 (CLI) failed: {e}", file=sys.stderr)
                sys.exit(1)
            log.warning(f"Level 2 (CLI) failed: {e} → trying API")

    # Level 3: API（兜底）—— 支持两个后端
    try:
        if args.backend == "imagen":
            await _level3_imagen(full_prompt, args.output, aspect)
            print(f"✅ [API/Imagen4] Image saved: {args.output}")
        else:
            await _level3_gemini(full_prompt, args.output)
            print(f"✅ [API/Gemini] Image saved: {args.output}")
    except Exception as e:
        print(f"❌ All levels failed. Last error: {e}", file=sys.stderr)
        sys.exit(1)


# ── Level 1: Playwright 操作 Gemini Web ──────────────────────────────────────

async def _level1_web(prompt: str, output: str) -> None:
    from playwright.async_api import async_playwright

    auth_state = os.environ.get("GEMINI_AUTH_STATE", "src/config/gemini_auth.json")
    if not Path(auth_state).exists():
        raise FileNotFoundError(
            f"Auth state not found: {auth_state}. "
            "Run: python scripts/gemini_login.py"
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=auth_state)
        page = await context.new_page()

        await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        input_box = page.locator("rich-textarea .ql-editor").first
        await input_box.wait_for(state="visible", timeout=20000)
        await input_box.click()
        await input_box.fill(f"请生成一张图片：{prompt}")
        await page.keyboard.press("Enter")

        img_locator = page.locator("img.generated-image, img[data-imageid]").first
        await img_locator.wait_for(state="visible", timeout=120000)
        await asyncio.sleep(1)

        img_url = await img_locator.get_attribute("src")
        if not img_url:
            raise ValueError("Generated image src is empty")

        response = await context.request.get(img_url)
        Path(output).write_bytes(await response.body())
        await browser.close()


# ── Level 2: Gemini CLI ───────────────────────────────────────────────────────

async def _level2_cli(prompt: str, output: str) -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    proc = await asyncio.create_subprocess_exec(
        "gemini", "generate-image",
        "--prompt", prompt,
        "--output", output,
        "--api-key", api_key,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"CLI error: {stderr.decode()}")
    if not Path(output).exists():
        raise FileNotFoundError("CLI produced no output file")


# ── Level 3a: Gemini 原生图片生成（免费额度可用）────────────────────────────

async def _level3_gemini(prompt: str, output: str) -> None:
    """
    使用 gemini-2.5-flash-image（直接替代已下线的 gemini-2.0-flash-exp-image-generation）。
    调用方式：generate_content + response_modalities=["IMAGE"]
    免费额度内可用。
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    response = await client.aio.models.generate_content(
        model="nano-banana-pro-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            Path(output).write_bytes(part.inline_data.data)
            return
    raise ValueError("Gemini API returned no image data")


# ── Level 3b: Imagen 4（付费，高质量）──────────────────────────────────────

async def _level3_imagen(prompt: str, output: str, aspect_ratio: str = "3:4") -> None:
    """
    使用 Imagen 4（imagen-4.0-generate-001）。
    调用方式：generate_images（独立方法，非 generate_content）
    注意：需要付费计划，免费额度不可用。
    支持 aspect_ratio: "1:1" | "3:4" | "4:3" | "9:16" | "16:9"
    """
    from google import genai
    from google.genai import types

    # Imagen 只支持以下 5 种比例，不支持 "1080:1440" 之类的绝对像素比
    _valid_ratios = {"1:1", "3:4", "4:3", "9:16", "16:9"}
    if aspect_ratio not in _valid_ratios:
        log.warning(
            f"Imagen 不支持比例 '{aspect_ratio}'，回退到 '3:4'。"
            f"支持的比例：{_valid_ratios}"
        )
        aspect_ratio = "3:4"

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    response = await client.aio.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio,
        ),
    )

    if not response.generated_images:
        raise ValueError("Imagen API returned no images")

    image_bytes = response.generated_images[0].image.image_bytes
    Path(output).write_bytes(image_bytes)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gemini image generation (3-level fallback)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Level 3 后端选择：
  --backend gemini  使用 gemini-2.5-flash-image（默认，免费额度可用）
  --backend imagen  使用 imagen-4.0-generate-001（付费，质量更高，需付费计划）
        """,
    )
    parser.add_argument("--prompt", required=True, help="图片描述")
    parser.add_argument("--output", required=True, help="保存路径")
    parser.add_argument(
        "--size", default="1080x1440",
        help="目标尺寸（用于计算 aspect_ratio），如 1080x1440 / 1080x1080 / 1080x1920"
    )
    parser.add_argument(
        "--level", default="auto",
        choices=["auto", "web", "cli", "api"],
        help="降级策略：auto（默认）/ web / cli / api"
    )
    parser.add_argument(
        "--style", default="小红书风格，高质量，真实感强",
        help="风格补充词，会拼接到 prompt 末尾"
    )
    parser.add_argument(
        "--backend", default="gemini",
        choices=["gemini", "imagen"],
        help="Level 3 API 后端：gemini（免费额度）/ imagen（付费，高质量）"
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
