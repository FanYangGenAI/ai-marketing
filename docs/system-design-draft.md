# AI Marketing Multi-Agent System — Design Draft v0.9

> 状态：待最终确认
> 更新日期：2026-03-17
> 变更说明：综合第一轮讨论反馈，完善多 LLM 架构、Skill 体系、Asset Library 策略

---

## 1. 系统目标

输入用户的**产品 PRD** 和**可运行产品**，系统自动生成一份**定时的物料清单**，包括每天在小红书（首期）、抖音、TikTok 等平台发布所需的文章、图文、短视频等。

系统是一个**自循环、可自进化**的 multi-agent pipeline：
- 通过每日投放数据反馈不断优化策略
- 用户充当 human-in-the-loop，负责提供产品资料、最终确认物料和手动投放
- 随着历史数据积累，系统决策质量持续提升

---

## 2. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                              USER                                     │
│  输入：PRD / 产品 / 个人想法建议 / 手动上传平台反馈数据                  │
│  输出：确认 Audit 通过的物料清单 → 手动投放各平台                        │
└───────────┬──────────────────────────────────────┬────────────────────┘
            │ 产品资料 + 用户建议                    │ 平台反馈数据（手动）
            │                                      ▼
            │                           ┌─────────────────────┐
            │                           │     Strategist      │
            │            ┌──────────────│  反思 & 策略 (冷/热)  │
            │            │ 策略建议文档  └─────────────────────┘
            ▼            ▼
  ┌──────────────────────────┐     ┌─────────────────────────┐
  │         Planner          │◄────│    Campaign Memory      │
  │      每日营销策划团队      │     │  历史投放记录 / 日志      │
  └────────────┬─────────────┘     └─────────────────────────┘
               │ daily_marketing_plan.md
               ▼
  ┌──────────────────────────┐     ┌─────────────────────────┐
  │    Platform  Adapter     │────►│   Platform Specs DB     │
  │       平台适配层          │     │  各平台格式/风格规范      │
  └────────────┬─────────────┘     └─────────────────────────┘
               │ 附加平台规范的计划
               ▼
  ┌──────────────────────────┐
  │       Scriptwriter       │
  │      操作脚本创作团队      │
  └────────────┬─────────────┘
               │ daily_marketing_script.md
               ▼
  ┌──────────────────────────┐   查重/入库   ┌─────────────────────────┐
  │        Director          │◄────────────►│     Asset Library       │
  │     素材生成团队           │              │   素材库 (索引 + 文件)    │
  │  [调用 Skill 体系]         │              └──────────┬──────────────┘
  └────────────┬─────────────┘                         │ 复用历史素材
               │ raw assets                            │
               ▼                                       ▼
  ┌──────────────────────────────────────────────────────────┐
  │                       Creator                            │
  │                     物料组装团队                           │
  │          (按脚本拼接素材 → 最终图文/视频)                    │
  └────────────────────────────┬─────────────────────────────┘
                               │ 待审物料
                               ▼
  ┌──────────────────────────────────────────────────────────┐
  │                         Audit                            │
  │                    合规 & 质量审核团队                       │
  └────────────────────────────┬─────────────────────────────┘
                               │ [Human Final Confirm — 天然发生在手动投放时]
                               ▼
                    ┌──────────────────────┐
                    │   每日投放物料清单     │
                    │  output/final/ 文件夹 │
                    └──────────────────────┘
```

---

## 3. 核心设计决策

### 3.1 多 LLM 驱动架构

**关键决策：不同 agent 由不同 LLM 驱动，各取所长。**

| Agent 角色 | 驱动模型 | 选型理由 |
|-----------|---------|---------|
| PlannerA（趋势分析） | **Gemini** | 原生集成 Google Search，实时信息获取能力最强 |
| PlannerB（产品视角） | **Claude Opus 4.6** | 深度推理，PRD 理解和功能分析最强 |
| PlannerC（用户视角） | **GPT-4o** | 创意和用户共鸣感知能力突出 |
| PlannerModerator | **Claude Opus 4.6** | 综合判断与收敛，决策质量最高 |
| ScriptwriterA（叙事结构） | **GPT-4o** | 故事线构建、营销叙事能力强 |
| ScriptwriterB（视觉指令） | **Gemini** | 多模态理解，图文视觉语言最自然 |
| ScriptwriterC（文案创作） | **GPT-4o** | 小红书风格口语化文案、钩子词能力强 |
| ScriptwriterModerator | **Claude Opus 4.6** | 确保脚本可操作性和一致性 |
| Director | **Gemini** | 多模态理解 + 可调用 Gemini 自身图像生成能力 |
| Creator | **Claude Opus 4.6** | 程序化组装逻辑清晰，指令执行精准 |
| PlatformAuditor | **GPT-4o** | 对各平台内容风格、违禁词规则熟悉度高 |
| ContentAuditor | **Claude Opus 4.6** | 事实核查、逻辑一致性检查最严谨 |
| SafetyAuditor | **Claude Opus 4.6** | 安全和隐私判断最保守可靠 |
| StrategyDataAnalyst | **Gemini** | 大上下文窗口，适合处理大量历史数据 |
| StrategyReviewer | **GPT-4o** | 创意策略思维，营销方向建议新颖 |
| StrategyModerator | **Claude Opus 4.6** | 策略文档的综合与输出 |

**LLM 接入方式：**
```python
# 统一的 LLM 调用抽象层
class LLMClient:
    claude  = anthropic.Anthropic()          # ANTHROPIC_API_KEY
    openai  = openai.OpenAI()                # OPENAI_API_KEY
    gemini  = google.generativeai.Client()   # GEMINI_API_KEY
```

---

### 3.2 Campaign Memory（跨日记忆）

**关键决策：用每日文件夹结构作为 Campaign Memory，不需要额外数据库。**

系统通过读取历史每日文件夹来感知：
- 哪些话题 / 卖点已经被讲过（`plan/` 目录）
- 哪些脚本风格用过（`script/` 目录）
- 哪些素材已生成并实际投放（`output/final/` + audit 结果）

Planner 在每次启动时，自动扫描最近 N 天（默认 30 天）的 `plan/` 目录，生成「已覆盖话题摘要」作为上下文输入，避免内容重复。

---

### 3.3 Skill 体系设计

**关键决策：借鉴 OpenClaw 的 SKILL 策略，所有 agent 需要的原子能力预先封装好，agent 只负责调用。**

```
src/skills/
├── search/
│   └── web_search.py          # Claude 内置 web_search 工具封装
│
├── screenshot/
│   └── product_screenshot.py  # Playwright 截取产品界面
│
├── image_gen/
│   └── gemini_imagegen.py     # ★ 核心 Skill：通过浏览器操作 Gemini 生成图片
│
├── image_edit/
│   ├── crop_resize.py         # 图片裁剪、缩放到平台规范尺寸
│   ├── text_overlay.py        # 给图片添加文字（标题/说明）
│   └── watermark.py           # 隐私遮挡（截图中的用户数据）
│
└── video/
    ├── screen_record.py       # 录制产品操作视频
    └── video_clip.py          # 视频裁剪、拼接（MoviePy + FFmpeg）
```

#### Gemini 图像生成 Skill 详细设计

**首选方案：浏览器自动化（Playwright）**

Agent 通过 Playwright 在受控的浏览器沙箱中操作 Gemini Web，实现图像生成。

```python
# src/skills/image_gen/gemini_imagegen.py

from playwright.async_api import async_playwright

async def gemini_web_imagegen(
    prompt: str,
    output_path: str,
    size: str = "1080x1440"
) -> str:
    """
    通过 Playwright 操作 Gemini Web 生成图片。
    沙箱权限：只允许访问 gemini.google.com，输出写入 output_path。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state="config/gemini_auth.json"  # 持久化登录态
        )
        page = await context.new_page()

        # 导航到 Gemini
        await page.goto("https://gemini.google.com")

        # 输入 prompt（附加尺寸和风格要求）
        full_prompt = f"{prompt}，尺寸 {size}，高质量，适合小红书风格"
        await page.fill("[data-testid='input-area']", full_prompt)
        await page.keyboard.press("Enter")

        # 等待图片生成并下载
        image_element = await page.wait_for_selector("img.generated-image", timeout=60000)
        image_url = await image_element.get_attribute("src")
        # 下载到 output_path ...

        return output_path
```

**降级方案：Gemini CLI**

当 Gemini Web 不可用时，降级到 Gemini CLI：

```bash
# 需要预先安装并配置好 gemini CLI
gemini generate-image \
    --prompt "{prompt}" \
    --output "{output_path}" \
    --api-key $GEMINI_API_KEY
```

**降级方案 2：Gemini API 直接调用**

```python
import google.generativeai as genai
model = genai.GenerativeModel("gemini-2.0-flash-exp-image-generation")
response = model.generate_content(prompt)
```

优先级：Gemini Web > Gemini CLI > Gemini API

---

### 3.4 Asset Library（素材库）设计

**关键决策：混合索引策略——内容哈希去重 + 标签索引复用。**

#### 目录结构
```
campaigns/{product}/asset_library/
├── index.json          # 主索引文件
├── images/             # 图片素材（按哈希命名，避免重复）
└── videos/             # 视频素材
```

#### index.json 结构
```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "asset_a3f8c2",
      "hash": "md5:a3f8c2d1e9b74f56",
      "type": "image",
      "file": "images/a3f8c2d1e9b74f56.jpg",
      "size": "1080x1440",
      "created_at": "2026-03-17",
      "source": "gemini_web",
      "prompt": "产品UI展示，蓝白配色",
      "tags": ["product_ui", "blue_theme", "screenshot"],
      "platform": "xiaohongshu",
      "used_in": ["2026-03-17/output/final/post_01.jpg"],
      "reuse_count": 2
    }
  ]
}
```

#### 查重策略
```
新素材生成请求
      ↓
1. 计算目标素材的 MD5 → 精确匹配已有 hash？
      ├── 是 → 直接返回已有文件路径（跳过生成）
      └── 否 → 2. 标签检索：同类型 + 同标签组合，找到相似素材？
                    ├── 是 → 询问 Director Agent：复用？还是重新生成？
                    └── 否 → 调用 Skill 生成新素材 → 入库
```

---

## 4. Agent 详细设计

### 4.1 Planner（每日营销策划团队）

**角色定位：** 整个系统的起点和大脑，负责制定每日营销方向。

**触发逻辑：**
```
系统每日启动
    ↓
1. 读取最新 strategy_suggestion.md（Strategist 输出，冷启动则用默认策略）
2. 扫描近 30 天 Campaign Memory（已投放内容摘要）
3. 读取用户当日输入（PRD更新 / 新想法 / 特殊要求）
4. 启动 Planner 多 agent 讨论
```

**输入：**
- 产品 PRD（首次全量，后续增量）
- 最新 `strategy_suggestion.md`
- 近 30 天 Campaign Memory 摘要
- 用户当日想法和建议（可选）

**Agent 构成与模型分配：**

| Agent | 模型 | 职责 |
|-------|------|------|
| PlannerA | Gemini | 调用 web_search Skill，搜索当日相关热点（行业趋势、竞品动态、社会热点） |
| PlannerB | Claude Opus 4.6 | 深度解读 PRD，挖掘产品最具传播力的功能亮点 |
| PlannerC | GPT-4o | 从目标用户视角出发，评估哪个方向最有共鸣感 |
| PlannerModerator | Claude Opus 4.6 | 主持讨论，综合三方观点，输出最终计划书 |

**讨论流程（Debate → Synthesize）：**
```
Round 1（并行）：PlannerA 输出热点报告 / PlannerB 输出产品亮点清单 / PlannerC 输出用户洞察
Round 2（并行）：各 agent 互相点评，指出优缺点
Round 3（串行）：PlannerModerator 综合，选定 1-3 个方案，输出计划书
最多 3 轮，超时强制收敛。
```

**实时搜索 Skill：**
```python
# 使用 Claude 内置的 web_search 工具（通过 Claude API tool_use）
# PlannerA (Gemini) 也可使用 Gemini 原生的 Google Search 接口
# 两者并行搜索，结果汇入讨论
```

**输出：** `/{daily_folder}/plan/daily_marketing_plan.md`

```markdown
# 每日营销计划 - {YYYY-MM-DD}

## 今日参考热点
- {热点1}：{来源} {搜索日期}
- {热点2}：...

## 内容方向（共 N 个方案）

### 方案一：{标题}
- **核心卖点**：
- **目标用户**：
- **内容形式**：图文（小红书）
- **话题钩子**：
- **关键词 / 话题标签**：
- **结合热点**：

## 本次放弃的方向（及理由）
## Campaign Memory 参考（避免重复的话题）
```

---

### 4.2 Platform Adapter（平台适配层）

**角色定位：** 将通用营销计划转化为各平台的具体格式要求。首期聚焦**小红书图文**。

此模块为**规则引擎**，非 LLM agent，读取平台规范配置文件后直接附加到计划书。

**小红书图文规范（`config/platforms/xiaohongshu.json`）：**

```json
{
  "platform": "xiaohongshu",
  "content_type": "图文",
  "specs": {
    "image_count": {"min": 1, "max": 9, "recommended": "3-6"},
    "image_ratio": ["3:4", "1:1"],
    "image_size_px": "1080x1440 (3:4) 或 1080x1080 (1:1)",
    "title_max_chars": 20,
    "body_chars": {"min": 500, "max": 1000},
    "hashtags": {"min": 3, "max": 8, "strategy": "头部+长尾混合"},
    "cover_note": "首图最重要，必须包含文字overlay，强视觉冲击"
  },
  "style_guide": {
    "tone": "口语化、真实感、生活化",
    "avoid": ["最强", "第一", "无敌", "绝对"],
    "prefer": ["亲测", "分享", "真实体验", "好用到哭"]
  }
}
```

**输出：** 在原计划书 markdown 末尾追加 `## 平台规范注释` 章节，传递给 Scriptwriter。

---

### 4.3 Scriptwriter（脚本创作团队）

**角色定位：** 以专业策划和脚本创作者视角，将计划转化为可执行的操作脚本。

**输入：**
- 附加了平台规范的 `daily_marketing_plan.md`
- 产品可运行版本（用于截屏 / 录屏指令参考）

**Agent 构成与模型分配：**

| Agent | 模型 | 职责 |
|-------|------|------|
| ScriptwriterA | GPT-4o | 设计整体叙事结构：钩子→铺垫→高光→行动引导 |
| ScriptwriterB | Gemini | 规划每张图的视觉构成：截屏区域、构图、视觉焦点 |
| ScriptwriterC | GPT-4o | 撰写最终文案：标题、正文、话题标签 |
| ScriptwriterModerator | Claude Opus 4.6 | 汇总，确保脚本的可操作性、平台规范符合度 |

**输出：** `/{daily_folder}/script/daily_marketing_script_{方案名}.md`

```markdown
# 营销脚本 - {YYYY-MM-DD} - {方案名}

## 元信息
- 目标平台：小红书
- 内容形式：图文（共 N 张）
- 方案来源：daily_marketing_plan.md § 方案X

## 标题
{最终确定标题，≤20字}

---

## 图1（封面）
- **素材来源**：[新截屏 / 新生成 / 复用 asset_id]
- **截屏操作**（如需）：打开产品 → 进入「{功能名}」界面 → 截取 {区域描述}
- **生成要求**（如需）：{给 Gemini 的 prompt，含风格/色调/内容}
- **后期处理**：裁剪为 1080x1440 / 添加文字 "{overlay内容}" / 遮挡用户隐私区域
- **视觉要点**：{高光元素、视觉焦点说明}

## 图2 ~ 图N
（同上格式）

---

## 正文
{完整文案，500-1000字，口语化}

## 话题标签
#{tag1} #{tag2} #{tag3} ...

---

## Director 任务清单（结构化，供自动解析）
```json
{
  "tasks": [
    {
      "id": "task_01",
      "type": "screenshot",
      "description": "截取产品首页功能界面",
      "skill": "product_screenshot",
      "params": {"url": "...", "selector": "...", "crop": "..."}
    },
    {
      "id": "task_02",
      "type": "image_gen",
      "description": "生成封面背景图",
      "skill": "gemini_web_imagegen",
      "params": {"prompt": "...", "size": "1080x1440"},
      "check_asset_library": true
    },
    {
      "id": "task_03",
      "type": "reuse",
      "description": "复用品牌 Logo 素材",
      "asset_id": "asset_a3f8c2"
    }
  ]
}
```
```

---

### 4.4 Director（素材生成团队）

**角色定位：** 解析脚本的 Director 任务清单，调用 Skill 体系生成原始素材。

**核心流程：**
```
读取 Director 任务清单（JSON）
      ↓
for 每个 task:
    1. 如 check_asset_library=true → 查询 Asset Library
           ├── 命中 → 直接返回文件路径，跳过生成
           └── 未命中 → 调用对应 Skill
    2. Skill 执行（Gemini Web → CLI → API 降级）
    3. 生成文件写入 assets/raw/，更新 index.json
并行执行（最多 N 个并发任务）
```

**Agent 模型：** Gemini（多模态理解，能直接分析截图质量、判断图像是否符合要求）

**沙箱权限边界：**
```
允许：
  ✅ 读取 /campaigns/{product}/  目录
  ✅ 写入 /{daily_folder}/assets/raw/
  ✅ 访问 gemini.google.com（Gemini Web Skill）
  ✅ 截取本机运行的产品界面（Playwright localhost）

禁止：
  ❌ 写入任何其他目录
  ❌ 访问非白名单域名
  ❌ 执行系统级命令（rm, chmod 等）
  ❌ 读取 .env / 配置文件
```

**输出：**
- 素材文件 → `/{daily_folder}/assets/raw/`
- 更新 `campaigns/{product}/asset_library/index.json`

---

### 4.5 Creator（物料组装团队）

**角色定位：** 按脚本将 Director 生成的素材组装成最终可投放的物料。

**与 Director 的边界：**
- Director：生成原始素材（截图、AI 生成图、原始视频）
- Creator：程序化组装（排版、加字、调整尺寸、合图）

Creator **不需要** GUI 或 Gemini Web，只用 Pillow / FFmpeg 这类确定性工具。

**Agent 模型：** Claude Opus 4.6（精准执行组装指令）

**工作内容：**
1. 按脚本图片顺序排列素材
2. 调整尺寸到平台规范（3:4 1080x1440）
3. 添加文字 overlay（封面标题、角标等）
4. 为图片中的隐私信息添加遮挡
5. 输出最终图片序列

**输出：** `/{daily_folder}/output/final/`

---

### 4.6 Audit（审计团队）

**角色定位：** 多维度审核最终物料，确保合规、准确、安全。

> 注：Audit 通过后，物料清单直接供用户手动投放，人工确认环节天然发生在投放动作本身。

**Agent 构成与模型分配：**

| Agent | 模型 | 审核维度 |
|-------|------|---------|
| PlatformAuditor | GPT-4o | 平台规范符合度（格式、风格、违禁词） |
| ContentAuditor | Claude Opus 4.6 | 内容准确性（功能描述是否夸大、数据是否真实） |
| SafetyAuditor | Claude Opus 4.6 | 隐私数据、版权风险、敏感词 |

**审核清单（小红书版）：**
```yaml
platform_checks:
  - image_count: 1-9张 ✓/✗
  - image_ratio: 3:4 或 1:1 ✓/✗
  - title_length: ≤20字 ✓/✗
  - hashtag_count: 3-8个 ✓/✗

content_checks:
  - no_superlative_claims: 无"最强""第一"等违禁词 ✓/✗
  - feature_accuracy: 功能描述与PRD一致 ✓/✗
  - no_false_data: 无虚假数据 ✓/✗

safety_checks:
  - privacy_masked: 截图中用户信息已遮挡 ✓/✗
  - copyright_clean: 图片/素材无版权问题 ✓/✗
  - no_sensitive_content: 无政治/宗教/敏感内容 ✓/✗
```

**输出：**
- `/{daily_folder}/audit/audit_report.md`（每项审核结果 + 通过/失败理由）
- 如有失败项：生成修改建议，可触发 Director / Creator 局部重新生成

---

### 4.7 Strategist（策略反思团队）

**角色定位：** 基于真实投放数据反思，输出策略建议文档供 Planner 参考。

**触发时机：** 每次 Planner 启动前运行（系统第一步）。

**冷启动处理（无历史数据时）：**

```
Strategist 检测到无历史投放数据
      ↓
DataAnalyst (Gemini): 搜索小红书同品类热门账号的内容规律
StrategyReviewer (GPT-4o): 结合行业知识，给出通用起步策略
StrategyModerator (Claude): 输出冷启动策略建议文档
```

**冷启动策略建议内容示例：**
```markdown
## 冷启动策略建议（适用于：首次发布 / 无历史数据）

### 内容方向建议
1. 首帖以「真实体验」为主，不要过度商业感
2. 封面图要有强视觉冲击，文字要大且清晰
3. 前 3 帖聚焦 1-2 个核心功能，不要贪多

### 话题标签策略
- 混合 3 个大流量话题（100w+ 笔记）+ 3 个垂直话题（10w-50w 笔记）
- 避免完全的蓝海话题（流量太低）

### 发布时间
- 工作日：18:00-22:00
- 周末：10:00-12:00, 20:00-22:00
```

**热启动处理（有历史数据时）：**

用户手动上传投放数据（点赞、评论、收藏、阅读量 CSV/截图），Strategist 分析并生成改进建议。

**Agent 构成与模型分配：**

| Agent | 模型 | 职责 |
|-------|------|------|
| DataAnalyst | Gemini | 解读数据（大上下文处理多篇历史记录），识别高/低表现内容特征 |
| StrategyReviewer | GPT-4o | 结合数据洞察，提出内容优化方向 |
| StrategyModerator | Claude Opus 4.6 | 输出结构化策略建议文档 |

**输出：** `campaigns/{product}/strategy/strategy_suggestion_{date}.md`

---

## 5. 文件系统结构

```
ai-marketing/
├── .gitignore                        # campaigns/ 全部忽略
├── .env.example                      # API Keys 模板（不提交实际值）
├── docs/
│   └── system-design-draft.md
├── src/
│   ├── agents/
│   │   ├── planner.py
│   │   ├── scriptwriter.py
│   │   ├── director.py
│   │   ├── creator.py
│   │   ├── audit.py
│   │   └── strategist.py
│   ├── skills/
│   │   ├── search/
│   │   │   └── web_search.py
│   │   ├── screenshot/
│   │   │   └── product_screenshot.py
│   │   ├── image_gen/
│   │   │   └── gemini_imagegen.py    # Web → CLI → API 降级
│   │   └── image_edit/
│   │       ├── crop_resize.py
│   │       ├── text_overlay.py
│   │       └── watermark.py
│   ├── orchestrator/
│   │   ├── pipeline.py               # 主编排逻辑
│   │   ├── debate.py                 # Debate→Synthesize 通用机制
│   │   └── asset_library.py          # Asset Library 管理
│   ├── llm/
│   │   ├── claude_client.py
│   │   ├── openai_client.py
│   │   └── gemini_client.py
│   └── config/
│       └── platforms/
│           └── xiaohongshu.json
├── requirements.txt
└── campaigns/                        # ← .gitignore 全部排除
    └── {product_name}/
        ├── product/                  # 产品资料（PRD、截图等）
        ├── strategy/                 # Strategist 输出（跨日期共享）
        │   └── strategy_suggestion_{date}.md
        ├── asset_library/
        │   ├── index.json            # 素材索引
        │   ├── images/               # 图片素材（按 hash 命名）
        │   └── videos/
        └── daily/
            └── {YYYY-MM-DD}/
                ├── plan/
                │   └── daily_marketing_plan.md
                ├── script/
                │   └── daily_marketing_script_{方案名}.md
                ├── assets/
                │   └── raw/          # Director 生成的原始素材
                ├── output/
                │   └── final/        # 最终投放物料（Audit 通过后）
                └── audit/
                    └── audit_report.md
```

**`.gitignore` 关键条目：**
```gitignore
# 投放物料（文件体积大，不上传）
campaigns/

# API Keys
.env

# Python 环境
.venv/
__pycache__/
*.pyc
```

---

## 6. 编排逻辑（Orchestrator）

```python
# src/orchestrator/pipeline.py

async def run_daily_pipeline(product: str, user_input: str = ""):

    daily_folder = f"campaigns/{product}/daily/{today}"

    # Step 1: Strategist（冷/热启动）
    strategy = await strategist.run(
        product=product,
        feedback_data=load_latest_feedback(product)  # None → 冷启动
    )

    # Step 2: Planner（多 LLM 讨论）
    plan = await planner.run(
        prd=load_prd(product),
        strategy=strategy,
        memory=scan_campaign_memory(product, days=30),
        user_input=user_input,
        output_path=f"{daily_folder}/plan/"
    )

    # Step 3: Platform Adapter（规则引擎，无 LLM）
    adapted_plan = platform_adapter.adapt(plan, platform="xiaohongshu")

    # Step 4: Scriptwriter（多 LLM 讨论）
    scripts = await scriptwriter.run(
        adapted_plan=adapted_plan,
        output_path=f"{daily_folder}/script/"
    )

    # Step 5: Director（并行 Skill 调用）
    for script in scripts:
        assets = await director.run(
            task_list=script.director_tasks,
            asset_library=load_asset_library(product),
            raw_output_path=f"{daily_folder}/assets/raw/"
        )

    # Step 6: Creator（程序化组装）
    final_materials = await creator.run(
        scripts=scripts,
        assets_path=f"{daily_folder}/assets/raw/",
        output_path=f"{daily_folder}/output/final/"
    )

    # Step 7: Audit（多 LLM 并行审核）
    audit_result = await audit.run(
        materials=final_materials,
        scripts=scripts,
        plan=plan,
        report_path=f"{daily_folder}/audit/"
    )

    # Step 8: 输出投放物料清单
    print(f"\n✅ 今日投放物料已就绪：{daily_folder}/output/final/")
    print(f"📋 审核报告：{daily_folder}/audit/audit_report.md")
    print("请确认后手动投放。")
```

---

## 7. Agent 讨论收敛机制（通用）

所有多 agent 讨论节点，均使用统一的 **Debate → Synthesize** 模式：

```python
# src/orchestrator/debate.py

async def debate_and_synthesize(agents: list, moderator, context: dict) -> str:
    """
    Round 1: 各 agent 独立发言（并行调用，降低延迟）
    Round 2: 各 agent 点评其他人的观点（并行）
    Round 3: Moderator 综合，输出最终结论（串行）
    最多 MAX_ROUNDS 轮，超时强制进入收敛。
    """
    MAX_ROUNDS = 3
    opinions = {}

    for round_num in range(1, MAX_ROUNDS + 1):
        # 并行获取所有 agent 的发言
        tasks = [agent.speak(context, history=opinions) for agent in agents]
        results = await asyncio.gather(*tasks)
        opinions[round_num] = dict(zip([a.name for a in agents], results))

        # 检查是否已收敛（所有 agent 表示同意）
        if all(r.get("agree") for r in results):
            break

    # Moderator 综合收敛
    return await moderator.synthesize(opinions, context)
```

---

## 8. 技术栈

| 层次 | 技术选型 | 说明 |
|------|---------|------|
| LLM - Claude | `anthropic` SDK | Planner/Script/Creator/Audit 的 Moderator 角色 |
| LLM - OpenAI | `openai` SDK | Scriptwriter/Strategist 创意角色 |
| LLM - Gemini | `google-generativeai` SDK | Planner 趋势分析、Director、图像生成 |
| 图像生成 Skill | Playwright + Gemini Web | 首选；CLI / API 降级 |
| 截屏 Skill | Playwright (headless) | 产品界面截图 |
| 图像处理 | Pillow, OpenCV | 裁剪、加字、遮挡 |
| 视频处理 | MoviePy, FFmpeg | 视频剪辑（后期） |
| Web 搜索 | Claude `web_search` tool / Gemini Search | Planner 实时热点搜索 |
| 数据持久化 | JSON 文件（跟随 campaigns/ 目录） | 轻量，无需数据库 |
| 并发 | Python `asyncio` | 多 agent 并行调用 |
| 环境隔离 | Python venv（当前）→ Docker（后期） | 沙箱逐步升级 |

---

## 9. 首期实现范围（MVP）

聚焦最小可行路径，优先跑通完整链路：

**平台：** 小红书图文（3-6 张图 + 标题 + 正文）

**完整链路：**
- [ ] Strategist 冷启动版（输出默认策略建议文档）
- [ ] Planner：3 agent（Claude + GPT-4o + Gemini）+ Moderator
- [ ] Platform Adapter：小红书规范配置
- [ ] Scriptwriter：3 agent + Moderator，输出结构化任务清单
- [ ] Director：`product_screenshot` + `gemini_web_imagegen` + `text_overlay`
- [ ] Asset Library：hash 去重 + tag 索引
- [ ] Creator：Pillow 拼图 + 文字 overlay
- [ ] Audit：3 agent 并行审核
- [ ] 输出物料清单，供用户手动发布

**暂不包括：**
- 抖音 / TikTok 视频内容
- 平台 API 自动拉取反馈数据
- Docker 完整沙箱
- 视频剪辑 Skill

---

## 10. 开放问题（待后续确认）

| # | 问题 | 当前假设 | 优先级 |
|---|------|---------|--------|
| 1 | Gemini Web 的登录态持久化方案 | Playwright storage_state 保存 cookie | 高 |
| 2 | 多 LLM 并发调用的成本估算 | 每日约 $0.5-2（依据 plan 复杂度） | 中 |
| 3 | Audit 失败时的自动修复循环最大重试次数 | 默认 2 次，超过则标记人工处理 | 中 |
| 4 | 小红书平台规范更新的维护策略 | 手动更新 `xiaohongshu.json` | 低 |
| 5 | 后续自动接入平台 API 获取投放反馈 | 暂时人工上传 CSV | 低（二期） |
