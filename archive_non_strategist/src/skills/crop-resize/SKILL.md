---
name: crop-resize
description: >
  Use this skill to crop and resize images to platform-specific dimensions.
  Triggers when: (1) an image needs to be adjusted to xiaohongshu 3:4 or 1:1 ratio,
  (2) after a screenshot or image generation to ensure correct output size,
  (3) a Director task requires image size normalization. NOT for: generating new
  images, adding text, or masking private information.
user-invocable: false
metadata:
  openclaw:
    requires:
      python_packages: [Pillow]
---

# Skill: crop-resize

## 用途
将图片裁剪并缩放到平台规范尺寸。通常在 `product-screenshot` 或 `gemini-imagegen` 之后调用。

## 平台预设尺寸

| Key | 平台 | 尺寸 | 比例 |
|-----|------|------|------|
| `xiaohongshu_34` | 小红书竖版 | 1080×1440 | 3:4 |
| `xiaohongshu_11` | 小红书方图 | 1080×1080 | 1:1 |
| `douyin` | 抖音 | 1080×1920 | 9:16 |
| `tiktok` | TikTok | 1080×1920 | 9:16 |

## 调用方式

```bash
# 使用平台预设
python src/skills/crop-resize/scripts/crop_resize.py \
  --input "assets/raw/shot_01.png" \
  --output "assets/raw/shot_01_cropped.png" \
  --size xiaohongshu_34

# 使用自定义尺寸
python src/skills/crop-resize/scripts/crop_resize.py \
  --input "assets/raw/shot_01.png" \
  --output "assets/raw/shot_01_cropped.png" \
  --size 1080x1440 \
  --mode center
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--input` | ✅ | 原始图片路径 |
| `--output` | ✅ | 输出路径 |
| `--size` | ✅ | 平台 key 或 `宽x高` 格式 |
| `--mode` | ❌ | `center`（居中裁剪，默认）/ `fit`（等比缩放留白） |

## 裁剪模式说明

- **center（默认）**：先缩放使图片覆盖目标尺寸，再居中裁剪。适合大多数情况，保证填满。
- **fit**：等比缩放至目标尺寸内，不裁剪，可能有留白。适合不能裁掉内容的图。

## 执行后检查

```bash
# 验证尺寸是否正确
python -c "from PIL import Image; img=Image.open('{output}'); print(img.size)"
```

预期输出：`(1080, 1440)`
