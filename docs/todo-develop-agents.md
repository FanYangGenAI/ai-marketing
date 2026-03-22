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

## 阶段二：Strategist（每次 Pipeline 的强制第一步）

- [ ] **#2** `src/agents/strategist/strategist.py`
  - **触发时机**：每次 Pipeline 运行的第一步（无论冷/热启动，强制执行）
  - 读取：`user_brief`（产品级永久需求）+ `today_note`（本次运行特殊要求，可选）+ 历史投放数据（有则热启动，无则冷启动）
  - 调用 Debate→Synthesize（StrategyDataAnalyst/Gemini, StrategyReviewer/GPT-4o, StrategyModerator/Claude）
  - 冷启动：搜索行业规律，输出起步策略建议
  - 热启动：分析历史投放数据，输出优化策略建议
  - 输出：`campaigns/{product}/strategy/strategy_suggestion_{date}.md`

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
  - [ ] **#9e-ext** 扩展为双向学习信号：
    - `write_rejection(reason, date)` — 用户拒绝反馈写入负向经验
    - `write_acceptance(theme, title, date)` — 用户接受反馈写入正向经验
    - 数据结构中新增 `signal`（positive/negative）和 `source`（audit_failure/user_rejection/user_acceptance）字段

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

## 阶段八·五：版本号抑制 + user_brief 注入

- [ ] **#11a** `campaigns/{product}/config/product_config.json` 新增字段
  - `suppress_version_in_copy: true`（默认 true，可在 product_config 中关闭）
  - `user_brief`：产品级永久需求描述（创建项目时写，后续 Strategist 读取）

- [ ] **#11b** Scriptwriter system prompt 注入版本号抑制规则
  - 读取 product_config.json 中的 `suppress_version_in_copy`
  - 若为 true，在 system prompt 中注入：「文案中不出现具体版本号（如 v1.2、3.0），除非 today_note 中明确要求」

---

## 阶段九：测试（待启动）

- [ ] **#12** `tests/agents/` — 各 Agent 单元测试（mock LLM 调用，验证文件输出）
- [ ] **#13** `tests/orchestrator/test_pipeline.py` — Pipeline 集成测试（端到端冒烟）
- [ ] **#14** 完整链路手动验证：输入真实 PRD，观察每个阶段的输出文件

---

## 执行顺序

```
（已完成）
#8a → #9a → #9b → #9c → #9e → #9d → #10a → #10 → #11

（待启动，按优先级）
#2   （Strategist，每次 Pipeline 强制第一步）
#11a → #11b  （版本号抑制 + user_brief 注入）
#9e-ext  （LessonMemory 双向学习信号扩展）
#12 → #13 → #14 （单元测试 + 集成测试）
```

---

## 进度总览

| # | 任务 | 状态 |
|---|------|------|
| 1 | BaseAgent 基类 | ✅ 完成 |
| 2 | Strategist（每次 Pipeline 强制第一步） | ⬜ 待开始 |
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
| 11a | product_config.json 扩展（user_brief + suppress_version） | ⬜ 待开始 |
| 11b | Scriptwriter 版本号抑制规则注入 | ⬜ 待开始 |
| 9e-ext | LessonMemory 双向学习信号（接受/拒绝） | ⬜ 待开始 |
| 14 | 完整链路手动验证 | ✅ 已完成（2026-03-22 原语首跑验收） |
