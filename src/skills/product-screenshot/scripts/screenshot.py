#!/usr/bin/env python3
"""
product-screenshot Skill — 截图脚本
由 Director Agent 通过 bash 调用。
用法见 SKILL.md。

支持两种模式：
  1. 简单截图：直接打开 URL 截图（公开页面）
  2. 带登录的操作截图：加载 auth state，执行 actions 序列后截图

actions 格式（JSON 数组）：
  [
    {"type": "navigate", "url": "/translate"},
    {"type": "click", "selector": ".btn"},
    {"type": "fill", "selector": "#input", "value": "Hello"},
    {"type": "wait_for", "selector": ".result"},
    {"type": "wait_ms", "ms": 1000},
    {"type": "screenshot", "selector": ".panel"}   ← 截图目标（省略则全页）
  ]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright


async def _execute_actions(page: Page, actions: list[dict], base_url: str, output: str) -> tuple[int, int]:
    """执行 actions 序列，返回 (width, height)。"""
    screenshot_taken = False
    vp = page.viewport_size or {}
    w, h = vp.get("width", 1280), vp.get("height", 800)

    for action in actions:
        atype = action.get("type")

        if atype == "navigate":
            url = action["url"]
            if not url.startswith("http"):
                url = base_url.rstrip("/") + "/" + url.lstrip("/")
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(1)

        elif atype == "click":
            await page.locator(action["selector"]).first.click()
            await asyncio.sleep(0.5)

        elif atype == "fill":
            await page.locator(action["selector"]).first.fill(action.get("value", ""))

        elif atype == "wait_for":
            await page.wait_for_selector(action["selector"], timeout=15000)

        elif atype == "wait_ms":
            await asyncio.sleep(action.get("ms", 1000) / 1000)

        elif atype == "screenshot":
            sel = action.get("selector")
            if sel:
                element = await page.query_selector(sel)
                if element:
                    await element.screenshot(path=output)
                    box = await element.bounding_box()
                    if box:
                        w, h = int(box["width"]), int(box["height"])
                else:
                    print(f"⚠️  selector 未找到：{sel}，改为全页截图", file=sys.stderr)
                    await page.screenshot(path=output, full_page=False)
            else:
                await page.screenshot(path=output, full_page=False)
            screenshot_taken = True

        else:
            print(f"⚠️  未知 action type: {atype!r}", file=sys.stderr)

    if not screenshot_taken:
        await page.screenshot(path=output, full_page=False)

    return w, h


async def take_screenshot(
    url: str,
    output: str,
    selector: str | None,
    wait_for: str | None,
    full_page: bool,
    delay: int,
    width: int,
    height: int,
    auth_state: str | None,
    actions: list[dict] | None,
    base_url: str,
) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        ctx_kwargs: dict = {"viewport": {"width": width, "height": height}}
        if auth_state and Path(auth_state).exists():
            ctx_kwargs["storage_state"] = auth_state

        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        if actions:
            await page.goto(base_url, wait_until="networkidle")
            await asyncio.sleep(1)
            w, h = await _execute_actions(page, actions, base_url, output)
        else:
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
    parser.add_argument("--url", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--selector", default=None)
    parser.add_argument("--wait-for", default=None)
    parser.add_argument("--full-page", action="store_true")
    parser.add_argument("--delay", type=int, default=1000)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--auth-state", default=None, help="Playwright storage_state JSON 路径")
    parser.add_argument("--actions", default=None, help="操作序列 JSON 字符串或文件路径")
    parser.add_argument("--base-url", default="", help="产品 base URL（actions 中相对路径的基准）")
    args = parser.parse_args()

    actions = None
    if args.actions:
        p = Path(args.actions)
        actions = json.loads(p.read_text(encoding="utf-8") if p.exists() else args.actions)

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
            auth_state=args.auth_state,
            actions=actions,
            base_url=args.base_url or args.url,
        )
    )


if __name__ == "__main__":
    main()
