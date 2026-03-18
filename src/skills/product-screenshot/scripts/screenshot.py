#!/usr/bin/env python3
"""
product-screenshot Skill — 截图脚本
由 Director Agent 通过 bash 调用。
用法见 SKILL.md。
"""

import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


async def take_screenshot(
    url: str,
    output: str,
    selector: str | None,
    wait_for: str | None,
    full_page: bool,
    delay: int,
    width: int,
    height: int,
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": width, "height": height})
        page = await context.new_page()

        await page.goto(url, wait_until="networkidle")

        if wait_for:
            await page.wait_for_selector(wait_for, timeout=15000)

        if delay > 0:
            await asyncio.sleep(delay / 1000)

        if selector:
            element = await page.query_selector(selector)
            if element is None:
                print(f"❌ Selector not found: {selector}", file=sys.stderr)
                sys.exit(1)
            await element.screenshot(path=output)
            box = await element.bounding_box()
            w = int(box["width"]) if box else width
            h = int(box["height"]) if box else height
        else:
            await page.screenshot(path=output, full_page=full_page)
            w, h = width, height

        await browser.close()

    print(f"✅ Screenshot saved: {output} ({w}x{h}px)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Product screenshot via Playwright")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--selector", default=None)
    parser.add_argument("--wait-for", default=None)
    parser.add_argument("--full-page", action="store_true")
    parser.add_argument("--delay", type=int, default=1000)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args()

    asyncio.run(
        take_screenshot(
            url=args.url,
            output=args.output,
            selector=args.selector,
            wait_for=args.wait_for,
            full_page=args.full_page,
            delay=args.delay,
            width=args.width,
            height=args.height,
        )
    )


if __name__ == "__main__":
    main()
