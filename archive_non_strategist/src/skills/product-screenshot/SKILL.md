---
name: product-screenshot
description: >
  Use this skill to capture screenshots of a running product's UI.
  Triggers when: (1) the marketing script requires a product interface screenshot,
  (2) Director needs to capture a specific product feature for visual material,
  (3) a task_list item has type "screenshot". NOT for: generating AI images or
  editing existing images.
user-invocable: false
metadata:
  openclaw:
    requires:
      bins: [python]
      env: [PRODUCT_URL]
      python_packages: [playwright]
---

# Skill: product-screenshot

## 用途
使用 Playwright 截取本地运行产品的界面截图，作为营销素材的原始图片。

## 前置条件

1. 产品已在本地运行，URL 配置在 `PRODUCT_URL` 环境变量中
2. Playwright 已安装：`pip install playwright && playwright install chromium`

## 调用方式

通过 bash 调用截图脚本：

```bash
python src/skills/product-screenshot/scripts/screenshot.py \
  --url "http://localhost:3000/dashboard" \
  --output "campaigns/{product}/daily/{date}/assets/raw/shot_01.png" \
  --selector ".main-content" \
  --wait-for ".data-loaded"
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--url` | ✅ | 要截图的页面路径（相对于 PRODUCT_URL） |
| `--output` | ✅ | 保存路径，含文件名 |
| `--selector` | ❌ | 只截取某个 CSS 元素（不填则截全页） |
| `--wait-for` | ❌ | 等待某个元素出现后再截图（处理异步加载） |
| `--full-page` | ❌ | 截取整个页面（包含滚动区域） |
| `--delay` | ❌ | 额外等待毫秒数，默认 1000 |
| `--width` | ❌ | 视口宽度，默认 1280 |
| `--height` | ❌ | 视口高度，默认 800 |

## 执行流程

1. 运行脚本
2. 检查输出文件是否存在：`ls -la {output_path}`
3. 如果截图成功，将结果传入 `crop-resize` Skill 调整为平台规范尺寸
4. 如果失败（产品未启动、选择器不存在），记录错误并在 Director 任务报告中标注

## 常见问题

**页面内容未加载完整**
→ 增加 `--wait-for` 参数指定一个数据加载完成后才出现的元素

**截图空白**
→ 检查产品是否正在运行：`curl -I $PRODUCT_URL`

**选择器找不到**
→ 去掉 `--selector`，截全页后手动标注需要裁剪的区域，交给 `crop-resize` 处理

## 输出

成功后在终端打印：
```
✅ Screenshot saved: {output_path} ({width}x{height}px)
```
