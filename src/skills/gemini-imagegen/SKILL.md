---
name: gemini-imagegen
description: >
  Use this skill to generate images using Google's AI models.
  Triggers when: (1) a Director task_list item has type "image_gen",
  (2) you need to create product showcase images, backgrounds, or decorative
  visuals that don't exist as screenshots. NOT for: editing existing images,
  cropping, or adding text overlays (use crop-resize or text-overlay instead).
user-invocable: false
metadata:
  openclaw:
    requires:
      env: [GEMINI_API_KEY]
      python_packages: [google-genai, playwright]
---

# Skill: gemini-imagegen

## 用途
调用 Google 图片生成模型创建素材。采用**三级降级 + Level 3 双后端**策略，保证最高成功率：

```
Level 1 (首选)  → Gemini Web    (Playwright 浏览器操作，无 API 限额)
Level 2 (降级)  → Gemini CLI    (命令行工具)
Level 3 (兜底)  → API，两个后端可选：
    --backend gemini  →  gemini-2.5-flash-image        (免费额度可用)
    --backend imagen  →  imagen-4.0-generate-001       (付费，最高质量)
```

> **SDK 注意**：使用 `google-genai` 包（`from google import genai`），
> 不要使用已于 2025-11-30 弃用的 `google-generativeai`。

## 调用方式

```bash
# 默认（auto 降级，Gemini 后端，免费额度）
python src/skills/gemini-imagegen/scripts/imagegen.py \
  --prompt "产品UI展示图，蓝白配色，简洁现代，小红书风格" \
  --output "campaigns/{product}/daily/{date}/assets/raw/gen_01.png" \
  --size "1080x1440" \
  --level auto

# 直接调用 API，使用 Imagen 4（高质量，需付费计划）
python src/skills/gemini-imagegen/scripts/imagegen.py \
  --prompt "极简产品展示图，白色背景" \
  --output "campaigns/{product}/daily/{date}/assets/raw/gen_01.png" \
  --level api \
  --backend imagen
```

### 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--prompt` | ✅ | — | 图片描述，中英文均可 |
| `--output` | ✅ | — | 保存路径 |
| `--size` | ❌ | `1080x1440` | 目标尺寸（脚本自动换算为 aspect_ratio） |
| `--level` | ❌ | `auto` | `auto`（自动降级）/ `web` / `cli` / `api` |
| `--style` | ❌ | `小红书风格，高质量，真实感强` | 风格补充词，会拼接到 prompt 末尾 |
| `--backend` | ❌ | `gemini` | Level 3 后端：`gemini`（免费）/ `imagen`（付费，高质量） |

### `--size` → aspect_ratio 映射表

| `--size` | API aspect_ratio |
|----------|-----------------|
| `1080x1440` | `3:4`（小红书竖版，默认） |
| `1080x1080` | `1:1`（小红书方形） |
| `1080x1920` | `9:16`（抖音/TikTok 竖版） |
| `1920x1080` | `16:9`（横版） |

## Level 3 双后端对比

| 维度 | `--backend gemini`（默认） | `--backend imagen` |
|------|--------------------------|-------------------|
| 模型 | `gemini-2.5-flash-image` | `imagen-4.0-generate-001` |
| API 方法 | `generate_content` + `response_modalities=["IMAGE"]` | `generate_images` |
| 免费额度 | ✅ 可用 | ❌ 需付费计划 |
| 图片质量 | 良好，支持文字理解和图文混合 | 最高，尤其擅长写实和精确构图 |
| 文字渲染 | 一般 | 优秀（Imagen 4 的核心改进点） |
| 每次生成张数 | 1 张 | 1-4 张 |

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
上方留白用于叠加标题文字，高分辨率，无水印
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

**Level 3 Imagen 报错 "permission denied" 或 "billing required"**
→ Imagen 4 不支持免费额度，改用 `--backend gemini` 或切换到 Level 1/2

**生成图片不符合要求**
→ 优化 prompt，增加更多风格描述词
→ 对比两个后端效果（Imagen 4 写实性更强）
→ 尝试多次生成，挑选最佳版本

**API 配额超限**
→ 等待几分钟后重试，或切换到 Level 1 (Web)
