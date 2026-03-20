#!/usr/bin/env python3
"""
setup_auth.py — 一次性登录并保存 Playwright auth state

用法：
  python src/skills/product-screenshot/scripts/setup_auth.py \\
    --account zh \\
    --product 原语

  # 强制重新登录（即使 auth state 已存在）
  python ... --force

需要在 .env 中设置：
  PRODUCT_LOGIN_URL=https://...
  PRODUCT_ZH_USERNAME=...
  PRODUCT_ZH_PASSWORD=...
  PRODUCT_EN_USERNAME=...
  PRODUCT_EN_PASSWORD=...
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

load_dotenv(override=True)

# ── Selector 候选列表（SPA 常见模式）──────────────────────────────────────────

_USERNAME_CANDIDATES = [
    "input[type='email']",
    "input[type='text'][name*='user']",
    "input[type='text'][name*='email']",
    "input[type='text'][name*='account']",
    "input[type='text'][name*='login']",
    "input[placeholder*='用户名']",
    "input[placeholder*='账号']",
    "input[placeholder*='邮箱']",
    "input[placeholder*='email' i]",
    "input[placeholder*='username' i]",
    "input[type='text']:visible",
]

_PASSWORD_CANDIDATES = [
    "input[type='password']",
]

_SUBMIT_CANDIDATES = [
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('登录')",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
    "button:has-text('Sign In')",
    "button:has-text('立即登录')",
    "[role='button']:has-text('登录')",
]

_SUCCESS_CANDIDATES = [
    "[class*='dashboard']",
    "[class*='home']",
    "[class*='workspace']",
    "[class*='main']",
    "nav",
    "header",
]


async def _find_selector(page: Page, candidates: list[str]) -> str | None:
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return sel
        except Exception:
            continue
    return None


async def _detect_and_login(page: Page, username: str, password: str, login_url: str) -> dict:
    """导航到登录页，自动检测 selector，完成登录，返回检测到的 selectors。"""
    print(f"  → 打开登录页：{login_url}")
    await page.goto(login_url, wait_until="networkidle")
    await asyncio.sleep(2)

    print("  → 自动检测表单 selectors...")
    user_sel = await _find_selector(page, _USERNAME_CANDIDATES)
    pass_sel = await _find_selector(page, _PASSWORD_CANDIDATES)
    submit_sel = await _find_selector(page, _SUBMIT_CANDIDATES)

    if not user_sel:
        raise RuntimeError("未找到用户名输入框，请手动在 login_config.json 中指定 username_selector")
    if not pass_sel:
        raise RuntimeError("未找到密码输入框，请手动在 login_config.json 中指定 password_selector")
    if not submit_sel:
        raise RuntimeError("未找到提交按钮，请手动在 login_config.json 中指定 submit_selector")

    print(f"  → 检测到 selectors: username={user_sel!r} password={pass_sel!r} submit={submit_sel!r}")

    # 填写表单并提交
    await page.locator(user_sel).first.fill(username)
    await page.locator(pass_sel).first.fill(password)
    await page.locator(submit_sel).first.click()

    # 等待登录成功（URL 变化 or 成功元素出现）
    print("  → 等待登录成功...")
    try:
        await page.wait_for_url(lambda url: url != login_url, timeout=15000)
    except Exception:
        # URL 没变，尝试等待成功元素
        success_sel = await _find_selector(page, _SUCCESS_CANDIDATES)
        if not success_sel:
            raise RuntimeError(f"登录后 URL 未变化且未检测到成功元素，当前 URL: {page.url}")

    print(f"  ✅ 登录成功，当前页面：{page.url}")

    success_indicator = await _find_selector(page, _SUCCESS_CANDIDATES)
    return {
        "login_url": login_url,
        "username_selector": user_sel,
        "password_selector": pass_sel,
        "submit_selector": submit_sel,
        "success_indicator": success_indicator,
    }


async def setup(account: str, product: str, force: bool) -> None:
    login_url = os.environ.get("PRODUCT_LOGIN_URL", "")
    if not login_url:
        print("❌ .env 中未设置 PRODUCT_LOGIN_URL", file=sys.stderr)
        sys.exit(1)

    key = account.upper()
    username = os.environ.get(f"PRODUCT_{key}_USERNAME", "")
    password = os.environ.get(f"PRODUCT_{key}_PASSWORD", "")
    if not username or not password:
        print(f"❌ .env 中未设置 PRODUCT_{key}_USERNAME / PRODUCT_{key}_PASSWORD", file=sys.stderr)
        sys.exit(1)

    config_dir = Path("campaigns") / product / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    auth_state_path = config_dir / f"auth_state_{account}.json"
    login_config_path = config_dir / "login_config.json"

    if auth_state_path.exists() and not force:
        print(f"✅ auth state 已存在：{auth_state_path}（使用 --force 强制重新登录）")
        return

    print(f"[setup_auth] 开始登录（account={account}, user={username}）")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 读取 login_config.json 中的手动 selectors（如果有）
        login_config = {}
        if login_config_path.exists():
            login_config = json.loads(login_config_path.read_text(encoding="utf-8"))

        user_sel = login_config.get("username_selector")
        pass_sel = login_config.get("password_selector")
        submit_sel = login_config.get("submit_selector")

        if user_sel and pass_sel and submit_sel:
            # 使用手动配置的 selectors
            print("  → 使用 login_config.json 中的 selectors")
            await page.goto(login_url, wait_until="networkidle")
            await asyncio.sleep(2)
            await page.locator(user_sel).first.fill(username)
            await page.locator(pass_sel).first.fill(password)
            await page.locator(submit_sel).first.click()
            await asyncio.sleep(3)
            detected = {**login_config, "login_url": login_url}
        else:
            # 自动检测 selectors
            detected = await _detect_and_login(page, username, password, login_url)

        # 保存 auth state
        await context.storage_state(path=str(auth_state_path))
        print(f"  [OK] auth state 已保存：{auth_state_path}")

        # 更新 login_config.json（写入检测到的 selectors）
        login_config.update(detected)
        login_config_path.write_text(
            json.dumps(login_config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  [OK] login_config.json 已更新：{login_config_path}")

        await browser.close()

    print("✅ 完成。")


def main() -> None:
    parser = argparse.ArgumentParser(description="一次性登录并保存 Playwright auth state")
    parser.add_argument("--account", required=True, choices=["zh", "en"], help="zh 或 en")
    parser.add_argument("--product", default="原语", help="产品名称（campaigns/ 下的文件夹）")
    parser.add_argument("--force", action="store_true", help="强制重新登录")
    args = parser.parse_args()
    asyncio.run(setup(args.account, args.product, args.force))


if __name__ == "__main__":
    main()
