# 视觉审计重设计方案

## 背景与问题

### 现有方案的局限

当前视觉审计（`_visual_audit`）存在以下核心缺陷：

1. **文字叠加层干扰**：图片上贴有文字 overlay，LLM 读到 overlay 的文字后认为"内容匹配"，忽略了底图本身的视觉内容是否与文案相关。
2. **单一检查项 `image_content_match` 语义模糊**：既要判断构图，又要判断内容相关性，导致误判多。
3. **无 per-image 结论**：所有图片混在一个审计请求中，无法定位哪张图有问题。
4. **无 holistic 整体视角**：多图之间的叙事连贯性、产品形象一致性没有检查。
5. **无 3-way 投票**：视觉审计只做一次，而文案审计做了 3 次投票，不一致。

---

## 新方案架构

### 两层审计结构

```
视觉审计
├── Layer 1：per-image audit（每张图独立审计）
│   ├── visual_matches_caption        图底层视觉是否支撑图说/caption
│   ├── no_misleading_overlay         overlay 文字是否与底图矛盾
│   └── product_ui_when_claimed       若声称展示产品界面，底图是否为产品 UI
│
└── Layer 2：holistic audit（全套图整体审计）
    ├── visual_narrative_coherent     多图合起来是否讲述一个连贯故事
    └── product_accurately_represented 产品功能/形象的整体传达是否准确
```

Per-image 与 holistic 均使用 **3-way 投票**（与文案审计一致），取多数决。

---

## 审计 Prompt 设计

### Per-image Audit Prompt

```
你是一名专业的社交媒体内容审核员，专注于图文一致性审核。

你的任务是审核单张配图的内容质量。你将收到：
- 一张图片（可能带有文字叠加层 overlay）
- 该图对应的 caption（图说）
- 帖子正文摘要

请【忽略图片上的文字叠加层】，只评估图片的底层视觉内容（场景、人物、物体、氛围）。

逐项判断（passed: true/false，reason: 简短说明）：

1. visual_matches_caption
   判断：图片的底层视觉场景/内容，是否合理支撑 caption 所描述的含义？
   注意：overlay 上写的文字不算"视觉内容"，只看画面本身。
   失败条件：底图是完全无关的场景（例如 caption 说"展示翻译结果"，但底图是海边日落）

2. no_misleading_overlay
   判断：overlay 文字（如有）是否与底图视觉产生明显矛盾或误导？
   失败条件：overlay 声称某个产品功能，但底图展示的是完全不同的事物，且二者放在一起会引起用户误解

3. product_ui_when_claimed
   判断：若 caption 或正文声称此图展示产品界面/截图，底图是否确实包含产品 UI 元素？
   若 caption 未声称展示产品界面，此项自动通过（passed: true）。
   失败条件：声称是产品截图，但底图是 AI 生成的插画或无关图片

对每项输出：
{
  "check_id": "<check名称>",
  "passed": true | false,
  "reason": "<一句话说明>"
}
```

### Holistic Audit Prompt

```
你是一名专业的社交媒体内容策略审核员。

你将收到一组配图（按发布顺序排列）和完整的帖子正文。

请忽略图片上的文字叠加层，只评估各图底层视觉内容的整体组合效果。

逐项判断（passed: true/false，reason: 简短说明）：

1. visual_narrative_coherent
   判断：这组图片的底层视觉，放在一起是否讲述了一个有逻辑、有层次的故事或演示？
   注意：单张图（共 1 张）自动视为连贯（passed: true）。
   失败条件：多图之间视觉风格/主题完全割裂，用户看了一头雾水

2. product_accurately_represented
   判断：从这组图片的整体视觉印象来看，用户能否正确理解该产品/服务的核心价值？
   失败条件：整组图片给出了错误的产品印象（如翻译 App 的配图全是旅游风景，完全看不出与语言/翻译相关）

对每项输出：
{
  "check_id": "<check名称>",
  "passed": true | false,
  "reason": "<一句话说明>"
}
```

---

## 输出 Schema

### 单轮审计结果（供 3-way 投票使用）

```json
{
  "per_image": [
    {
      "image_order": 1,
      "checks": [
        { "check_id": "visual_matches_caption", "passed": true, "reason": "..." },
        { "check_id": "no_misleading_overlay",  "passed": true, "reason": "..." },
        { "check_id": "product_ui_when_claimed","passed": true, "reason": "..." }
      ]
    }
  ],
  "holistic": [
    { "check_id": "visual_narrative_coherent",       "passed": true, "reason": "..." },
    { "check_id": "product_accurately_represented",  "passed": true, "reason": "..." }
  ]
}
```

### 最终汇总到 audit_result.json 的 visual_items

```json
"visual_items": [
  {
    "check_id": "img_1_visual_matches_caption",
    "passed": true,
    "votes": [true, true, true],
    "reason": "多数认为底图场景（对话/手机）与 caption 描述一致"
  },
  {
    "check_id": "img_1_no_misleading_overlay",
    "passed": true,
    "votes": [true, true, false],
    "reason": "..."
  },
  ...
  {
    "check_id": "holistic_visual_narrative_coherent",
    "passed": true,
    "votes": [true, true, true],
    "reason": "..."
  }
]
```

---

## 3-way 投票流程

```
对每张图 + holistic，并发调用 3 次 _single_visual_audit(image, caption, post_text)
↓
收集 3 组结果，对每个 check_id 取多数票
↓
majority_vote(votes) → passed / failed
↓
汇总为 visual_items 写入 audit_result.json
```

---

## 与现有流程的集成

| 组件 | 变化 |
|---|---|
| `AuditAgent._visual_audit()` | 替换为新两层审计 + 3-way 投票 |
| `AuditAgent.run()` | overall_passed 逻辑不变，依然 AND text + visual |
| `ReviserAgent` | 无需修改，已支持 `visual_items` |
| `audit_result.json` | `visual_items` 字段结构变化（check_id 前缀加 `img_{n}_`） |

---

## 关键设计决策说明

**为何强调"忽略 overlay"？**
现有方案的核心失败点：LLM 读到 overlay 上写着"煤老板→梅老板"就认为图文匹配，而不去看底图是否是 AI 生成的随机场景。新 prompt 明确指令让审核员把 overlay 当作独立的文字层，单独评估，不混入底图视觉判断。

**为何分 per-image + holistic？**
单张图的问题（caption 不符）和整体问题（多图讲不清产品是什么）是不同维度。分开后，失败原因更明确，Reviser 也更容易定向修复。

**为何 `product_ui_when_claimed` 用条件判断？**
AI 生成的营销插画本来就不应是产品截图，不能因为"看不清 UI 文字"就失败。只有当 caption 明确声称展示产品界面时，才检查底图是否真的包含 UI。
