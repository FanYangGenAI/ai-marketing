# TODO List — 展示层（Frontend + FastAPI）

> 分支：`develop/develop-agents`（当前）→ 后续可拆独立分支
> 创建日期：2026-03-22
> 目标：提供本地 Web 界面，支持完整用户交互闭环：
>       创建项目 → 触发流水线（异步）→ 审阅物料 → 接受/拒绝反馈 → LessonMemory 更新
> 技术栈：FastAPI（Python）+ Vite + Vue 3 + Tailwind CSS
> 详细设计：`docs/system-design-draft.md` § 11

---

## 后端（FastAPI）

### #1 基础只读路由 `server/main.py` + `server/routers/campaigns.py`

- [ ] `server/` 目录结构 + `requirements.txt`（fastapi、uvicorn、python-multipart）
- [ ] `server/main.py`：FastAPI 入口，CORS 配置（允许 localhost:5173），生产模式 serve `frontend/dist/`
- [ ] `server/routers/campaigns.py`，实现只读路由：

| 路由 | 说明 |
|------|------|
| `GET /api/products` | 扫描 `campaigns/` 返回产品列表 |
| `GET /api/products/{product}/dates` | 返回日期列表 + 每日 pipeline 状态 + feedback 状态 |
| `GET /api/products/{product}/{date}/state` | 读取 `.pipeline_state.json` |
| `GET /api/products/{product}/{date}/package` | 读取 `creator/post_package.json` |
| `GET /api/products/{product}/{date}/audit` | 读取 `audit/audit_result.json` |
| `GET /api/products/{product}/{date}/file?path=` | 任意文本文件（路径限 `campaigns/` 内） |
| `GET /api/products/{product}/assets` | 读取 `asset_library/index.json` |
| `GET /api/products/{product}/memory/{platform}` | 读取 `memory/lessons_{platform}.json` |
| `GET /api/products/{product}/run/status` | 返回当前/最近 Pipeline 运行状态（供轮询） |

### #2 图片服务 `server/routers/images.py`

- [ ] `GET /api/images?path=` → 读取图片二进制，返回正确 Content-Type
- [ ] 路径安全校验：只允许 `campaigns/` 目录内，禁止 `..` 目录遍历

### #3 写操作路由（交互功能）

- [ ] `POST /api/products` — 创建新产品项目
  - body: `{"name": "原语", "user_brief": "这是一款..."}`
  - 创建 `campaigns/{name}/config/product_config.json`
  - 创建必要子目录（config/, docs/, strategy/, memory/）

- [ ] `POST /api/products/{product}/config` — 更新产品配置
  - 支持更新 `user_brief`、`suppress_version_in_copy` 等字段

- [ ] `POST /api/products/{product}/prd` — 上传 PRD 文件
  - multipart/form-data，写入 `campaigns/{product}/docs/`
  - 更新 `product_config.json` 中的 `prd_path`

- [ ] `POST /api/products/{product}/run` — 异步触发 Pipeline
  - body: `{"today_note": "..."}`（可选）
  - 后台启动 `python main.py --product {product}`
  - 写入 `today_note` 到当日 context
  - 立即返回 `{"status": "started"}`
  - 防重入：运行中时拒绝再次触发

- [ ] `POST /api/products/{product}/{date}/feedback` — 提交接受/拒绝反馈
  - body: `{"action": "accept"}` 或 `{"action": "reject", "reason": "..."}`
  - 写入 `campaigns/{product}/daily/{date}/feedback.json`
  - 同步调用 `LessonMemory.write_acceptance()` 或 `LessonMemory.write_rejection()`

---

## 前端（Vite + Vue 3）

### #4 项目脚手架 + 全局结构（已完成，标记进度）

- [x] `frontend/` 初始化（Vite + Vue 3 + Tailwind CSS）
- [x] `src/api/index.js`：封装所有 fetch 调用
- [ ] 新增 API 调用封装：`createProduct`, `updateConfig`, `uploadPrd`, `triggerRun`, `getRunStatus`, `submitFeedback`

**Sidebar（`components/Sidebar.vue`，已有基础，待扩展）：**
- [x] 产品列表 + 日期列表（含状态图标）
- [ ] 每个日期显示反馈状态（✅已接受 / ❌已拒绝 / ⬜未处理）
- [ ] 顶部「+ 新建项目」按钮（触发 CreateProjectModal）
- [ ] 产品旁「▶ 运行」按钮（触发 RunPanel 或直接触发）

### #5 Overview + PostDetail（核心视图，已有基础，待扩展）

**Overview（`views/Overview.vue`，已有基础）：**
- [x] Pipeline 各阶段状态列表
- [x] 帖子摘要卡片
- [ ] 新增「接受/拒绝」操作区
  - [✅ 接受并准备发布] 按钮
  - [❌ 拒绝] + 拒绝原因文本框 + [提交] 按钮
  - 已提交后显示已锁定状态（不可重复提交）
- [ ] 新增「▶ 触发今日流水线」入口（如当日无数据时）

**PostDetail（`views/PostDetail.vue`，已有基础）：**
- [x] 小红书风格帖子卡片 + 图片轮播
- [x] 图片下载、文案复制
- [ ] 同样集成接受/拒绝操作区（与 Overview 共用组件）

### #6 AuditReport + PipelineLog（已完成）

- [x] **AuditReport**（`views/AuditReport.vue`）：总体结论 + 条目明细 + 三票展开 + 滚动条
- [x] **PipelineLog**（`views/PipelineLog.vue`）：折叠阶段列表 + 文件预览（markdown/json）+ 滚动条

### #7 新增交互组件

**CreateProjectModal（`components/CreateProjectModal.vue`）：**
- [ ] 产品名称输入框
- [ ] user_brief 多行文本框（永久产品需求描述）
- [ ] PRD 文件上传（可选）
- [ ] 提交 → 调用 `POST /api/products`，成功后刷新侧边栏

**RunPanel（`components/RunPanel.vue`，内嵌在 Overview 或浮层）：**
- [ ] today_note 文本框（可选，本次运行特殊要求）
- [ ] [🚀 开始运行流水线] 按钮
- [ ] 运行中状态：按钮 disabled + 显示「流水线运行中...」

**PipelineStatusPanel（`components/PipelineStatusPanel.vue`）：**
- [ ] 右下角悬浮面板（fixed 定位，z-50）
- [ ] 可折叠（collapsed 时显示小图标 + 当前阶段名）
- [ ] 展开时显示各阶段状态（⏳/🔄/✅/❌）+ 时间戳
- [ ] 轮询 `GET /api/products/{product}/run/status`（每 3 秒，仅运行时）
- [ ] 流水线完成后自动折叠 + 刷新侧边栏数据

**FeedbackPanel（`components/FeedbackPanel.vue`）：**
- [ ] 显示当前 feedback 状态（未处理 / 已接受 / 已拒绝）
- [ ] 未处理时显示操作按钮
- [ ] 接受：调用 `POST /feedback {"action": "accept"}`
- [ ] 拒绝：文本框输入原因 → 调用 `POST /feedback {"action": "reject", "reason": "..."}`
- [ ] 已处理后显示锁定提示

### #8 AssetLibrary + LessonMemory

**AssetLibrary（`views/AssetLibrary.vue`）：**
- [ ] 图片网格（4 列，`/api/images?path=` 作为 `<img src>`）
- [ ] 筛选条：source（全部 / generate / screenshot）+ 日期范围
- [ ] 点击图片 → 展开详情（prompt / asset_id / 使用日期 / used_in）+ [下载] 按钮

**LessonMemory（`views/LessonMemory.vue`）：**
- [ ] 平台选择器（当前只有 xiaohongshu）
- [ ] 分类展示：负向经验（audit 失败 + 用户拒绝）/ 正向经验（用户接受）
- [ ] 展开每条 → 完整规则文本 + 来源信息

---

## 执行顺序

```
#1 (FastAPI 只读路由 + #3 写操作路由)
    ↓
#2 (图片文件服务)
    ↓
#4 (Sidebar 扩展：新建项目按钮、反馈状态)
    ↓
#7 (CreateProjectModal + RunPanel + PipelineStatusPanel)   ← Pipeline 触发闭环
    ↓
#5 扩展 (Overview/PostDetail 加接受/拒绝)                   ← 用户反馈闭环
    ↓
#7 (FeedbackPanel)
    ↓
#8 (AssetLibrary + LessonMemory)                           ← 辅助视图
```

**#1 + #2 + #4 + #7 中 PipelineStatusPanel 完成后**即可触发流水线并观察进度，是最小可运行版本。
**再加 #5 扩展 + FeedbackPanel**，完整交互闭环跑通。

---

## 进度总览

| # | 任务 | 状态 |
|---|------|------|
| 1 | FastAPI 只读路由（9 个接口） | ⬜ 待开始 |
| 2 | 图片文件服务（路径安全） | ⬜ 待开始 |
| 3 | 写操作路由（创建项目、触发运行、提交反馈） | ⬜ 待开始 |
| 4 | Sidebar 扩展（新建项目按钮、反馈状态图标） | ⬜ 待开始 |
| 5 | Overview + PostDetail（接受/拒绝操作区） | ⬜ 待开始 |
| 6 | AuditReport + PipelineLog（含滚动条） | ✅ 完成 |
| 7a | CreateProjectModal | ⬜ 待开始 |
| 7b | RunPanel（today_note + 触发按钮） | ⬜ 待开始 |
| 7c | PipelineStatusPanel（右下角实时状态） | ⬜ 待开始 |
| 7d | FeedbackPanel（接受/拒绝组件） | ⬜ 待开始 |
| 8 | AssetLibrary + LessonMemory | ⬜ 待开始 |

---

## 本地启动

```bash
# 后端（端口 8000）
cd server
pip install -r requirements.txt
uvicorn main:app --reload

# 前端（端口 5173）
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 即可使用。
