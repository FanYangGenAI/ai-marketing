#!/usr/bin/env python3
"""
Gemini 网页登录 — 保存 Playwright auth state 供 gemini-imagegen Skill 使用。

用法：
  python scripts/gemini_login.py

流程：
  1. 打开可见的浏览器窗口，导航到 gemini.google.com
  2. 自动填写 Google 账号（如果 .env 中设置了 GOOGLE_EMAIL / GOOGLE_PASSWORD）
  3. 你在浏览器里完成剩余登录步骤（密码、2FA 等）
  4. 登录成功后，回到终端按 Enter，脚本保存 auth state

需要在 .env 中设置（可选，用于自动填写邮箱）：
  GOOGLE_EMAIL=your@gmail.com
  GOOGLE_PASSWORD=yourpassword
"""

import asyncio
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(override=True)

AUTH_STATE_PATH = Path("src/config/gemini_auth.json")
GEMINI_URL = "https://gemini.google.com/app"


async def main() -> None:
    email = os.environ.get("GOOGLE_EMAIL", "")
    password = os.environ.get("GOOGLE_PASSWORD", "")

    AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("[gemini-login] 正在启动浏览器...")
    print(f"[gemini-login] auth state 将保存到：{AUTH_STATE_PATH}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto(GEMINI_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 尝试自动填写邮箱
        if email:
            try:
                await page.wait_for_selector("input[type='email']", timeout=4000)
                await page.fill("input[type='email']", email)
                await page.keyboard.press("Enter")
                print(f"[gemini-login] 已自动填写邮箱：{email}")
                await asyncio.sleep(2)
            except Exception:
                pass

        # 尝试自动填写密码
        if password:
            try:
                await page.wait_for_selector("input[type='password']", timeout=4000)
                await page.fill("input[type='password']", password)
                await page.keyboard.press("Enter")
                print("[gemini-login] 已自动填写密码")
                await asyncio.sleep(2)
            except Exception:
                pass

        wait_seconds = 180
        print()
        print(">>> 请在弹出的浏览器窗口中完成 Google 登录")
        print(f">>> 登录完成后无需任何操作，脚本将在 {wait_seconds} 秒后自动保存 <<<")
        print()

        for remaining in range(wait_seconds, 0, -30):
            print(f"[gemini-login] 等待中... 还剩 {remaining} 秒（请在浏览器中完成登录）")
            await asyncio.sleep(min(30, remaining))

        # 保存当前状态
        await context.storage_state(path=str(AUTH_STATE_PATH))
        print(f"[gemini-login] auth state 已保存：{AUTH_STATE_PATH}")

        # 截图确认
        await page.screenshot(path="src/config/gemini_login_confirm.png")
        print("[gemini-login] 确认截图已保存：src/config/gemini_login_confirm.png")

        await browser.close()
        print("[gemini-login] 完成！")


if __name__ == "__main__":
    asyncio.run(main())
