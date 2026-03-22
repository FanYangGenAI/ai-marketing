# TODO List — develop/develop-agents

> 分支：`develop/develop-agents`
> 创建日期：2026-03-17
> 前置：`develop/develop-skills` 已合并到 main ✅
> 目标：实现全部 Agent + Orchestrator 主流程，跑通完整 pipeline

---

## 阶段一：Agent 基类与共享接口

- [ ] **#1** `src/agents/base.py` — 定义 `BaseAgent` 抽象类
  - 属性：`name`, `llm_client`, `role_description`
  - 方法：`async run(context) -> AgentOutput`
  - 数据类：`AgentContext`（campaign 路径 + 当日输入），`AgentOutput`（输出文件路径 + 摘要）

---

## 阶段二：Strategist（策略反思，冷/热启动）

- [ ] **#2** `src/agents/strategist/strategist.py`
  - 读取：历史投放数据摘要 + 用户反馈
  - 调用 Debate→Synthesize（StrategyDataAnalyst/Gemini, StrategyReviewer/GPT-4o, StrategyModerator/Claude）
  - 输出：`campaigns/{product}/strategy_suggestion.md`

---

## 阶段三：Planner（每日内容策划）

- [ ] **#3** `src/agents/planner/planner.py`
  - 读取：strategy_suggestion.md + 近30天 Campaign Memory 摘要 + 用户当日输入
  - PlannerA (Gemini)：调用 web-search Skill 获取热点
  - PlannerB (Claude)：深度解读 PRD 亮点
  - PlannerC (GPT-4o)：用户视角洞察
  - PlannerModerator (Claude)：Debate→Synthesize 收敛
  - 输出：`{daily_folder}/plan/daily_marketing_plan.md`

- [ ] **#4** `src/agents/planner/campaign_memory.py`
  - 扫描近 N 天的 `plan/` 目录，生成「已覆盖话题摘要」
  - 用于防止 Planner 重复选题

- [ ] **#5** `src/orchestrator/platform_adapter.py`
  - 读取 `src/config/platforms/xiaohongshu.json`
  - 将平台规范（字数限制、图片比例、禁用词）注入到计划书上下文

---

## 阶段四：Scriptwriter（文案创作）

- [ ] **#6** `src/agents/scriptwriter/scriptwriter.py`
  - 读取：daily_marketing_plan.md + 平台规范
  - ScriptwriterA (GPT-4o)：叙事结构设计
  - ScriptwriterB (Gemini)：视觉指令描述（配图方向）
  - ScriptwriterC (GPT-4o)：小红书口语化文案
  - ScriptwriterModerator (Claude)：Debate→Synthesize 收敛
  - 输出：`{daily_folder}/script/daily_marketing_script.md`

---

## 阶段五：Director（素材编排）

- [ ] **#7** `src/agents/director/director.py`
  - 读取：daily_marketing_script.md + Asset Library 索引
  - 生成 `task_list`（需要哪些图片/截图/文生图，以及顺序）
  - 检查 Asset Library 是否有可复用素材
  - 调用 Skills：product-screenshot / gemini-imagegen / crop-resize / text-overlay / privacy-mask
  - 输出：`{daily_folder}/assets/raw/` 下的所有素材 + `director_task_result.json`

---

## 阶段六：Creator（物料组装）

- [ ] **#8** `src/agents/creator/creator.py`
  - 读取：daily_marketing_script.md + director_task_result.json + 平台规范
  - 按脚本将素材、文案、话题标签组装为平台发布包
  - 输出：`{daily_folder}/output/draft/` 下的组装物料清单

---

## 阶段六·五：模型配置统一（已完成）

- [x] **#8a** `src/config/llm_config.json`
  - 创建统一的 LLM 模型配置文件（所有 Agent 驱动模型在此声明）
  - 默认 GPT 模型：`gpt-5-nano`；Gemini：`gemini-2.5-flash`；Claude：`claude-opus-4-6`
  - 各 Agent 构造时从配置中读取模型名（不硬编码）

---

## 阶段七：Audit v2（已完成）

- [x] **#9a** `src/config/audit_checklist.json`
  - 共享审计清单，12 个条目，Platform / Content / Safety 三类

- [x] **#9b** `src/llm/gemini_client.py` — `chat_structured()` 方法
  - 调用 Gemini StructuredOutput，返回已解析 Python 对象
  - max_tokens=8192 防止中文 12 条目输出截断（已 bugfix）

- [x] **#9c** `src/agents/audit/audit.py` — Audit v2
  - 3× Gemini 并行 + per-item 2/3 多数投票
  - 通过时自动拷贝 `creator/` 文件及图片到 `output/final/`

---

## 阶段七·五：ReviserAgent + LessonMemory（已完成）

- [x] **#9d** `src/agents/reviser/reviser.py`
  - 读取失败条目 → 确定最上游路由阶段 → LLM 生成修订指令
  - 写入 LessonMemory；超限写 human_review_required.json

- [x] **#9e** `src/orchestrator/lesson_memory.py`
  - `load()` / `inject_prompt()` / `write_lessons()`
  - 按 platform 隔离，失败条目去重累计

- [x] **#10a** `src/orchestrator/pipeline.py` — Audit 失败回路
  - Audit 失败 → ReviserAgent → 从 route_to 续跑
  - `from_step` 指定时自动重置 retry_count（bugfix）

---

## 阶段八：Orchestrator 主流程（已完成）

- [x] **#10** `src/orchestrator/pipeline.py` — 基础版本
  - 串联：Planner → Scriptwriter → Director → Creator → Audit
  - 支持断点续跑（`.pipeline_state.json`）
  - 支持 `--from-step` / `--to-step` 精确控制范围

- [x] **#11** `main.py`（CLI 入口）
  - `python main.py --product "MyApp" --prd docs/prd.md`
  - 支持 `--from-step` / `--to-step` / `--dry-run`

---

## 阶段九：测试（待启动）

- [ ] **#12** `tests/agents/` — 各 Agent 单元测试（mock LLM 调用，验证文件输出）
- [ ] **#13** `tests/orchestrator/test_pipeline.py` — Pipeline 集成测试（端到端冒烟）
- [ ] **#14** 完整链路手动验证：输入真实 PRD，观察每个阶段的输出文件

---

## 阶段十：展示层 Frontend + FastAPI（新增）

> 目标：提供本地 Web 界面，让用户浏览、审阅所有 Pipeline 输出数据，下载投放物料。当前阶段只读。
> 技术栈：FastAPI（Python）+ Vite + Vue 3 + Tailwind CSS
> 详细设计见：`docs/system-design-draft.md` § 11

### 后端（FastAPI）

- [ ] **#15a** `server/main.py` + `server/routers/campaigns.py`
  - FastAPI 应用入口，CORS 配置，静态文件服务（生产模式 serve `frontend/dist/`）
  - 实现全部只读路由：
    - `GET /api/products` → 扫描 `campaigns/` 返回产品列表
    - `GET /api/products/{product}/dates` → 返回日期列表 + 每日状态摘要
    - `GET /api/products/{product}/{date}/state` → pipeline state
    - `GET /api/products/{product}/{date}/package` → post_package.json
    - `GET /api/products/{product}/{date}/audit` → audit_result.json
    - `GET /api/products/{product}/{date}/file?path=` → 任意文本文件（路径限 campaigns/）
    - `GET /api/products/{product}/assets` → asset_library/index.json
    - `GET /api/products/{product}/memory/{platform}` → lessons_{platform}.json

- [ ] **#15b** `server/routers/images.py`
  - `GET /api/images?path=` → 读取图片二进制，路径限 `campaigns/` 目录内

### 前端（Vue 3 + Vite）

- [ ] **#15c** 项目脚手架 + Sidebar 导航
  - `frontend/` 目录初始化（`npm create vite`，Vue 3 + Tailwind）
  - `vite.config.js`：`/api` 代理到 `http://localhost:8000`
  - `Sidebar.vue`：产品/日期导航树，点击切换主视图
  - `App.vue`：路由切换（vue-router 或手动状态）

- [ ] **#15d** Overview + PostDetail 视图
  - `Overview.vue`：Pipeline 阶段状态列表 + 帖子摘要卡片
  - `PostDetail.vue`：小红书风格帖子预览卡片（CSS 模拟）
    - `ImageCarousel.vue`：图片轮播，支持点击大图预览（lightbox）
    - 每张图片：[下载] 按钮 → `<a download>` 触发浏览器下载
    - [复制标题] / [复制正文] / [复制话题标签] → `navigator.clipboard.writeText()`

- [ ] **#15e** AuditReport + PipelineLog 视图
  - `AuditReport.vue`：12 条目表格，含 3 票明细展开、重试历史
  - `PipelineLog.vue`：阶段折叠列表，右侧 Markdown / JSON 预览面板
    - Markdown：marked.js 渲染
    - JSON：语法高亮（highlight.js 或 prism.js）

- [ ] **#15f** AssetLibrary + LessonMemory 视图
  - `AssetLibrary.vue`：图片网格，支持 type/date 筛选，点击查看 prompt + 下载
  - `LessonMemory.vue`：经验记忆表格，展开显示规则全文和反例

---

## 执行顺序（更新）

```
（已完成）
#8a → #9a → #9b → #9c → #9e → #9d → #10a → #10 → #11

（下一阶段：展示层）
#15a (FastAPI 后端 + 基础路由)
    ↓
#15b (图片服务)
    ↓
#15c (Vue 项目脚手架 + Sidebar)
    ↓
#15d (Overview + PostDetail，含图片下载/复制文案)
    ↓
#15e (AuditReport + PipelineLog)
    ↓
#15f (AssetLibrary + LessonMemory)

（后续）
#12 → #13 → #14 （单元测试 + 集成测试）
```

---

## 进度总览

| # | 任务 | 状态 |
|---|------|------|
| 1 | BaseAgent 基类 | ✅ 完成 |
| 2 | Strategist | ⬜ 待开始 |
| 3 | Planner | ✅ 完成并验收 |
| 4 | CampaignMemory | ✅ 完成 |
| 5 | PlatformAdapter | ✅ 完成 |
| 6 | Scriptwriter | ✅ 完成并验收 |
| 7 | Director | ✅ 完成并验收 |
| 8 | Creator | ✅ 完成并验收 |
| 8a | llm_config.json（模型统一配置） | ✅ 完成 |
| 9 | Audit v1（旧版） | ✅ 已替换为 v2 |
| 9a | audit_checklist.json | ✅ 完成 |
| 9b | GeminiClient.chat_structured | ✅ 完成（含 bugfix） |
| 9c | AuditAgent v2（共享清单+投票） | ✅ 完成（含 bugfix） |
| 9d | ReviserAgent（含 LessonMemory 写入） | ✅ 完成 |
| 9e | LessonMemory 模块 | ✅ 完成 |
| 10 | Pipeline 基础版 | ✅ 完成 |
| 10a | Pipeline Audit 失败回路 + LessonMemory 注入 | ✅ 完成（含 bugfix） |
| 11 | main.py CLI 入口 | ✅ 完成 |
| 12 | Agent 单元测试 | ⬜ 待开始 |
| 13 | Pipeline 集成测试 | ⬜ 待开始 |
| 14 | 完整链路手动验证 | ✅ 已完成（2026-03-22 原语首跑验收） |
| 15a | FastAPI 后端 + 路由 | ⬜ 待开始 |
| 15b | 图片文件服务 | ⬜ 待开始 |
| 15c | Vue 脚手架 + Sidebar 导航 | ⬜ 待开始 |
| 15d | Overview + PostDetail（下载/复制） | ⬜ 待开始 |
| 15e | AuditReport + PipelineLog | ⬜ 待开始 |
| 15f | AssetLibrary + LessonMemory | ⬜ 待开始 |
