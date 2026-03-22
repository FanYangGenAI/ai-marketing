# AI Marketing Multi-Agent System — Design Draft v1.3

> 状态：进行中
> 更新日期：2026-03-22
> 变更说明：
> - v0.9 → v1.0：Audit 架构全面重设计
>   - 引入共享审计清单（audit_checklist.json），按条目投票
>   - 所有 Auditor 改用 Gemini + StructuredOutput（response_schema 保证 JSON 可靠性）
>   - 新增 ReviserAgent：Audit 失败后自动分类问题、路由到正确阶段重跑
>   - 新增 RetryGuard：超限后写入 human_review_required.json 等待人工介入
> - v1.0 → v1.1：
>   - 所有 Agent 驱动模型全部可配置（统一在 `src/config/llm_config.json`）
>   - 默认 GPT 模型由 `gpt-4o` 升级为 `gpt-5-nano`
>   - 新增 LessonMemory 模块：Audit 失败经验写入长期记忆，后续创作自动注入，避免重复犯错
>   - Campaign Memory 章节扩展为「记忆体系」，区分短期（选题去重）与长期（规则经验）
> - v1.1 → v1.2：
>   - 新增第 7 章：展示层（Frontend + FastAPI）
>   - 技术选型：Vite + Vue 3 + Tailwind（前端）/ FastAPI（后端）
>   - 设计六个核心视图：Overview、PostDetail、AuditReport、PipelineLog、AssetLibrary、LessonMemory
>   - FastAPI 只读 REST API，自动生成 OpenAPI 文档
> - v1.2 → v1.3：
>   - **Strategist 成为每次 Pipeline 必跑的第一步**（不再是冷启动专属）
>   - **新增用户交互完整闭环**：项目创建 → 运行触发 → 接受/拒绝反馈 → LessonMemory 更新
>   - **前端从只读升级为可操作**：创建项目、触发流水线（异步）、接受/拒绝每日素材包
>   - **新增右下角实时状态面板**：流水线各阶段实时进度，可折叠
>   - **版本号抑制策略**：文案默认不携带产品版本号，可通过 product_config.json 控制
>   - **LessonMemory 扩展为双向**：接受（正向强化）+ 拒绝原因（负向强化）

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
│                        USER（前端可操作）                              │
│  创建项目：产品命名 + 上传 PRD + 填写产品需求描述（user_brief）          │
│  运行前可选：填写 today_note（本次特殊要求）                             │
│  触发流水线（异步）→ 右下角实时状态面板查看进度                           │
│  接受 ✅ / 拒绝 ❌+原因 每日素材包 → 反馈写入 LessonMemory               │
└───────────┬──────────────────────────────────────┬────────────────────┘
            │ 产品资料 + 用户建议                    │ 平台反馈数据（手动上传）
            ▼
  ┌─────────────────────────────────────────────────┐
  │                  Strategist                     │  ← 每次 Pipeline 的强制第一步
  │          策略反思 & 建议（冷/热启动）              │    冷启动：分析行业规律，给出起步策略
  └──────────────────────┬──────────────────────────┘    热启动：解读历史投放数据，给出优化策略
                         │ strategy_suggestion.md
                         ▼
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
  │      操作脚本创作团队      │  （文案默认不携带版本号，suppress_version_in_copy）
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
  │  文本：共享清单 × 3 Gemini 并行投票（per-item 2/3）         │
  │  视觉：per-image + holistic，3-way voting                 │
  └────────────────────────────┬─────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │ 通过                 │ 未通过
                    ▼                     ▼
       ┌──────────────────────┐  ┌─────────────────────────────┐
       │   每日投放物料清单     │  │        ReviserAgent         │
       │  output/final/ 文件夹 │  │  分类问题 → 决定路由阶段      │
       └──────────┬───────────┘  └──────────┬──────────────────┘
                  │                         │ route_to + revision_instructions
                  ▼                         │ (RetryGuard: 超限 → human_review_required.json)
       ┌──────────────────────┐             │
       │   前端展示层（可操作）  │             ▼
       │  FastAPI + Vue 前端   │  ┌──────────────────────────────────┐
       │  浏览 / 审阅 / 下载    │  │          LessonMemory            │
       │  [✅接受] / [❌拒绝]   │  │   campaigns/{p}/memory/          │
       └──────────┬───────────┘  │   lessons_{platform}.json        │
                  │              │                                  │
                  │ 接受/拒绝+原因│  写入信号（双向）：                │
                  └─────────────►│  ① Audit 失败    → 负向经验       │
                                 │  ② 用户拒绝+原因 → 负向经验       │
                                 │  ③ 用户接受      → 正向经验       │
                                 └──────────┬───────────────────────┘
                                            │ 读取历史规则经验（注入到 prompt）
                                            ▼
                                 Planner / Scriptwriter / Creator
                                            │
                                            ▼
                                    从指定阶段重新执行 Pipeline
```

---

## 3. 核心设计决策

### 3.1 多 LLM 驱动架构

**关键决策：不同 agent 由不同 LLM 驱动，各取所长。所有模型均可配置，通过 `src/config/llm_config.json` 统一管理，无需改代码即可切换。**

| Agent 角色 | 默认模型 | 可配置 | 选型理由 |
|-----------|---------|:------:|---------|
| PlannerA（趋势分析） | `gemini-2.5-flash` | ✅ | 原生集成 Google Search，实时信息获取能力最强 |
| PlannerB（产品视角） | `claude-opus-4-6` | ✅ | 深度推理，PRD 理解和功能分析最强 |
| PlannerC（用户视角） | `gpt-5-nano` | ✅ | 创意和用户共鸣感知能力突出 |
| PlannerModerator | `claude-opus-4-6` | ✅ | 综合判断与收敛，决策质量最高 |
| ScriptwriterA（叙事结构） | `gpt-5-nano` | ✅ | 故事线构建、营销叙事能力强 |
| ScriptwriterB（视觉指令） | `gemini-2.5-flash` | ✅ | 多模态理解，图文视觉语言最自然 |
| ScriptwriterC（文案创作） | `gpt-5-nano` | ✅ | 小红书风格口语化文案、钩子词能力强 |
| ScriptwriterModerator | `claude-opus-4-6` | ✅ | 确保脚本可操作性和一致性 |
| Director | `gemini-2.5-flash` | ✅ | 多模态理解 + 可调用 Gemini 自身图像生成能力 |
| Creator | `claude-opus-4-6` | ✅ | 程序化组装逻辑清晰，指令执行精准 |
| PlatformAuditor | `gemini-2.5-flash` | ✅ | StructuredOutput 保证 JSON 可靠性；平台规则熟悉度高 |
| ContentAuditor | `gemini-2.5-flash` | ✅ | StructuredOutput；事实核查、逻辑一致性 |
| SafetyAuditor | `gemini-2.5-flash` | ✅ | StructuredOutput；安全、隐私、虚假宣传判断 |
| ReviserAgent | `gemini-2.5-flash` | ✅ | 分类任务轻量，不需要重型模型 |
| StrategyDataAnalyst | `gemini-2.5-flash` | ✅ | 大上下文窗口，适合处理大量历史数据 |
| StrategyReviewer | `gpt-5-nano` | ✅ | 创意策略思维，营销方向建议新颖 |
| StrategyModerator | `claude-opus-4-6` | ✅ | 策略文档的综合与输出 |

**模型配置文件（`src/config/llm_config.json`）：**
```json
{
  "planner_a":           "gemini-2.5-flash",
  "planner_b":           "claude-opus-4-6",
  "planner_c":           "gpt-5-nano",
  "planner_moderator":   "claude-opus-4-6",
  "scriptwriter_a":      "gpt-5-nano",
  "scriptwriter_b":      "gemini-2.5-flash",
  "scriptwriter_c":      "gpt-5-nano",
  "scriptwriter_moderator": "claude-opus-4-6",
  "director":            "gemini-2.5-flash",
  "creator":             "claude-opus-4-6",
  "auditor":             "gemini-2.5-flash",
  "reviser":             "gemini-2.5-flash",
  "strategy_analyst":    "gemini-2.5-flash",
  "strategy_reviewer":   "gpt-5-nano",
  "strategy_moderator":  "claude-opus-4-6"
}
```

**LLM 接入方式：**
```python
# 统一的 LLM 调用抽象层
class LLMClient:
    claude  = anthropic.Anthropic()          # ANTHROPIC_API_KEY
    openai  = openai.OpenAI()                # OPENAI_API_KEY
    gemini  = google.generativeai.Client()   # GEMINI_API_KEY
```

---

### 3.2 记忆体系（Campaign Memory + Lesson Memory）

系统设计了两层记忆，分别解决「重复选题」和「重复犯错」两类问题。

#### 短期记忆：Campaign Memory（跨日选题去重）

**关键决策：用每日文件夹结构作为 Campaign Memory，不需要额外数据库。**

系统通过读取历史每日文件夹来感知：
- 哪些话题 / 卖点已经被讲过（`plan/` 目录）
- 哪些脚本风格用过（`script/` 目录）
- 哪些素材已生成并实际投放（`output/final/` + audit 结果）

Planner 在每次启动时，自动扫描最近 N 天（默认 30 天）的 `plan/` 目录，生成「已覆盖话题摘要」作为上下文输入，避免内容重复。

#### 长期记忆：Lesson Memory（双向学习信号）

**关键决策：LessonMemory 同时接受正向（用户接受）和负向（Audit 失败 / 用户拒绝）信号，形成双向学习闭环。**

- **负向写入时机（避免犯错）**：
  - ① ReviserAgent 触发时（Audit 失败条目写入，含违规内容片段）
  - ② 用户在前端点击「❌ 拒绝」并填写原因时（写入拒绝理由）
- **正向写入时机（强化成功）**：
  - ③ 用户在前端点击「✅ 接受」时（记录当日成功物料特征，供后续创作参考）
- **读取时机**：Planner / Scriptwriter / Creator 启动时读取当前平台的 lesson 列表，注入到各自的 system prompt 末尾（"历史经验提示"段落）
- **作用范围**：按 `platform` 隔离（小红书经验不污染抖音创作）；按 `category` 筛选相关经验（Scriptwriter 主要读 `content` + `platform` 类经验，Director 主要读 `safety` 类经验）
- **持久化**：不限时间，不删除，只追加（可手动清理）

详细设计见 **3.5 LessonMemory 模块**。

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

### 3.5 LessonMemory 模块（长期经验记忆）

**文件位置：** `campaigns/{product}/memory/lessons_{platform}.json`
（每个平台独立文件，如 `lessons_xiaohongshu.json`）

#### 数据结构

```json
{
  "platform": "xiaohongshu",
  "version": "1.1",
  "lessons": [
    {
      "id": "lesson_001",
      "signal": "negative",
      "source": "audit_failure",
      "date": "2026-03-22",
      "checklist_item": "title_length",
      "category": "platform",
      "offending_content": "「用这款App，你的待办事项再也不会被遗忘，效率提升300%」（共25字）",
      "rule": "标题必须严格控制在20字以内（含标点），超出会被平台截断",
      "injected_to": ["scriptwriter", "creator"]
    },
    {
      "id": "lesson_002",
      "signal": "negative",
      "source": "user_rejection",
      "date": "2026-03-23",
      "rejection_reason": "整体风格过于硬广，缺少真实生活感，不符合小红书社区调性",
      "category": "content",
      "rule": "避免硬广叙事，多用第一人称真实体验分享角度",
      "injected_to": ["planner", "scriptwriter"]
    },
    {
      "id": "lesson_003",
      "signal": "positive",
      "source": "user_acceptance",
      "date": "2026-03-22",
      "title": "AI把梅老板翻成煤老板，我3秒救回",
      "theme": "翻译翻车反差叙事",
      "note": "用户接受，发布效果良好。幽默反差型内容与产品功能结合效果佳",
      "category": "content",
      "injected_to": ["planner", "scriptwriter"]
    }
  ]
}
```

#### 写入逻辑

```
【负向信号 ①】Audit 失败 → ReviserAgent 触发
      ↓
for 每个 failed checklist item:
    构建 lesson 条目（signal=negative, source=audit_failure）
    检查是否已有相同 checklist_item 的 lesson（去重：同一条规则不重复记录）
        ├── 已有 → 更新 date（证明规则仍在违反，可累计触发次数）
        └── 无 → 追加新 lesson
    写入 lessons_{platform}.json

【负向信号 ②】用户在前端点击「❌ 拒绝」+ 填写拒绝原因
      ↓
    写入 lesson 条目（signal=negative, source=user_rejection）
    记录 rejection_reason、日期
    写入 lessons_{platform}.json

【正向信号 ③】用户在前端点击「✅ 接受」
      ↓
    写入 lesson 条目（signal=positive, source=user_acceptance）
    记录当日素材的 theme、title 等成功特征
    写入 lessons_{platform}.json
```

#### 读取与注入逻辑

```
各 Agent 启动时（Planner / Scriptwriter / Creator）
      ↓
读取 lessons_{platform}.json
      ↓
按 injected_to 字段筛选当前 agent 需要接收的经验
      ↓
在 system prompt 末尾追加：

「## 历史创作经验（请严格遵守）
以下规则来自过去审计失败的经验，必须在本次创作中避免：

1. [title_length] 标题必须严格控制在20字以内（含标点）
2. [no_superlatives] 禁止使用绝对化用语：最快、最强、第一...
...」
```

#### 实现模块

`src/orchestrator/lesson_memory.py`

```python
class LessonMemory:
    def load(platform: str) -> list[dict]          # 读取当前平台所有 lessons
    def inject_prompt(agent: str, platform: str) -> str  # 生成注入段落
    def write_lesson(platform: str, lesson: dict)  # 追加/更新单条 lesson
```

---

### 3.6 版本号抑制策略

**关键决策：营销文案默认不携带产品版本号（如 v1.2、2.0 等），除非用户明确要求。**

**原因：**
- 版本号属于开发视角，用户（消费者）对版本号无感知，不增加宣传效果
- 版本号频繁更新会导致历史物料过期，增加维护成本
- 例外：用户在 today_note 中明确提及「本次发布是大版本更新，请强调 X.0」

**实现方式：**
- `campaigns/{product}/config/product_config.json` 新增字段：`"suppress_version_in_copy": true`（默认 `true`）
- Scriptwriter system prompt 中注入规则：「文案中不出现具体版本号（如 v1.2、3.0），除非用户在 today_note 中明确要求」
- 用户可在 today_note 中写「本次是 2.0 正式版大更新，请在文案中体现」，Scriptwriter 优先响应

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
| PlannerA | Gemini（默认 gemini-2.5-flash，可配置） | 调用 web_search Skill，搜索当日相关热点（行业趋势、竞品动态、社会热点） |
| PlannerB | Claude（默认 claude-opus-4-6，可配置） | 深度解读 PRD，挖掘产品最具传播力的功能亮点 |
| PlannerC | GPT（默认 gpt-5-nano，可配置） | 从目标用户视角出发，评估哪个方向最有共鸣感 |
| PlannerModerator | Claude（默认 claude-opus-4-6，可配置） | 主持讨论，综合三方观点，输出最终计划书 |

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
| ScriptwriterA | GPT（默认 gpt-5-nano，可配置） | 设计整体叙事结构：钩子→铺垫→高光→行动引导 |
| ScriptwriterB | Gemini（默认 gemini-2.5-flash，可配置） | 规划每张图的视觉构成：截屏区域、构图、视觉焦点 |
| ScriptwriterC | GPT（默认 gpt-5-nano，可配置） | 撰写最终文案：标题、正文、话题标签 |
| ScriptwriterModerator | Claude（默认 claude-opus-4-6，可配置） | 汇总，确保脚本的可操作性、平台规范符合度 |

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

#### 设计原则

1. **共享审计清单**：所有 Auditor 审的是同一份清单（`src/config/audit_checklist.json`），而非各自为政。
2. **独立并行审核**：3 个 Gemini 实例同时对每个清单条目独立给出 `passed/failed`。
3. **按条目多数投票**：每个条目 2/3 Gemini 认为不通过 → 该条目 ❌；所有条目全部 ✅ → 整体通过。
4. **StructuredOutput 保证可靠性**：使用 Gemini `response_schema` 强制 JSON 输出，彻底消除解析错误。

#### 模型配置

| 角色 | 默认模型 | 可配置 |
|------|---------|--------|
| Auditor × 3（并行） | `gemini-2.5-flash` | ✅ 可在 config 中切换，如 `gemini-3.1-flash` |

> 选用 Gemini 而非 Claude 的原因：Gemini 原生支持 `response_schema`（StructuredOutput），可 100% 保证输出符合 JSON Schema，无需正则解析，彻底解决 free-form 输出的解析问题。Claude 暂无等价原生支持。

#### 审计清单（`src/config/audit_checklist.json`，可扩展）

```json
[
  { "id": "title_length",    "category": "platform", "route_on_fail": "creator",      "description": "标题字数 ≤ 20 字" },
  { "id": "body_length",     "category": "platform", "route_on_fail": "creator",      "description": "正文 500-1000 字" },
  { "id": "hashtag_count",   "category": "platform", "route_on_fail": "creator",      "description": "话题标签 3-8 个" },
  { "id": "no_superlatives", "category": "platform", "route_on_fail": "scriptwriter", "description": "无绝对化用语（最强/第一等）" },
  { "id": "fact_accuracy",   "category": "content",  "route_on_fail": "scriptwriter", "description": "功能描述与 PRD 一致，无夸大" },
  { "id": "brand_tone",      "category": "content",  "route_on_fail": "scriptwriter", "description": "品牌调性统一，语气一致" },
  { "id": "logic_clarity",   "category": "content",  "route_on_fail": "scriptwriter", "description": "内容逻辑清晰，结构合理" },
  { "id": "title_match",     "category": "content",  "route_on_fail": "scriptwriter", "description": "标题与正文内容匹配" },
  { "id": "privacy_safe",    "category": "safety",   "route_on_fail": "director",     "description": "截图中无未遮挡个人信息" },
  { "id": "no_false_claims", "category": "safety",   "route_on_fail": "planner",      "description": "无虚假宣传/未上线功能声称" },
  { "id": "copyright_safe",  "category": "safety",   "route_on_fail": "scriptwriter", "description": "无版权/名人姓名权风险" },
  { "id": "no_sensitive",    "category": "safety",   "route_on_fail": "planner",      "description": "无政治/宗教/敏感话题" }
]
```

每个条目的 `route_on_fail` 字段声明「此项失败时应路由到哪个阶段」，ReviserAgent 直接读取。

#### StructuredOutput Schema

每个 Auditor 输出固定 schema：

```python
response_schema = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id":      {"type": "STRING"},   # 对应 checklist 中的 id
            "passed":  {"type": "BOOLEAN"},
            "reason":  {"type": "STRING"}    # 简短理由，≤ 100 字
        },
        "required": ["id", "passed", "reason"]
    }
}
```

#### 投票汇总逻辑

```
对每个清单条目 item_id：
  votes = [auditor_A.passed, auditor_B.passed, auditor_C.passed]
  item.passed = (sum(votes) >= 2)   # 2/3 多数通过

overall_passed = all(item.passed for item in checklist)
```

#### 输出文件

- `/{daily_folder}/audit/audit_result.json` — 每条目投票明细 + 整体结论
- `/{daily_folder}/audit/audit_raw.md` — 各 Auditor 原始输出日志

#### 整体通过后

将 `creator/` 目录下所有文件拷贝至 `output/final/`，标记为可投放状态。

---

### 4.7 ReviserAgent（审计失败路由器）

**角色定位：** Audit 失败后的分类与路由决策层。不产生内容，只分析问题归属、决定从哪个阶段重跑，并携带修改指令。

#### 触发条件

仅当 `overall_passed = false` 时触发。

#### 工作流程

```
读取 audit_result.json（各条目投票明细）
      ↓
按 route_on_fail 字段收集所有失败条目
      ↓
取最上游的 route_to（优先级：planner > scriptwriter > director > creator）
      ↓
生成 revision_instructions（对应阶段的具体修改要求）
      ↓
【写入 LessonMemory】
  → 将每个失败条目（含违规内容片段）写入 lessons_{platform}.json
  → 确保下次创作时 Scriptwriter/Creator 可读取并规避同类错误
      ↓
检查 retry_count（当日累计重试次数）
  ├── < MAX_RETRIES（默认 2）→ 写入 revision_plan.json → Pipeline 从 route_to 续跑
  └── ≥ MAX_RETRIES → 写入 human_review_required.json → 停止自动重跑，等待人工
```

#### 路由优先级

多个失败条目同时存在时，取最上游阶段：

| 优先级 | 路由目标 | 触发条件示例 |
|--------|---------|-------------|
| 1（最上游） | `planner` | 虚假宣传、策略方向错误 |
| 2 | `scriptwriter` | 文案事实错误、调性偏差、版权问题 |
| 3 | `director` | 图片隐私遮挡缺失 |
| 4（最下游） | `creator` | 标题超长、字数不足（纯格式问题） |

> **设计原则**：路由到上游，下游的问题一并修复；不会出现「先修 Creator 再修 Scriptwriter」的反复。

#### 输出文件

**`/{daily_folder}/audit/revision_plan.json`**（正常重试时）：
```json
{
  "route_to": "scriptwriter",
  "retry_count": 1,
  "failed_items": ["fact_accuracy", "copyright_safe"],
  "revision_instructions": "1. 「不超过3秒」改为「几秒内」避免量化承诺；2. 将梅西真实姓名替换为虚构人名或球星昵称"
}
```

**`/{daily_folder}/audit/human_review_required.json`**（超限时）：
```json
{
  "status": "requires_human_review",
  "retry_count": 2,
  "date": "2026-03-22",
  "failed_items": ["no_false_claims", "copyright_safe"],
  "last_audit_result": "audit/audit_result.json",
  "note": "已自动重试 2 次，仍未通过。请人工审查后决定是否发布或放弃。"
}
```

> 人工介入界面：当前阶段记录状态文件，待后续 Web 前端接入后提供可视化操作入口。

#### 模型

`gemini-2.5-flash`（可配置，见 `llm_config.json` 的 `reviser` 字段）— 分类任务简单，不需要重型模型。

---

### 4.8 Strategist（策略反思团队）

**角色定位：** 基于真实投放数据反思，输出策略建议文档供 Planner 参考。

**触发时机：** 每次 Pipeline 运行的强制第一步（无论冷启动还是热启动）。Strategist 输出的 `strategy_suggestion.md` 作为 Planner 的必需输入。

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
| DataAnalyst | Gemini（默认 gemini-2.5-flash，可配置） | 解读数据（大上下文处理多篇历史记录），识别高/低表现内容特征 |
| StrategyReviewer | GPT（默认 gpt-5-nano，可配置） | 结合数据洞察，提出内容优化方向 |
| StrategyModerator | Claude（默认 claude-opus-4-6，可配置） | 输出结构化策略建议文档 |

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
│       ├── llm_config.json           # 各 Agent 模型配置（全部可切换）
│       ├── audit_checklist.json      # 共享审计清单
│       └── platforms/
│           └── xiaohongshu.json
├── requirements.txt
└── campaigns/                        # ← .gitignore 全部排除
    └── {product_name}/
        ├── product/                  # 产品资料（PRD、截图等）
        ├── strategy/                 # Strategist 输出（跨日期共享）
        │   └── strategy_suggestion_{date}.md
        ├── memory/                   # 长期记忆（LessonMemory）
        │   ├── lessons_xiaohongshu.json   # 小红书审计失败经验
        │   └── lessons_douyin.json        # 抖音审计失败经验（扩展时添加）
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

    # Step 1: Strategist（强制第一步，冷启动/热启动自动判断）
    strategy = await strategist.run(
        product=product,
        user_brief=load_user_brief(product),        # 产品级需求描述（创建项目时写）
        today_note=context.extra.get("today_note"), # 本次运行特殊要求（可选）
        feedback_data=load_latest_feedback(product) # None → 冷启动，有数据 → 热启动
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
| **展示层 - 后端** | **FastAPI** | 只读 REST API；Python 同栈，自动 OpenAPI 文档 |
| **展示层 - 前端** | **Vite + Vue 3 + Tailwind CSS** | 轻量 SPA；Composition API；快速开发 |

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

---

## 11. 展示层（Frontend + FastAPI）

### 11.1 设计目标

提供一个本地 Web 界面，支持完整的用户交互闭环：创建产品项目 → 触发流水线 → 浏览/审阅物料 → 接受/拒绝反馈 → 自动更新 LessonMemory。

**交互阶段：**
- **创建项目**：输入产品命名、上传 PRD、填写产品需求描述（user_brief，永久有效）
- **触发流水线**：每日运行前可填写 today_note（本次特殊要求，如「今天是情人节，写一篇相关的帖子」）；点击「开始运行」异步触发 Pipeline；右下角状态面板实时显示各阶段进度
- **审阅物料**：浏览帖子、下载图片、复制文案
- **接受/拒绝**：每个日期的素材包可点击「✅ 接受」或「❌ 拒绝 + 填写原因」；反馈自动写入 LessonMemory，供下次创作参考

### 11.2 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| API 后端 | FastAPI (Python) | 与 Pipeline 同语言，直接读 `campaigns/` 目录；自动生成 OpenAPI 文档 |
| 前端框架 | Vite + Vue 3 (Composition API) | 响应式数据驱动；与 Vite 原生配合；轻量 |
| UI 样式 | Tailwind CSS | 快速布局；无额外依赖 |
| Markdown 渲染 | marked.js | 渲染 `.md` 文件 |

### 11.3 目录结构

```
ai-marketing/
├── frontend/                    ← Vue 3 + Vite 前端
│   ├── src/
│   │   ├── views/
│   │   │   ├── Overview.vue     ← 今日总览（默认）
│   │   │   ├── PostDetail.vue   ← 帖子详情 + XHS 预览
│   │   │   ├── AuditReport.vue  ← 审核清单 per-item 明细
│   │   │   ├── PipelineLog.vue  ← 各阶段原始输出（折叠）
│   │   │   ├── AssetLibrary.vue ← 素材库图片浏览
│   │   │   └── LessonMemory.vue ← 历史经验记忆
│   │   ├── components/
│   │   │   ├── Sidebar.vue      ← 产品/日期导航树
│   │   │   ├── XhsPreview.vue   ← 小红书帖子仿真卡片
│   │   │   ├── ImageCarousel.vue← 图片轮播
│   │   │   └── AuditBadge.vue   ← 审核状态徽章
│   │   └── api/
│   │       └── index.js         ← API 调用封装（fetch）
│   ├── index.html
│   ├── vite.config.js           ← proxy /api → FastAPI
│   └── package.json
│
└── server/                      ← FastAPI 后端
    ├── main.py                  ← FastAPI 入口 + CORS
    ├── routers/
    │   ├── campaigns.py         ← 所有 /api/campaigns/* 路由
    │   └── images.py            ← 图片文件服务
    └── requirements.txt
```

### 11.4 FastAPI 接口设计

基准路径 `/api`。只读接口（GET）+ 写操作接口（POST）。

```
=== 只读接口 ===

GET  /api/products
     → 扫描 campaigns/ 目录，返回所有产品名（按字母排序）
     → ["原语", "Yuanyu", ...]

GET  /api/products/{product}/dates
     → 返回该产品所有已运行日期（降序），含每日 pipeline 状态摘要
     → [{"date": "2026-03-22", "passed": true, "stages_done": 5, "feedback": "accepted"}, ...]

GET  /api/products/{product}/{date}/state
     → 读取 .pipeline_state.json
     → 返回各阶段 done/success/summary

GET  /api/products/{product}/{date}/package
     → 读取 creator/post_package.json
     → 返回 title、body、hashtags、images 列表

GET  /api/products/{product}/{date}/audit
     → 读取 audit/audit_result.json
     → 返回 passed、各条目 votes 明细

GET  /api/products/{product}/{date}/file?path=plan/daily_marketing_plan.md
     → 读取 daily_folder 下任意文本文件
     → 返回 {content: "...", type: "markdown" | "json" | "text"}

GET  /api/products/{product}/assets
     → 读取 asset_library/index.json
     → 支持 ?type=generate&date=2026-03-22 筛选

GET  /api/products/{product}/memory/{platform}
     → 读取 memory/lessons_{platform}.json

GET  /api/images?path=campaigns/原语/daily/.../img_01.png
     → 读取图片文件，返回二进制（Content-Type: image/png）
     → 前端直接用作 <img src="/api/images?path=...">

GET  /api/products/{product}/run/status
     → 返回当前或最近一次 Pipeline 运行状态
     → {"running": true, "stage": "scriptwriter", "stages": {...}}

=== 写操作接口 ===

POST /api/products
     → 创建新产品项目
     → body: {"name": "原语", "user_brief": "这是一款..."}
     → 创建 campaigns/{name}/config/product_config.json

POST /api/products/{product}/config
     → 更新产品配置（user_brief 等）

POST /api/products/{product}/prd
     → 上传 PRD 文件（multipart/form-data）
     → 写入 campaigns/{product}/docs/

POST /api/products/{product}/run
     → 异步触发 Pipeline
     → body: {"today_note": "今天是情人节，写一篇相关的帖子"}（可选）
     → 在后台启动 main.py，立即返回 {"status": "started"}

POST /api/products/{product}/{date}/feedback
     → 提交用户接受/拒绝反馈
     → body: {"action": "accept"} 或 {"action": "reject", "reason": "..."}
     → 写入 daily_folder/feedback.json
     → 同步更新 memory/lessons_{platform}.json
```

**安全限制：** `file` 接口和 `images` 接口限制路径只能在 `campaigns/` 目录内，防止目录遍历。

### 11.5 六个核心视图

#### ① Overview（今日总览，默认视图）

选中产品+日期后展示，快速掌握当日状态：

```
[ ✅ 审核通过 ]  原语 · 2026-03-22 · xiaohongshu

Pipeline 状态
  ✅ Planner      以「翻译翻车→救场」的反差叙事为核心...
  ✅ Scriptwriter  AI把梅老板翻成煤老板，我3秒救回
  ✅ Director     素材编排完成：8/8 张成功
  ✅ Creator      发布包已组装，审核就绪
  ✅ Audit        审核通过（第 2 次，1 次重试后通过）

帖子摘要
  [封面缩略图]  标题 + 正文前 80 字 + hashtags
  [ 查看完整帖子 ]  [ 查看审核报告 ]  [ 流水线日志 ]
```

#### ② PostDetail（帖子详情 + 小红书仿真预览）

核心视图。左侧：小红书风格帖子卡片（CSS 模拟，非像素级）；右侧：图片缩略图列表。

```
┌──────────────────────┐  ┌─────────────────────────────────┐
│   [小红书帖子卡片]    │  │  图片列表（8张）                 │
│                      │  │  img_01 封面·翻车名场面    [下载] │
│   ←  [图片轮播]  →   │  │  img_02 翻车案例：老六     [下载] │
│   ────────────────   │  │  img_03 翻车案例：绝绝子   [下载] │
│   标题：AI把梅老板…  │  │  ...                             │
│                      │  │                                  │
│   正文（可展开）…    │  │  操作                            │
│                      │  │  [复制标题]  [复制正文]           │
│   #tag1 #tag2 #tag3  │  │  [复制话题标签]                  │
└──────────────────────┘  └─────────────────────────────────┘
```

**可执行操作（只读）：**
- 点击图片 → 原图预览（lightbox）
- 每张图片旁 [下载] → 触发浏览器 `<a download>` 下载
- [复制标题 / 正文 / 话题标签] → `navigator.clipboard.writeText()`

**小红书卡片样式设计：**
采用 CSS 模拟移动端卡片（圆角卡片 + 适当阴影），不引入手机外壳图片资源。重点呈现内容本身的阅读感受，与真实发布效果接近即可。

#### ③ AuditReport（审核报告）

```
总体结论：✅ 通过  （第 1 次重试后通过，共审核 2 次）

重试历史：[第1次 ❌ → Scriptwriter 修订] → [第2次 ✅]

条目明细（12 项）：
  条目             类别      3票结果      结论    代表理由
  title_length     platform  3通/0失      ✅      标题15字符合要求
  no_superlatives  platform  2通/1失      ✅      重试后无绝对化用语
  fact_accuracy    content   3通/0失      ✅      功能描述与PRD一致
  ...

展开每条目 → 显示 Auditor A/B/C 三票的具体理由
```

#### ④ PipelineLog（流水线日志）

按阶段折叠展示原始输出，方便 debug：

```
▼ Planner                              [2026-03-22 13:30]
  ├ daily_marketing_plan.md            [查看 Markdown]
  └ debate_raw.md（3轮辩论）           [查看 Markdown]

▼ Scriptwriter                         [2026-03-22 13:45]
  ├ daily_marketing_script.md          [查看 Markdown]
  └ debate_raw.md（2轮辩论）           [查看 Markdown]

▼ Director                             [2026-03-22 13:50]
  └ director_task_result.json（8任务） [查看 JSON]

▼ Creator                              [2026-03-22 14:05]
  ├ post_content.md                    [查看 Markdown]
  └ creator_raw.md                     [查看 Markdown]

▼ Audit                                [2026-03-22 14:10]
  └ audit_raw.md（3 Auditor 原始投票）[查看 Markdown]
```

文件内容在右侧面板（或 modal）中展示，Markdown 渲染，JSON 语法高亮。

#### ⑤ AssetLibrary（素材库）

```
[筛选：全部 | generate | screenshot]  [排序：最新 | 使用次数]

 ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
 │      │ │      │ │      │ │      │
 │ img  │ │ img  │ │ img  │ │ img  │
 │      │ │      │ │      │ │      │
 └──────┘ └──────┘ └──────┘ └──────┘
 generate  generate  generate  generate
 2026-03-22  used×1  2026-03-22  used×0

点击图片：展开 prompt、asset_id、使用日期       [下载]
```

#### ⑥ LessonMemory（经验记忆）

```
平台：xiaohongshu    共 12 条经验

  条目              类别      违规次数  规则摘要
  title_length      platform    1      标题不超过20字...
  no_superlatives   platform    1      不使用绝对化用语...
  fact_accuracy     content     1      功能描述与PRD一致...
  ...

展开每条 → 显示完整规则 + 反例内容
```

### 11.6 新增交互组件

#### 创建项目 Modal（`components/CreateProjectModal.vue`）

```
┌─────────────────────────────────────────┐
│           新建产品项目                   │
├─────────────────────────────────────────┤
│  产品名称   [ 原语                    ]  │
│                                         │
│  产品需求描述（user_brief）：             │
│  ┌─────────────────────────────────┐    │
│  │ 原语是一款AI辅助翻译工具，       │    │
│  │ 主要面向职场人群和学生...        │    │
│  └─────────────────────────────────┘    │
│                                         │
│  上传 PRD（可选）  [ 选择文件 ]           │
│                                         │
│  [ 取消 ]              [ 创建项目 ]      │
└─────────────────────────────────────────┘
```

#### 运行触发 Panel（`components/RunPanel.vue`）

```
┌─────────────────────────────────────────┐
│  今日运行备注（today_note，可选）          │
│  ┌─────────────────────────────────┐    │
│  │ 今天是情人节，希望写一篇与...    │    │
│  └─────────────────────────────────┘    │
│                                         │
│  [ 🚀 开始运行流水线 ]                   │
└─────────────────────────────────────────┘
```

#### 右下角实时状态面板（`components/PipelineStatusPanel.vue`）

```
┌──────────────────────────────┐  ← 可折叠，默认展开（运行时）
│  流水线进行中...  [─]         │
├──────────────────────────────┤
│  ✅ Strategist    13:30:12   │
│  ✅ Planner       13:35:48   │
│  🔄 Scriptwriter  进行中...  │
│  ⏳ Director                 │
│  ⏳ Creator                  │
│  ⏳ Audit                    │
└──────────────────────────────┘
```

轮询 `/api/products/{product}/run/status`（每 3 秒），更新各阶段状态图标。

#### 接受/拒绝 操作区（集成到 Overview 或 PostDetail）

```
┌─────────────────────────────────────────┐
│  用户操作                                │
│                                         │
│  [ ✅ 接受并准备发布 ]                   │
│                                         │
│  [ ❌ 拒绝 ]  拒绝原因：                 │
│  ┌─────────────────────────────────┐    │
│  │ 整体风格过于硬广，不符合小红书   │    │
│  │ 社区调性...                      │    │
│  └─────────────────────────────────┘    │
│  [ 提交拒绝 ]                           │
└─────────────────────────────────────────┘
```

接受/拒绝后状态固化，不可撤销（防止重复提交）。反馈即时写入 LessonMemory。

### 11.7 布局结构（更新版）

```
┌─────────────────────────────────────────────────────────────────┐
│  AI Marketing Studio            [+ 新建项目]    [今日 03-22]    │
├──────────────┬──────────────────────────────────────────────────┤
│  CAMPAIGNS   │                                                   │
│              │          主内容区（视图切换）                     │
│  原语  [▶运行]│                                                   │
│  ├ 03-22 ✅接│  [Overview] [帖子预览] [审核报告] [日志] 标签栏   │
│  └ 03-21 ❌拒│                                                   │
│              │                                                   │
│  ──────────  │                                                   │
│  素材库      │                                                   │
│  经验记忆    │                                        ┌────────┐ │
│              │                           右下角状态面板 │流水线  │ │
│              │                           （可折叠）    │进行中  │ │
└──────────────┴────────────────────────────────────────┴────────┘
```

- 左侧：导航树，每个日期显示反馈状态（✅接受 / ❌拒绝 / ⬜未处理）
- 产品级「▶运行」按钮触发当日 Pipeline
- 右下角悬浮状态面板（运行时展开，完成后自动折叠）
- 每个日期下有 4 个标签（Overview / 帖子预览 / 审核报告 / 日志）
- 素材库和经验记忆为产品级全局视图（不区分日期）

### 11.8 开发说明

**本地启动方式（开发期）：**
```bash
# 启动 FastAPI（端口 8000）
cd server && uvicorn main:app --reload

# 启动 Vite 前端（端口 5173，/api 代理到 8000）
cd frontend && npm run dev
```

**Vite proxy 配置（`frontend/vite.config.js`）：**
```js
export default {
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
}
```

**生产部署：**
```bash
npm run build   # 生成 frontend/dist/
# FastAPI 同时 serve dist/ 静态文件 + /api 路由
# 单进程启动，无需 Nginx
```
