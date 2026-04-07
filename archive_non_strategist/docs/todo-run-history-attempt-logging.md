# TODO List — 审核重试全链路可追溯（attempt 化）

> 方案文档：`docs/run-history-attempt-logging-v1.md`  
> 创建日期：2026-03-23  
> 目标：同一天多次重试不覆盖日志，前端可查看完整执行链路与中间数据

---

## 阶段 0：设计定稿

- [ ] 定稿 attempt 编号规则：`attempt_00` 起始，重试递增
- [ ] 定稿 `.run_history.json` schema（attempt / steps / reviser / failed_items）
- [ ] 定稿 latest 与 attempts 双写策略（兼容旧读取）

---

## 阶段 1：Pipeline 轨迹索引

- [ ] `src/orchestrator/pipeline.py` 新增 `.run_history.json` 读写
- [ ] 每次 attempt 记录开始/结束时间、步骤结果、audit/reviser信息
- [ ] 重试时记录 `route_to` 与 `revision_instructions`

---

## 阶段 2：Agent 产物 attempt 化（不覆盖）

- [ ] Planner：`plan/attempts/{attempt_id}/daily_marketing_plan.md` + `debate_raw.md`
- [ ] Scriptwriter：`script/attempts/{attempt_id}/daily_marketing_script.md` + `debate_raw.md`
- [ ] Director：`director/attempts/{attempt_id}/director_task_result.json` + `director_raw.md`
- [ ] Creator：`creator/attempts/{attempt_id}/post_package.json` + `post_content.md` + `creator_raw.md` + `copy_validation.json`
- [ ] Audit：`audit/attempts/{attempt_id}/audit_result.json` + `audit_raw.md`
- [ ] Reviser：`audit/attempts/{attempt_id}/revision_plan.json` / `human_review_required.json`

---

## 阶段 3：前端可见性（AuditReport）

- [ ] 读取 `.run_history.json`
- [ ] 展示 attempt 时间线与 route_to
- [ ] 展示每次 attempt 的步骤 summary 与失败条目
- [ ] 前端文案明确“历史保留，不覆盖”

---

## 阶段 4：测试与验证

- [ ] 单测：run_history 追加与 schema 稳定
- [ ] 集成：模拟 audit 失败 + 重试，验证 attempt 目录数量递增
- [ ] 前端构建与基本交互验证

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-03-23 | 初版实现清单 |
