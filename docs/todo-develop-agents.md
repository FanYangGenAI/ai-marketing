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

## 阶段七：Audit（合规与质量审核）

- [ ] **#9** `src/agents/audit/audit.py`
  - PlatformAuditor (GPT-4o)：检查平台规则（禁用词、字数、图片规格）
  - ContentAuditor (Claude)：事实一致性、品牌调性
  - SafetyAuditor (Claude)：隐私、版权、安全风险
  - 输出：`{daily_folder}/output/audit_result.json`
  - 通过 → 拷贝到 `{daily_folder}/output/final/`；不通过 → 列出修改意见

---

## 阶段八：Orchestrator 主流程

- [ ] **#10** `src/orchestrator/pipeline.py`
  - 串联：Strategist（按需）→ Planner → PlatformAdapter → Scriptwriter → Director → Creator → Audit
  - 管理 `{daily_folder}` 的创建（`campaigns/{product}/daily/{YYYY-MM-DD}/`）
  - 异常处理：任一阶段失败时保存断点，支持从断点重启

- [ ] **#11** `main.py`（CLI 入口）
  - `python main.py --product "MyApp" --date 2026-03-17 --prd docs/prd.md`
  - 支持 `--from-step planner` 跳过已完成阶段
  - 支持 `--dry-run` 只打印执行计划不实际运行

---

## 阶段九：测试

- [ ] **#12** `tests/agents/` — 各 Agent 单元测试（mock LLM 调用，验证文件输出）
- [ ] **#13** `tests/orchestrator/test_pipeline.py` — Pipeline 集成测试（端到端冒烟）
- [ ] **#14** 完整链路手动验证：输入真实 PRD，观察每个阶段的输出文件

---

## 执行顺序

```
#1 (BaseAgent)
    ↓
#4 (CampaignMemory) + #5 (PlatformAdapter)  ← 工具类，先做，后续 Agent 依赖
    ↓
#2 (Strategist) → #3 (Planner) → #6 (Scriptwriter) → #7 (Director) → #8 (Creator) → #9 (Audit)
    ↓
#10 (Pipeline) → #11 (main.py)
    ↓
#12 → #13 → #14
```

---

## 进度总览

| # | 任务 | 状态 |
|---|------|------|
| 1 | BaseAgent 基类 | ⬜ 待开始 |
| 2 | Strategist | ⬜ 待开始 |
| 3 | Planner | ⬜ 待开始 |
| 4 | CampaignMemory | ⬜ 待开始 |
| 5 | PlatformAdapter | ⬜ 待开始 |
| 6 | Scriptwriter | ⬜ 待开始 |
| 7 | Director | ⬜ 待开始 |
| 8 | Creator | ⬜ 待开始 |
| 9 | Audit | ⬜ 待开始 |
| 10 | Pipeline 主流程 | ⬜ 待开始 |
| 11 | main.py CLI 入口 | ⬜ 待开始 |
| 12 | Agent 单元测试 | ⬜ 待开始 |
| 13 | Pipeline 集成测试 | ⬜ 待开始 |
| 14 | 完整链路手动验证 | ⬜ 待开始 |
