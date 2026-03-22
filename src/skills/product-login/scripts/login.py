#!/usr/bin/env python3
"""
product-login Skill — 登录原语 Web 产品并保存 Playwright auth state

用法：
  python src/skills/product-login/scripts/login.py \\
    --account zh \\
    --auth-state campaigns/原语/config/auth_state_zh.json

  # 强制重新登录
  python ... --force

需要在 .env 中设置：
  PRODUCT_LOGIN_URL=https://...
  PRODUCT_ZH_USERNAME=...
  PRODUCT_ZH_PASSWORD=...
  PRODUCT_EN_USERNAME=...
  PRODUCT_EN_PASSWORD=...

退出码：
  0 — 成功
  1 — 登录失败（凭据错误、网络超时等）
  2 — 缺少必要配置（.env 变量未设置）
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
from playwright.async_api import async_playwright

load_dotenv(override=True)

# ── Selector 候选列表 ──────────────────────────────────────────────────────────

_USERNAME_CANDIDATES = [
    "input[placeholder*='用户名']",
    "input[placeholder*='账号']",
    "input[placeholder*='邮箱']",
    "input[placeholder*='email' i]",
    "input[placeholder*='username' i]",
    "input[type='email']",
    "input[type='text'][name*='user']",
    "input[type='text'][name*='email']",
    "input[type='text'][name*='account']",
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


async def _find_selector(page, candidates: list[str]) -> str | None:
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return sel
        except Exception:
            continue
    return None


async def login(
    login_url: str,
    username: str,
    password: str,
    auth_state_path: str,
    login_config: dict,
    force: bool,
) -> None:
    out = Path(auth_state_path)
    if out.exists() and not force:
        print(f"[product-login] auth state 已存在，跳过登录：{out}")
        print(f"[product-login] 使用 --force 强制重新登录")
        return

    out.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        print(f"[product-login] 打开登录页：{login_url}")
        await page.goto(login_url, wait_until="networkidle")
        await asyncio.sleep(2)

        # ── 确定 selectors ────────────────────────────────────────────────────
        user_sel = login_config.get("username_selector") or await _find_selector(page, _USERNAME_CANDIDATES)
        pass_sel = login_config.get("password_selector") or await _find_selector(page, _PASSWORD_CANDIDATES)
        submit_sel = login_config.get("submit_selector") or await _find_selector(page, _SUBMIT_CANDIDATES)

        if not user_sel:
            raise RuntimeError("未找到用户名输入框，请在 login_config.json 中手动指定 username_selector")
        if not pass_sel:
            raise RuntimeError("未找到密码输入框，请在 login_config.json 中手动指定 password_selector")
        if not submit_sel:
            raise RuntimeError("未找到提交按钮，请在 login_config.json 中手动指定 submit_selector")

        print(f"[product-login] selectors: username={user_sel!r} password={pass_sel!r} submit={submit_sel!r}")

        # ── 填写并提交 ────────────────────────────────────────────────────────
        await page.locator(user_sel).first.fill(username)
        await page.locator(pass_sel).first.fill(password)
        await page.locator(submit_sel).first.click()

        # ── 等待登录成功（等 localStorage token 写入）────────────────────────
        # 策略1：等待 localStorage['auth-storage'].state.isAuthenticated === true
        # 策略2：回退 — 等待密码框消失
        # 策略3：兜底 — 截图确认
        print("[product-login] 等待登录完成...")
        try:
            await page.wait_for_function(
                """() => {
                    const s = localStorage.getItem('auth-storage');
                    if (!s) return false;
                    try {
                        const d = JSON.parse(s);
                        return d.state && d.state.isAuthenticated === true && !!d.state.token;
                    } catch (e) { return false; }
                }""",
                timeout=15000,
            )
            print("[product-login] localStorage token 已写入 → 登录成功")
        except Exception:
            # 回退：等密码框消失
            try:
                await page.wait_for_selector(pass_sel, state="hidden", timeout=10000)
                print("[product-login] 登录表单已消失 → 登录成功（回退策略）")
            except Exception:
                # 兜底：截图供调试
                await asyncio.sleep(3)
                debug_shot = out.parent / "login_debug.png"
                await page.screenshot(path=str(debug_shot))
                still_on_login = await page.locator(pass_sel).first.is_visible()
                if still_on_login:
                    raise RuntimeError(
                        f"登录失败：表单仍然可见。调试截图：{debug_shot}\n"
                        f"请检查用户名/密码是否正确，或手动在 login_config.json 中调整 selectors"
                    )
                print(f"[product-login] 登录完成（兜底判断通过），当前 URL：{page.url}")

        # ── 保存 auth state ────────────────────────────────────────────────────
        await context.storage_state(path=auth_state_path)
        print(f"[product-login] auth state 已保存：{auth_state_path}")

        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="登录原语产品并保存 Playwright auth state")
    parser.add_argument("--account", required=True, choices=["zh", "en"],
                        help="账号类型：zh（中文用户）或 en（英文用户）")
    parser.add_argument("--auth-state", required=True,
                        help="auth state 保存路径，如 campaigns/原语/config/auth_state_zh.json")
    parser.add_argument("--login-config", default=None,
                        help="login_config.json 路径（可选，提供 selectors 覆盖）")
    parser.add_argument("--force", action="store_true", help="强制重新登录")
    args = parser.parse_args()

    login_url = os.environ.get("PRODUCT_LOGIN_URL", "")
    if not login_url:
        print("❌ .env 中未设置 PRODUCT_LOGIN_URL", file=sys.stderr)
        sys.exit(2)

    key = args.account.upper()
    username = os.environ.get(f"PRODUCT_{key}_USERNAME", "")
    password = os.environ.get(f"PRODUCT_{key}_PASSWORD", "")
    if not username or not password:
        print(f"❌ .env 中未设置 PRODUCT_{key}_USERNAME / PRODUCT_{key}_PASSWORD", file=sys.stderr)
        sys.exit(2)

    login_config: dict = {}
    config_path = args.login_config
    if config_path and Path(config_path).exists():
        login_config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    try:
        asyncio.run(login(login_url, username, password, args.auth_state, login_config, args.force))
        print("[product-login] 完成")
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
