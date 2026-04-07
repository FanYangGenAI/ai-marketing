---
name: privacy-mask
description: >
  Use this skill to mask private or sensitive information in images (faces,
  phone numbers, ID numbers, addresses, QR codes, etc.).
  Triggers when: (1) a product screenshot may contain personal data,
  (2) a Director task explicitly requests privacy masking,
  (3) an image contains visible user data before publishing. NOT for:
  generating new images, cropping, or adding decorative text.
user-invocable: false
metadata:
  openclaw:
    requires:
      python_packages: [Pillow]
---

# Skill: privacy-mask

## 用途
对图片中的敏感信息区域进行马赛克处理，确保发布素材符合隐私保护要求。

## 马赛克方式

使用**像素块马赛克**（缩小再放大）：将指定区域缩小为 `block_size` 分之一，再放大回原尺寸，形成方格效果。无需 OpenCV，仅依赖 Pillow。

## 调用方式

```bash
# 马赛克单个区域（格式：x,y,width,height）
python src/skills/privacy-mask/scripts/privacy_mask.py \
  --input "assets/raw/shot_01.png" \
  --output "assets/processed/shot_01_masked.png" \
  --regions "120,80,200,60"

# 马赛克多个区域
python src/skills/privacy-mask/scripts/privacy_mask.py \
  --input "assets/raw/shot_01.png" \
  --output "assets/processed/shot_01_masked.png" \
  --regions "120,80,200,60" "300,150,180,40"

# 调整马赛克粒度（block-size 越小越模糊）
python src/skills/privacy-mask/scripts/privacy_mask.py \
  --input "assets/raw/shot_01.png" \
  --output "assets/processed/shot_01_masked.png" \
  --regions "120,80,200,60" \
  --block-size 8
```

### 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--input` | ✅ | — | 原始图片路径 |
| `--output` | ✅ | — | 输出路径 |
| `--regions` | ✅ | — | 一个或多个区域，格式 `x,y,width,height`（像素坐标） |
| `--block-size` | ❌ | `15` | 马赛克块大小（像素），越大越模糊 |

## 区域坐标说明

```
(0,0) ─────────────────────────► x
  │
  │   (x, y) ┌──────────────┐
  │           │   width      │ height
  │           └──────────────┘
  ▼ y
```

坐标从图片左上角开始，x 向右，y 向下。

## 如何确定坐标

可借助以下方式获取需要遮挡的区域坐标：

```python
# 快速查看图片尺寸
python -c "from PIL import Image; img=Image.open('shot_01.png'); print(img.size)"

# 使用 Pillow 打开图片查看坐标（在 Python shell 中）
from PIL import Image
img = Image.open("shot_01.png")
# 通过图片编辑器（如 GIMP、PS）标注坐标后输入
```

## 执行后检查

```bash
# 验证输出文件存在
ls -la {output_path}

# 打开图片确认遮挡效果（在有图形界面的环境）
python -c "from PIL import Image; Image.open('{output}').show()"
```

## 常见问题

**不知道要遮挡哪些区域**
→ 先对截图进行目视检查，标注含手机号、邮箱、姓名、身份证、二维码的位置
→ 可请 Vision LLM（如 Claude/Gemini）分析截图并返回需要遮挡的坐标

**马赛克效果不够明显**
→ 减小 `--block-size`（默认 15，可降至 5）
→ 增大 `--regions` 区域范围，确保覆盖完整

**区域坐标超出图片边界**
→ 脚本会自动 clamp 到图片范围，不会报错
