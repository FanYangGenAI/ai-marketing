---
name: gemini-imagegen
description: >
  Use this skill to generate images using Gemini AI.
  Triggers when: (1) a Director task_list item has type "image_gen",
  (2) you need to create product showcase images, backgrounds, or decorative
  visuals that don't exist as screenshots. NOT for: editing existing images,
  cropping, or adding text overlays (use crop-resize or text-overlay instead).
user-invocable: false
metadata:
  openclaw:
    requires:
      env: [GEMINI_API_KEY]
      python_packages: [google-generativeai, playwright]
---

# Skill: gemini-imagegen

## 用途
调用 Gemini 生成图片素材。采用**三级降级**策略，保证最高成功率：

```
Level 1 (首选)  → Gemini Web  (Playwright 浏览器操作)
Level 2 (降级)  → Gemini CLI  (命令行工具)
Level 3 (兜底)  → Gemini API  (google-generativeai SDK)
```

## 调用方式

统一入口脚本自动处理降级逻辑：

```bash
python src/skills/gemini-imagegen/scripts/imagegen.py \
  --prompt "产品UI展示图，蓝白配色，简洁现代，小红书风格" \
  --output "campaigns/{product}/daily/{date}/assets/raw/gen_01.png" \
  --size "1080x1440" \
  --level auto
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--prompt` | ✅ | 图片描述，中英文均可 |
| `--output` | ✅ | 保存路径 |
| `--size` | ❌ | 目标尺寸，默认 `1080x1440`（生成后由 crop-resize 精确调整） |
| `--level` | ❌ | `auto`（默认，自动降级）/ `web` / `cli` / `api` |
| `--style` | ❌ | 风格补充词，默认 `小红书风格，高质量，真实感` |

### 强制指定 Level

```bash
# 仅使用 API（调试用）
python ... --level api

# 仅使用 Web（需要 gemini_auth.json 存在）
python ... --level web
```

## Prompt 编写指南

好的 prompt 应包含：
1. **主体内容**：画面里有什么
2. **风格基调**：配色、质感、光线
3. **平台适配**：`小红书风格` / `竖版构图` / `留白适合加文字`
4. **禁止出现**：`无文字水印` / `无人物面孔`（版权安全）

**示例 prompt：**
```
极简产品展示图，白色背景，产品居中，柔和阴影，
专业摄影风格，小红书审美，竖版 3:4 构图，
上方留白用于叠加标题文字，高分辨率
```

## 执行后必做

图片生成成功后：
1. 调用 `crop-resize` Skill 确保尺寸精确符合平台规范
2. 调用 `privacy-mask` Skill（如果图中可能含有敏感信息）
3. 将结果路径记录到 Asset Library

## 常见问题

**Level 1 (Web) 失败**
→ 检查 `src/config/gemini_auth.json` 是否存在且未过期
→ 运行 `python scripts/gemini_login.py` 重新登录

**生成图片不符合要求**
→ 优化 prompt，增加更多风格描述词
→ 尝试多生成几次，挑选最佳版本

**API 配额超限**
→ 等待几分钟后重试，或切换到 Level 1/2
