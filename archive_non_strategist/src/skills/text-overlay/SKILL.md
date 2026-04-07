---
name: text-overlay
description: >
  Use this skill to add text overlays (titles, hashtags, CTAs) onto images.
  Triggers when: (1) a Director task requires adding title or body text to a
  product image, (2) creating final xiaohongshu-ready images with captions,
  (3) adding hashtag watermarks or call-to-action text. NOT for: generating
  new images, cropping/resizing, or masking private information.
user-invocable: false
metadata:
  openclaw:
    requires:
      python_packages: [Pillow]
---

# Skill: text-overlay

## 用途
在图片上叠加文字内容（标题、正文、话题标签、CTA），生成平台发布就绪的最终素材。

## 平台字体建议

| 平台 | 推荐字体 | 说明 |
|------|----------|------|
| 小红书 | 系统黑体 / 苹方 | 无字体文件时自动使用 Pillow 默认字体 |
| 通用 | 任意 TTF/OTF | 通过 `--font` 参数指定路径 |

## 调用方式

```bash
# 添加标题（居上，白色，大字）
python src/skills/text-overlay/scripts/text_overlay.py \
  --input "assets/processed/shot_01.png" \
  --output "assets/final/shot_01_titled.png" \
  --text "这款产品真的绝了" \
  --position top \
  --font-size 64 \
  --color "#FFFFFF" \
  --bg-color "#00000080"

# 添加底部话题标签
python src/skills/text-overlay/scripts/text_overlay.py \
  --input "assets/processed/shot_01.png" \
  --output "assets/final/shot_01_final.png" \
  --text "#好物推荐 #亲测有效" \
  --position bottom \
  --font-size 36 \
  --color "#FFFFFF" \
  --padding 24
```

### 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--input` | ✅ | — | 原始图片路径 |
| `--output` | ✅ | — | 输出路径 |
| `--text` | ✅ | — | 要叠加的文字内容 |
| `--position` | ❌ | `top` | 文字位置：`top` / `bottom` / `center` |
| `--font` | ❌ | Pillow默认 | TTF/OTF 字体文件路径 |
| `--font-size` | ❌ | `48` | 字体大小（像素） |
| `--color` | ❌ | `#FFFFFF` | 文字颜色（十六进制，支持8位含透明度） |
| `--bg-color` | ❌ | `#00000080` | 文字背景色（十六进制，支持8位含透明度） |
| `--padding` | ❌ | `20` | 文字与边缘的内边距（像素） |
| `--line-spacing` | ❌ | `8` | 行间距（像素） |
| `--max-width` | ❌ | 图片宽度-2*padding | 文字自动换行的最大宽度 |

## 颜色格式说明

- `#FFFFFF` — 纯白，不透明
- `#FFFFFF80` — 白色，50% 透明度（80 = hex 128/255）
- `#000000B3` — 黑色，70% 透明度
- `#00000000` — 完全透明（无背景）

## 多行文字

脚本自动按 `--max-width` 折行。若文字中含 `\n`，则强制换行。

```bash
python ... --text "亲测好用\n不踩雷！"
```

## 执行后检查

```bash
# 验证输出文件存在且尺寸正确
python -c "from PIL import Image; img=Image.open('{output}'); print(img.size)"
```
