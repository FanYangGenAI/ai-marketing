# TODO：LLM 客户端按角色配置与温度重构

配套方案：`docs/llm-clients-config-refactor-v1.md`

## Phase 1 — 基础设施

- [ ] 新增 `build_llm_client(model_name: str) -> BaseLLMClient`（OpenAI vs Gemini 规则清晰，单测覆盖）
- [ ] （可选）同一 `model_name` 短生命周期内复用同一实例，避免重复构造
- [ ] 在 `llm_config.json` 中确认/补全：`strategy_*`、`planner_*`、`scriptwriter_*`、`director`、`creator`、`auditor`、`reviser`、以及各 `*_moderator` 或顶层 `moderator`
- [ ] 文档中注明：Moderator 目标模型与厂商可用名一致（如 `gemini-3.1-flash-preview`）

## Phase 2 — Debate 与温度透传

- [ ] `debate.py`：`debate_and_synthesize` 与内部函数支持 `temperature`（可分辩手轮与 moderator 两档，或统一一档按阶段传入）
- [ ] Strategist / Planner：`run()` 调用 debate 时 **temperature = 0.0**
- [ ] Scriptwriter：`run()` 调用 debate 时 **temperature = 0.7**（或常量 + 注释可调）

## Phase 3 — Moderator 独立 client

- [ ] Strategist / Planner / Scriptwriter：构造函数改为接收 **三个辩手 client + 独立 moderator_client**，`debate_and_synthesize(..., moderator_client=moderator_client)`
- [ ] 删除「用某一辩手兼作 Moderator」的路径；更新类 docstring

## Phase 4 — Pipeline 组装

- [ ] 重写 `pipeline._init_agents`：**仅**通过 `cfg` 各键 `build` 出 client，按各 Agent 构造参数传入；**不保留**三个全局共享 client 作为唯一来源
- [ ] Director / Creator / Audit / Reviser：各 `build(cfg["..."])`；必要时 auditor 与 reviser 共用同一模型时可复用同一 build 结果（缓存）

## Phase 5 — 各 Agent 文件温度

- [ ] Director：**0.7**（或与 Scriptwriter 共用命名常量）
- [ ] Creator：**0.7**
- [ ] Audit：文本 `chat_structured`、视觉 `chat_structured_with_images` 均 **0.0**
- [ ] Reviser：**0.0～0.3**（建议默认 **0.2** 或 **0.3**，与方案一致）

## Phase 6 — 约束与文档

- [ ] 在方案或 README 中注明：OpenAI 新推理模型可能无法自定义 temperature 的例外
- [ ] 若存在 `CLAUDEClient` 误用名：清理或注明与 Gemini 并行策略

## Phase 7 — 测试与验证

- [ ] 更新所有实例化 Strategist / Planner / Scriptwriter 的单元测试
- [ ] 运行 `pytest` 相关 orchestrator / agents 测试
- [ ] 手动跑一次 `main.py` 或 API 触发 Pipeline，确认无重复 client 导致的认证错误

## 审查（完成后填写）

| 项目 | 结果 |
|------|------|
| 完成日期 | |
| 主要提交 / 分支 | |
| 备注 | |
