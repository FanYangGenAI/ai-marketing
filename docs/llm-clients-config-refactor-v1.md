# LLM 客户端与温度策略重构方案（v1）

## 1. 背景与目标

当前 `pipeline._init_agents` 使用三个全局式客户端（历史上命名为 `_openai` / `_gemini` / `_claude`，且 `_claude` 实为 Gemini），与 `llm_config.json` 中**按角色拆分**的键不完全一致；Strategist 未使用 `strategy_*` 键；Moderator 在部分 Agent 中与某一辩手共用同一 client，与配置语义不符。

**本方案目标：**

1. **只从 `llm_config.json` 按角色构建 client**，不再在 Pipeline 层维护「三个共享全局变量」作为所有阶段复用的唯一来源。
2. **Moderator** 使用独立配置项（默认与产品约定一致的可配置模型），与辩手 A/B/C 解耦。
3. **温度策略**：策略/规划为 0；Scriptwriter / Director / Creator 偏高以保创造力；Audit 为 0；**Reviser 为偏低温度（0～0.3）**。
4. 保留单一工厂函数（或等价模块），根据 `model` 字符串选择 `OpenAIClient` 或 `GeminiClient`，避免散落判断逻辑。

## 2. 配置约定（`src/config/llm_config.json`）

### 2.1 已有键（保持并补全语义）

继续使用并**显式消费**下列键（名称可与现状一致，缺省时在代码中给合理默认）：

| 键 | 用途 |
|----|------|
| `strategy_analyst` | Strategist 辩手 DataAnalyst |
| `strategy_reviewer` | Strategist 辩手 StrategyReviewer |
| `strategy_moderator` | Strategist Moderator（或合并见下） |
| `planner_a` / `planner_b` / `planner_c` | Planner 三辩手 |
| `planner_moderator` | Planner Moderator |
| `scriptwriter_a` / `scriptwriter_b` / `scriptwriter_c` | Scriptwriter 三辩手 |
| `scriptwriter_moderator` | Scriptwriter Moderator |
| `director` | Director |
| `creator` | Creator |
| `auditor` | Audit |
| `reviser` | Reviser |

### 2.2 Moderator 统一模型（可选简化）

若希望「所有 Debate 的 Moderator 同一模型」：

- 可增加顶层键 **`moderator`**；解析时优先 `moderator`，否则回退到各阶段的 `*_moderator`。

若希望「分阶段可不同」：

- 不增加 `moderator`，**仅**使用 `strategy_moderator` / `planner_moderator` / `scriptwriter_moderator` 三个键，由配置填成同一模型名即可。

**文档约定：** 以 Google / OpenAI 实际可用模型名为准；例如产品侧要求 Moderator 使用 `gemini-3.1-flash-preview` 时，在对应 `*_moderator` 或 `moderator` 中配置。

## 3. Client 构建方式（无全局三变量）

### 3.1 工厂函数

新增（或等价放置于 `src/llm/` 下）例如：

- `build_llm_client(model_name: str) -> BaseLLMClient`

规则示例（实现时以代码为准）：

- 模型名属于 OpenAI 系列（如 `gpt-*`、`o1`、`o3` 等）→ `OpenAIClient(model=...)`
- 其余 → `GeminiClient(model=...)`

### 3.2 Pipeline `_init_agents`

- **不再**定义 `self.agent_a` / `self.agent_b` / `self.agent_c` 作为全项目唯一 trio。
- 对每个 **Agent 类** 传入其 **所需的一组 client**，每组均由 `cfg["<role_key>"]` 经 `build_llm_client` 得到，例如：
  - `StrategistAgent(build(cfg["strategy_analyst"]), build(cfg["strategy_reviewer"]), build(moderator_key_for_strategy), ...)`
  - `PlannerAgent(build(planner_a), build(planner_b), build(planner_c), build(moderator_key_for_planner), ...)`
  - 其余类推。
- **Director / Creator / Audit / Reviser** 各 **一个** `build(cfg["director"])` 等即可。
- **可选优化**：同一 `(model_name)` 可 **缓存** `build` 结果，避免同一模型重复建多个实例；这是实现细节，不改变「按角色从 config 读」的语义。

### 3.3 Agent 内部

- Strategist / Planner / Scriptwriter：`debate_and_synthesize(..., moderator_client=<独立 client>)`，**禁止**再用某一辩手 client 兼作 Moderator。
- 更新 docstring 与参数名，去掉误导性的「Claude」命名（若仍用 `BaseAgent.llm_client`，可指向 Moderator client 或明确约定仅用于日志）。

## 4. 温度策略

| 环节 | 温度 | 说明 |
|------|------|------|
| Strategist、Planner（debate 全链路） | `0.0` | 策略与规划偏稳定、可复现 |
| Scriptwriter（debate 全链路） | `0.7`（或配置项，可略高） | 充分创造力 |
| Director | `0.7`（或配置项） | 与创意一致 |
| Creator | `0.7`（或配置项） | 与创意一致 |
| Audit（文本 + 视觉结构化） | `0.0` | 审计严格 |
| **Reviser** | **`0.0`～`0.3`** | 路由与修订指令稳定、少漂移 |

**实现要点：**

- `src/orchestrator/debate.py`：`debate_and_synthesize` 及内部 `_agent_speak_*`、`_moderator_*` 需将 `temperature` 透传至 `client.chat(...)`。
- 各 Agent 的 `run()` 调用 debate 时传入对应温度；Director / Creator / Audit / Reviser 在各自文件中显式常量或 `llm_config` 可选键（若未来要「温度也可配置」）。

**已知约束：**

- **OpenAI 部分新模型**（如 `gpt-5-nano`）在现有 `OpenAIClient` 中可能 **无法传入非默认 temperature**；若该角色需严格 0 或 0.7，需在文档中标注例外，或换用支持自定义温度的模型。

## 5. 影响范围（文件级）

- `src/orchestrator/pipeline.py`：`_init_agents` 重写为按角色 `build` + 传入各 Agent。
- `src/config/llm_config.json`：补全/统一 `moderator` 或各 `*_moderator`；按需增加可选 `temperature_*`（若二期再做「温度可配置」）。
- `src/orchestrator/debate.py`：temperature 透传。
- `src/agents/strategist/strategist.py`、`planner/planner.py`、`scriptwriter/scriptwriter.py`：构造函数与 `run()` 签名、Moderator 独立 client、温度参数。
- `src/agents/director/director.py`、`creator/creator.py`**：** 创意温度。
- `src/agents/audit/audit.py`：** 0.0。
- `src/agents/reviser/reviser.py`：** 0～0.3。
- `src/llm/`：** 新增 `client_factory.py`（或等价命名）。
- `tests/`：** 所有构造上述 Agent 的用例同步更新。

## 6. 实施顺序建议

1. 实现 `build_llm_client` + 可选实例缓存。
2. 修正 debate 层 temperature 透传；Audit / Reviser 温度。
3. 拆分 Moderator client；改 Strategist / Planner / Scriptwriter 构造与调用。
4. 重写 `pipeline._init_agents` 为「按角色建 client」。
5. 全量测试与回归（含 Pipeline 集成路径）。

## 7. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-03-24 | 初版：按角色建 client、无三全局变量；Reviser 0～0.3；温度与文件清单 |
