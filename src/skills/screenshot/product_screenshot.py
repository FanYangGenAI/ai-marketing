"""
Skill: product_screenshot
基于 Playwright，截取本地运行产品的界面截图。
用于 Director 获取产品功能截图作为原始素材。
"""

import os
import asyncio
from dataclasses import dataclass
from pathlib import Path
from playwright.async_api import async_playwright, Page


@dataclass
class ScreenshotResult:
    file_path: str
    width: int
    height: int
    url: str


async def product_screenshot(
    url: str,
    output_path: str,
    selector: str | None = None,
    wait_for: str | None = None,
    viewport: dict | None = None,
    full_page: bool = False,
    delay_ms: int = 1000,
) -> ScreenshotResult:
    """
    截取产品界面截图。

    Args:
        url:         要截图的页面 URL（如 http://localhost:3000/dashboard）
        output_path: 保存路径（含文件名，如 .../assets/raw/shot_01.png）
        selector:    仅截取某个 CSS 选择器对应的元素（可选）
        wait_for:    等待某个 CSS 选择器出现后再截图（可选）
        viewport:    自定义视口，默认 {"width": 1280, "height": 800}
        full_page:   是否截取整页（默认 False）
        delay_ms:    页面加载后额外等待时间（毫秒）

    Returns:
        ScreenshotResult
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    vp = viewport or {"width": 1280, "height": 800}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport=vp)
        page: Page = await context.new_page()

        await page.goto(url, wait_until="networkidle")

        if wait_for:
            await page.wait_for_selector(wait_for, timeout=15000)

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)

        if selector:
            element = await page.query_selector(selector)
            if element is None:
                raise ValueError(f"Selector not found: {selector}")
            await element.screenshot(path=output_path)
            box = await element.bounding_box()
            width = int(box["width"]) if box else vp["width"]
            height = int(box["height"]) if box else vp["height"]
        else:
            await page.screenshot(path=output_path, full_page=full_page)
            width = vp["width"]
            height = vp["height"]

        await browser.close()

    return ScreenshotResult(
        file_path=output_path,
        width=width,
        height=height,
        url=url,
    )
