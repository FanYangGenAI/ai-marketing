#!/usr/bin/env python3
"""
gemini-imagegen Skill — 图片生成脚本（三级降级）
由 Director Agent 通过 bash 调用。
用法见 SKILL.md。
"""

import argparse
import asyncio
import base64
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def run(args: argparse.Namespace) -> None:
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    full_prompt = f"{args.prompt}，{args.style}"

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

    # Level 3: API（兜底）
    try:
        await _level3_api(full_prompt, args.output)
        print(f"✅ [API] Image saved: {args.output}")
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

        await page.goto("https://gemini.google.com/app", wait_until="networkidle")
        await asyncio.sleep(2)

        input_box = page.locator("rich-textarea .ql-editor").first
        await input_box.click()
        await input_box.fill(f"请生成一张图片：{prompt}")
        await page.keyboard.press("Enter")

        img_locator = page.locator("img.generated-image, img[data-imageid]").first
        await img_locator.wait_for(state="visible", timeout=90000)
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


# ── Level 3: Gemini API ───────────────────────────────────────────────────────

async def _level3_api(prompt: str, output: str) -> None:
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
            Path(output).write_bytes(base64.b64decode(part.inline_data.data))
            return
    raise ValueError("API returned no image data")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini image generation (3-level fallback)")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--size", default="1080x1440")
    parser.add_argument("--level", default="auto", choices=["auto", "web", "cli", "api"])
    parser.add_argument("--style", default="小红书风格，高质量，真实感强")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
