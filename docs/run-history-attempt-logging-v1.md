# 审核重试全链路可追溯方案 — 初稿 v1

> 状态：开发中  
> 日期：2026-03-23  
> 目标：重试链路全量留痕，前端可回放每次 attempt 的思考过程与中间数据（不覆盖、不删除）

---

## 1. 问题定义

当前 `daily/{date}` 下多数阶段产物使用固定文件名（如 `debate_raw.md`、`audit_result.json`），重试时会覆盖前一次内容，导致：

- 无法还原「Audit 失败 → Reviser 路由 → 从 route_to 重跑」的完整执行过程；
- 前端仅能看到最终态，无法按 attempt 查看每次中间数据；
- 同一天多次 route 到同一阶段（如 Planner）时，历史日志丢失。

---

## 2. 目标与原则

1. **每次 attempt 独立落盘**：`attempt_00`、`attempt_01`...
2. **保留 latest 兼容路径**：不破坏现有读取逻辑（`daily_marketing_script.md` 等）
3. **统一运行轨迹索引**：新增 `.run_history.json` 作为前端追溯主数据源
4. **前端可视化回放**：展示每次 attempt 的阶段执行、失败条目、route_to、修订指令
5. **禁止覆盖历史**：新数据只 append，不删除既有 attempt 目录

---

## 3. 落盘结构（新增）

在 `campaigns/{product}/daily/{date}/` 下新增：

- `.run_history.json`
- `plan/attempts/{attempt_id}/...`
- `script/attempts/{attempt_id}/...`
- `director/attempts/{attempt_id}/...`
- `creator/attempts/{attempt_id}/...`
- `audit/attempts/{attempt_id}/...`
- `strategy/attempts/{attempt_id}/...`（可选但建议统一）

其中 `attempt_id` 格式：`attempt_00`, `attempt_01`, `attempt_02`。

---

## 4. Pipeline 行为改造

### 4.1 attempt 生命周期

- 初次执行：`attempt_00`
- 每次 Reviser 返回有效 `route_to` 后：attempt 递增
- `MAX_RETRIES` 超限后写人工介入并结束

### 4.2 run history 记录字段（建议）

每个 attempt 至少记录：

- `attempt_id`
- `retry_count`
- `started_at` / `ended_at`
- `steps[]`：每阶段 `step`、`success`、`summary`、`output_path`、`artifacts[]`
- `audit_passed`
- `failed_items[]`
- `reviser`：`route_to`、`revision_instructions`

---

## 5. Agent 改造策略

各阶段同时输出两类产物：

1. **latest 路径**（兼容）
2. **attempt 路径**（归档）

优先覆盖：Planner / Scriptwriter / Director / Creator / Audit / Reviser。  
Director 的图片中间文件写入 `assets/attempts/{attempt_id}/` 避免互相覆盖。

---

## 6. 前端展示改造（AuditReport）

在现有审核页增加“执行历史（attempt）”区块：

- 按 attempt 显示：开始/结束时间、是否通过、route_to
- 展示该 attempt 的阶段列表与 summary
- 展示失败条目与 revision 指令
- 可跳转查看该 attempt 的关键文件路径（后续可增强为内嵌预览）

---

## 7. 验收标准（DoD）

1. 同一天同一阶段多次执行，历史 attempt 文件均保留。
2. 前端可看到每次 `Audit -> Reviser -> route_to` 的完整链路。
3. `.run_history.json` 可完整重建执行时间线。
4. 不影响现有 latest 路径消费逻辑。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-03-23 | 初稿：attempt 化落盘 + 运行轨迹索引 + 前端回放 |
