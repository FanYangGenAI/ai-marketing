# product-login Skill

登录原语 Web 产品，保存 Playwright auth state 供后续截图使用。

## 用法

```bash
python src/skills/product-login/scripts/login.py \
  --account zh \
  --auth-state campaigns/原语/config/auth_state_zh.json

# 强制重新登录（session 过期时使用）
python src/skills/product-login/scripts/login.py \
  --account zh \
  --auth-state campaigns/原语/config/auth_state_zh.json \
  --force

# 指定自定义 selectors 配置
python src/skills/product-login/scripts/login.py \
  --account en \
  --auth-state campaigns/原语/config/auth_state_en.json \
  --login-config campaigns/原语/config/login_config.json
```

## 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--account` | 是 | `zh`（中文账号）或 `en`（英文账号） |
| `--auth-state` | 是 | auth state 保存路径 |
| `--login-config` | 否 | login_config.json 路径，提供 selector 覆盖 |
| `--force` | 否 | 强制重新登录（即使 auth state 已存在） |

## 依赖 .env 变量

```
PRODUCT_LOGIN_URL=https://sypl.mindturi.com
PRODUCT_ZH_USERNAME=fan_zh_test
PRODUCT_ZH_PASSWORD=password123
PRODUCT_EN_USERNAME=fan_en_test
PRODUCT_EN_PASSWORD=password123
```

## 登录成功判断逻辑

1. 等待密码输入框消失（SPA 路由切换后表单卸载）
2. 回退：等待 URL 发生变化
3. 兜底：3秒后检查密码框是否仍可见；失败时保存 `login_debug.png` 供排查

## 输出

- `{auth-state}` — Playwright storage_state JSON（含 cookies + localStorage）
- `login_debug.png`（仅登录失败时）— 当时页面截图

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 登录失败 |
| 2 | 缺少 .env 配置 |
