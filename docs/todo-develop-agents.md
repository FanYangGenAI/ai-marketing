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

## 阶段六·五：模型配置统一（新增）

- [ ] **#8a** `src/config/llm_config.json`
  - 创建统一的 LLM 模型配置文件（所有 Agent 驱动模型在此声明）
  - 默认 GPT 模型：`gpt-5-nano`；Gemini：`gemini-2.5-flash`；Claude：`claude-opus-4-6`
  - 各 Agent 构造时从配置中读取模型名（不硬编码）

---

## 阶段七：Audit v2（共享清单 + Gemini StructuredOutput + 投票）

- [ ] **#9a** `src/config/audit_checklist.json`
  - 创建共享审计清单文件（12 个初始条目，含 `id`、`category`、`route_on_fail`、`description`）
  - 可扩展、可编辑，Platform / Content / Safety 三类

- [ ] **#9b** `src/llm/gemini_client.py` — 新增 `chat_structured()` 方法
  - 接受 `response_schema: dict` 参数
  - 调用 Gemini API 的 `response_mime_type="application/json"` + `response_schema`
  - 返回已解析的 Python 对象（不再是字符串），彻底消除 JSON 解析错误
  - 模型从 `llm_config.json` 读取（默认 `gemini-2.5-flash`，支持切换至 `gemini-3.1-flash` 等）

- [ ] **#9c** `src/agents/audit/audit.py` — 全面重写
  - 读取 `audit_checklist.json` 动态加载清单
  - 3 个 Gemini 实例并行，每实例用 `chat_structured()` 对全部清单条目给出 `{id, passed, reason}`
  - 按条目汇总：2/3 多数投票决定每条目结论
  - 写入 `audit/audit_result.json`（含每条目三票明细 + 整体 passed）
  - 通过 → 拷贝 `creator/` 到 `output/final/`

---

## 阶段七·五：ReviserAgent + LessonMemory（新增）

- [ ] **#9d** `src/agents/reviser/reviser.py`
  - 读取 `audit/audit_result.json`，收集所有 `passed=false` 的条目
  - 按各条目的 `route_on_fail` 字段，取最上游阶段作为 `route_to`
  - 生成 `revision_instructions`（对下游 Agent 的修改要求文本）
  - **写入 LessonMemory**：将每个失败条目（含违规内容片段）写入 `campaigns/{product}/memory/lessons_{platform}.json`
  - 检查 `retry_count`（读取当日 pipeline state）：
    - `< MAX_RETRIES`（默认 2）→ 写入 `audit/revision_plan.json`
    - `≥ MAX_RETRIES` → 写入 `audit/human_review_required.json`，停止自动重跑

- [ ] **#9e** `src/orchestrator/lesson_memory.py` — LessonMemory 模块
  - `LessonMemory.load(platform)` → 读取当前平台所有 lessons
  - `LessonMemory.inject_prompt(agent, platform)` → 生成注入段落（Markdown）
  - `LessonMemory.write_lesson(platform, lesson)` → 追加/更新单条 lesson（去重）
  - Planner / Scriptwriter / Creator 启动时调用 `inject_prompt()` 注入历史经验
  - 返回 `route_to` 供 Pipeline 决定续跑起点

- [ ] **#10a** `src/orchestrator/pipeline.py` — 新增 Audit 失败回路
  - Audit 失败后调用 ReviserAgent
  - 若 `revision_plan.json` 存在 → 从 `route_to` 阶段重跑（携带 `revision_instructions`）
  - 若 `human_review_required.json` 存在 → 终止，输出提示
  - 各阶段 Agent 接受可选的 `revision_instructions` 注入（追加到 user prompt）

---

## 阶段八：Orchestrator 主流程（已完成基础，待补充回路）

- [x] **#10** `src/orchestrator/pipeline.py` — 基础版本已完成
  - 串联：Planner → Scriptwriter → Director → Creator → Audit
  - 支持断点续跑（`.pipeline_state.json`）
  - 支持 `--from-step` / `--to-step` 精确控制范围
- [ ] **#10a** 见上：补充 Audit 失败回路 + ReviserAgent 集成

- [x] **#11** `main.py`（CLI 入口）— 已完成
  - `python main.py --product "MyApp" --prd docs/prd.md`
  - 支持 `--from-step` / `--to-step` / `--dry-run`

---

## 阶段九：测试

- [ ] **#12** `tests/agents/` — 各 Agent 单元测试（mock LLM 调用，验证文件输出）
- [ ] **#13** `tests/orchestrator/test_pipeline.py` — Pipeline 集成测试（端到端冒烟）
- [ ] **#14** 完整链路手动验证：输入真实 PRD，观察每个阶段的输出文件

---

## 执行顺序（更新）

```
#8a (llm_config.json)
    ↓
#9a (audit_checklist.json)
    ↓
#9b (GeminiClient.chat_structured)
    ↓
#9c (AuditAgent v2)
    ↓
#9e (LessonMemory 模块) → #9d (ReviserAgent，含 LessonMemory 写入)
    ↓
#10a (Pipeline 回路，含 LessonMemory 注入到各 Agent)
    ↓
#12 → #13 → #14
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
| 8a | llm_config.json（模型统一配置） | ⬜ 待开始 |
| 9 | Audit v1（旧版） | ✅ 已跑通，待重设计 |
| 9a | audit_checklist.json | ⬜ 待开始 |
| 9b | GeminiClient.chat_structured | ⬜ 待开始 |
| 9c | AuditAgent v2（共享清单+投票） | ⬜ 待开始 |
| 9d | ReviserAgent（含 LessonMemory 写入） | ⬜ 待开始 |
| 9e | LessonMemory 模块 | ⬜ 待开始 |
| 10 | Pipeline 基础版 | ✅ 完成（含 --from-step/--to-step） |
| 10a | Pipeline Audit 失败回路 + LessonMemory 注入 | ⬜ 待开始 |
| 11 | main.py CLI 入口 | ✅ 完成 |
| 12 | Agent 单元测试 | ⬜ 待开始 |
| 13 | Pipeline 集成测试 | ⬜ 待开始 |
| 14 | 完整链路手动验证 | ⬜ 待开始 |
