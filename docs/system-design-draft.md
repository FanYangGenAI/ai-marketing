# AI Marketing Multi-Agent System — Design Draft v0.1

> 状态：草稿，待讨论确认
> 日期：2026-03-17

---

## 1. 系统目标

输入用户的**产品 PRD** 和**可运行产品**，系统自动生成一份**定时的物料清单**，内容包括每天在小红书（首期）、抖音、TikTok 等平台发布所需的文章、图文、短视频等。

系统是一个**自循环、可自进化**的 multi-agent pipeline：
- 通过每日投放数据反馈不断优化策略
- 用户充当 human-in-the-loop，负责提供产品资料、最终确认物料和手动投放
- 随着历史数据积累，系统决策质量持续提升

---

## 2. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER                                      │
│  输入：PRD / 产品 / 想法建议 / 平台反馈数据                         │
│  输出：确认物料清单 → 手动投放                                       │
└──────────┬───────────────────────────────────┬───────────────────┘
           │ 产品资料 + 用户建议                 │ 平台反馈数据
           ▼                                   ▼
  ┌────────────────┐                  ┌────────────────┐
  │   Planner      │◄─────────────────│  Strategist    │
  │  每日营销计划   │   策略建议文档     │  反思 & 策略    │
  └────────┬───────┘                  └────────────────┘
           │ 每日营销计划书 (markdown)
           ▼
  ┌────────────────┐     ┌──────────────────────┐
  │Platform Adapter│────►│  Platform Specs DB   │
  │  平台适配层     │     │  各平台格式/风格规范   │
  └────────┬───────┘     └──────────────────────┘
           │ 各平台版本计划
           ▼
  ┌────────────────┐
  │  Scriptwriter  │
  │  操作脚本创作   │
  └────────┬───────┘
           │ 每日营销脚本 (markdown)
           ▼
  ┌────────────────┐     ┌──────────────────────┐
  │   Director     │────►│    Asset Library     │
  │  素材生成       │     │    素材库             │
  └────────┬───────┘     └──────────┬───────────┘
           │                        │
           ▼                        ▼
  ┌────────────────┐     ┌──────────────────────┐
  │    Creator     │◄────│  Asset Library       │
  │  物料组装       │     │  (复用历史素材)        │
  └────────┬───────┘     └──────────────────────┘
           │ 待审物料
           ▼
  ┌────────────────┐
  │     Audit      │
  │  合规 & 质量审核 │
  └────────┬───────┘
           │ [Human Final Confirm]
           ▼
  ┌────────────────┐
  │  每日投放物料清单 │
  │  定时发布计划   │
  └────────────────┘
```

---

## 3. Agent 详细设计

### 3.1 Planner（每日营销策划团队）

**角色定位：** 整个系统的"大脑"，负责制定每日营销方向和内容计划。

**输入：**
- 产品 PRD（首次运行时提供，后续有更新时增量输入）
- 可运行产品的实际功能截图/录屏
- Strategist 输出的最新策略建议文档
- 用户临时想法和建议
- Campaign Memory（历史发布内容记录）
- 实时网络趋势（通过 Search Skill）

**Agent 构成（讨论模式）：**
- `PlannerA` — 偏向数据和趋势分析，关注热点话题
- `PlannerB` — 偏向产品功能亮点挖掘
- `PlannerC` — 偏向目标用户视角和痛点共鸣
- `PlannerModerator` — 负责主持讨论，推动收敛，输出最终文档

**讨论机制：**
1. PlannerA 搜索当日相关热点，提出话题方向（2-3 个）
2. PlannerB 结合产品功能，给每个方向找到最强结合点
3. PlannerC 从用户视角评估每个方向的共鸣度
4. 多轮 debate → PlannerModerator 综合，输出最终计划书

**输出：** `/{daily_folder}/plan/daily_marketing_plan.md`

**计划书结构：**
```markdown
# 每日营销计划 - {date}

## 今日主题
## 目标平台（首期：小红书）
## 内容方向（1-3 个）
### 方案一：{标题}
- 核心卖点
- 目标用户
- 内容形式（图文/视频）
- 关键词 / 话题标签
- 参考热点
## 本次不做的方向（及原因）
## 参考历史（避免重复）
```

---

### 3.2 Platform Adapter（平台适配层）

**角色定位：** 将通用营销计划翻译成各平台的具体规范要求。首期聚焦**小红书图文**。

**小红书图文规范（内置知识库）：**
| 维度 | 规范 |
|------|------|
| 图片数量 | 1-9 张，建议 3-6 张 |
| 图片尺寸 | 3:4 竖版 或 1:1 方图 |
| 标题 | ≤20 字，要有钩子词 |
| 正文 | 500-1000 字，口语化 |
| 话题标签 | 3-8 个，头部+长尾混合 |
| 风格 | 真实感、生活化、有用 |
| 封面 | 第一张图最重要，要有文字overlay |

**输出：** 在计划书基础上附加平台规范注释，传递给 Scriptwriter。

---

### 3.3 Scriptwriter（脚本创作团队）

**角色定位：** 专业的策划和脚本创作者，将营销计划转化为可执行的操作脚本。

**输入：**
- `daily_marketing_plan.md` + 平台规范
- 产品可运行版本（用于截屏/录屏指导）

**Agent 构成（讨论模式）：**
- `ScriptwriterA` — 专注叙事结构，负责整体故事线
- `ScriptwriterB` — 专注视觉表达，负责每张图的具体拍摄/截屏指令
- `ScriptwriterC` — 专注文案创作，负责标题、正文、话题标签
- `ScriptwriterModerator` — 汇总，确保脚本可操作性

**输出：** `/{daily_folder}/script/daily_marketing_script.md`

**脚本结构（以小红书图文为例）：**
```markdown
# 营销脚本 - {date} - {方案名}

## 目标平台：小红书
## 内容形式：图文（共N张）

## 标题
{最终确定标题}

## 封面图（图1）
- 素材来源：[截屏 / 重用素材 / 新生成]
- 如需截屏：打开产品 → 进入{功能}界面 → 截取{区域}
- 视觉要求：高亮{元素}，添加文字"{overlay文字}"
- 尺寸：3:4，1080x1440px

## 内容图（图2-图N）
...

## 正文
{完整文案}

## 话题标签
#{tag1} #{tag2} ...

## Director 任务清单
- [ ] 截屏任务1：{具体指令}
- [ ] 生成任务2：{具体指令}
- [ ] 复用素材：{Asset Library ID}
```

---

### 3.4 Director（素材生成团队）

**角色定位：** 根据脚本的 Director 任务清单，调用各种 Skill 生成原始素材。

**输入：** `daily_marketing_script.md` 中的 Director 任务清单 + Asset Library（查重复用）

**Agent 构成：**
- `DirectorAgent`（1个或多个并行）— 执行具体任务，调用 Skill
- `AssetLibraryManager` — 任务前先查询 Asset Library，避免重复生成；任务后入库

**Skill 体系（封装好的原子能力）：**

```
skills/
├── screenshot.py        # 截取产品界面截图
├── screen_record.py     # 录制产品操作视频
├── image_gen.py         # 调用 Gemini/其他 API 生成图片
├── image_edit.py        # 图片裁剪、加字、调色（Pillow）
├── video_clip.py        # 视频剪辑（MoviePy）
└── text_overlay.py      # 给图片/视频添加文字
```

**Skill 调用示例：**
```python
# Agent 通过工具调用 Skill，而不是直接操作软件
result = skills.image_gen(
    prompt="产品UI界面风格，蓝白配色，简洁现代",
    provider="gemini",  # 或 dalle, stable_diffusion
    size="1080x1440",
    output_path=f"{daily_folder}/assets/"
)
```

**输出：** 素材文件写入 `/{daily_folder}/assets/raw/`，并更新 Asset Library 索引

---

### 3.5 Creator（物料组装团队）

**角色定位：** 根据脚本和 Director 生成的素材，组装成最终可投放的物料。

**输入：** `daily_marketing_script.md` + `/{daily_folder}/assets/raw/` + Asset Library

**工作内容：**
1. 按脚本顺序排列图片
2. 调整尺寸到平台规范
3. 添加文字 overlay（封面标题等）
4. 生成最终图片/视频文件

**输出：** `/{daily_folder}/output/final/`

---

### 3.6 Audit（审计团队）

**角色定位：** 多维度审核最终物料，确保合规、安全、质量达标。

**Agent 构成（多角色审核）：**
- `PlatformAuditor` — 检查是否符合小红书平台规范和风格
- `ContentAuditor` — 检查内容准确性（不夸大功能、不虚假宣传）
- `SafetyAuditor` — 隐私数据、版权、敏感内容检查

**审核项目清单（小红书版）：**
- [ ] 图片数量符合规范（1-9张）
- [ ] 图片尺寸正确（3:4 或 1:1）
- [ ] 标题不超过20字
- [ ] 无夸大宣传词（"最强"、"第一"等）
- [ ] 无隐私数据曝露（截图中用户信息已遮挡）
- [ ] 话题标签合规
- [ ] 产品截图清晰无水印问题

**输出：** `/{daily_folder}/audit/audit_report.md` + 审核通过的 final 物料

---

### 3.7 Strategist（策略反思团队）

**角色定位：** 基于真实投放数据进行反思，输出可指导下一次 Planner 的策略建议。

**输入：** 用户提供的历史投放数据（点赞、转发、评论、阅读量、热度趋势）

**冷启动策略：**
- 当无历史数据时，Strategist 提供基于平台通用规律的初始策略建议
- 例如：小红书图文首帖建议聚焦"真实体验"类内容，封面要有强视觉冲击

**Agent 构成：**
- `DataAnalyst` — 解读数据，找出高/低表现内容的共同特征
- `StrategyReviewer` — 结合数据和行业知识，提出改进方向
- `StrategyModerator` — 输出结构化策略建议文档

**输出：** `/{campaign_root}/strategy/strategy_suggestion_{date}.md`

---

## 4. 文件系统结构

```
ai-marketing/
├── docs/                          # 系统文档
├── src/                           # 源代码
│   ├── agents/                    # 各 agent 实现
│   ├── skills/                    # Skill 封装
│   └── orchestrator/              # 编排逻辑
├── campaigns/                     # 所有活动数据（不进 git，或选择性提交）
│   └── {product_name}/
│       ├── product/               # 产品资料（PRD、截图等）
│       ├── strategy/              # Strategist 输出（跨日期共享）
│       ├── asset_library/         # 素材库索引
│       │   └── index.json         # 素材元数据
│       └── daily/
│           └── {YYYY-MM-DD}/
│               ├── plan/
│               │   └── daily_marketing_plan.md
│               ├── script/
│               │   └── daily_marketing_script.md
│               ├── assets/
│               │   ├── raw/       # Director 生成的原始素材
│               │   └── processed/ # Creator 处理后的素材
│               ├── output/
│               │   └── final/     # 最终投放物料
│               └── audit/
│                   └── audit_report.md
└── requirements.txt
```

---

## 5. 编排逻辑（Orchestrator）

```
每日触发（手动 or 定时）：

1. Strategist.run(feedback_data)         # 有数据则分析，无则冷启动
       ↓
2. Planner.run(prd, strategy, memory, user_input)
       ↓
3. Platform Adapter.adapt(plan, platform="xiaohongshu")
       ↓
4. Scriptwriter.run(adapted_plan)
       ↓
5. Director.run(script.task_list)        # 并行执行多个素材任务
       ↓
6. Creator.run(script, assets)
       ↓
7. Audit.run(output, script, plan)
       ↓
8. 生成最终投放清单 → 等待用户确认 → 手动投放
```

---

## 6. Agent 间讨论收敛机制

每个需要多 agent 讨论的节点，采用统一的 **Debate → Synthesize** 模式：

```
Round 1: 各 agent 独立发言（parallel）
Round 2: 各 agent 对其他人的观点进行点评（parallel）
Round 3: Moderator 综合所有观点，输出结论（sequential）
```

最大讨论轮数：3 轮（可配置），超时则 Moderator 强制收敛。

---

## 7. 技术栈

| 层次 | 技术选型 |
|------|----------|
| LLM | Claude API (claude-sonnet-4-6) |
| Multi-agent 框架 | Anthropic SDK + 自定义 Orchestrator |
| 图像生成 Skill | Gemini CLI / Gemini API |
| 图像处理 Skill | Pillow, OpenCV |
| 视频处理 Skill | MoviePy, FFmpeg |
| 截屏 Skill | Playwright (headless browser) |
| 趋势搜索 Skill | Tavily API 或 Brave Search API |
| 数据持久化 | JSON 文件（轻量，跟随项目文件夹） |
| 环境隔离 | Python venv（近期），Docker（后期沙箱） |

---

## 8. 首期实现范围（MVP）

聚焦最小可行路径，验证核心 pipeline：

- [ ] **平台：** 小红书图文（3-6张图 + 标题 + 正文）
- [ ] **完整走通：** Planner → Scriptwriter → Director（截图+文字overlay）→ Creator → Audit
- [ ] **Strategist：** 冷启动版（无历史数据时给出通用建议）
- [ ] **Skill：** screenshot, text_overlay, image_gen（Gemini）
- [ ] **Human-in-loop：** Audit 后输出清单，人工确认后手动发布

暂不包括：
- 抖音 / TikTok 视频流
- 自动接入平台 API 获取实时反馈
- Docker 沙箱（先用本地 venv）

---

## 9. 待讨论问题

1. **Planner 中的实时搜索**：Tavily 还是其他搜索工具？是否有偏好？
2. **Gemini 接入方式**：通过 CLI 调用还是直接走 Gemini API？你提到了 gemini cli 和 gemini web，需要确认。
3. **Asset Library 的查重策略**：按内容哈希？按语义相似度？还是简单按标签索引？
4. **多 agent 讨论的实现**：是用 Claude 的 multi-turn conversation 模拟不同 agent，还是并发调用多个独立 Claude 实例？
5. **campaigns/ 目录是否 gitignore**：素材文件可能很大，是否需要 Git LFS 或完全排除在版本控制之外？
