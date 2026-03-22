# TODO List — 展示层（Frontend + FastAPI）

> 分支：`develop/develop-agents`（当前）→ 后续可拆独立分支
> 创建日期：2026-03-22
> 目标：提供本地 Web 界面，浏览、审阅所有 Pipeline 输出，支持下载图片和复制文案
> 技术栈：FastAPI（Python）+ Vite + Vue 3 + Tailwind CSS
> 详细设计：`docs/system-design-draft.md` § 11
> 阶段定性：**只读**，不触发任何 Pipeline 操作

---

## 后端（FastAPI）

### #1 基础路由 `server/main.py` + `server/routers/campaigns.py`

- [ ] `server/` 目录结构 + `requirements.txt`（fastapi、uvicorn、python-multipart）
- [ ] `server/main.py`：FastAPI 入口，CORS 配置（允许 localhost:5173），生产模式 serve `frontend/dist/`
- [ ] `server/routers/campaigns.py`，实现所有只读路由：

| 路由 | 说明 |
|------|------|
| `GET /api/products` | 扫描 `campaigns/` 返回产品列表 |
| `GET /api/products/{product}/dates` | 返回日期列表 + 每日 pipeline 状态摘要 |
| `GET /api/products/{product}/{date}/state` | 读取 `.pipeline_state.json` |
| `GET /api/products/{product}/{date}/package` | 读取 `creator/post_package.json` |
| `GET /api/products/{product}/{date}/audit` | 读取 `audit/audit_result.json` |
| `GET /api/products/{product}/{date}/file?path=` | 任意文本文件（路径限 `campaigns/` 内） |
| `GET /api/products/{product}/assets` | 读取 `asset_library/index.json` |
| `GET /api/products/{product}/memory/{platform}` | 读取 `memory/lessons_{platform}.json` |

### #2 图片服务 `server/routers/images.py`

- [ ] `GET /api/images?path=` → 读取图片二进制，返回正确 Content-Type
- [ ] 路径安全校验：只允许 `campaigns/` 目录内，禁止 `..` 目录遍历

---

## 前端（Vite + Vue 3）

### #3 项目脚手架 + 全局结构

- [ ] `frontend/` 初始化（`npm create vite@latest`，选 Vue + JS）
- [ ] 安装依赖：`tailwindcss`、`vue-router`、`marked`、`highlight.js`
- [ ] `vite.config.js`：`/api` 代理到 `http://localhost:8000`
- [ ] `App.vue`：两栏布局（左侧 Sidebar + 右侧主内容区）
- [ ] `src/api/index.js`：封装所有 fetch 调用

**Sidebar（`components/Sidebar.vue`）：**
- [ ] 产品列表（从 `/api/products` 加载）
- [ ] 每个产品展开日期列表（从 `/api/products/{product}/dates` 加载），含状态图标（✅/❌）
- [ ] 底部固定入口：素材库、经验记忆
- [ ] 点击日期 → 切换到 Overview 视图

### #4 Overview + PostDetail（核心视图）

**Overview（`views/Overview.vue`）：**
- [ ] Pipeline 各阶段状态列表（图标 + 摘要一行）
- [ ] 帖子摘要卡片：封面缩略图 + 标题 + 正文前 80 字 + hashtags
- [ ] 底部快捷跳转按钮：[帖子预览] [审核报告] [流水线日志]

**PostDetail（`views/PostDetail.vue`）：**
- [ ] 小红书风格帖子卡片（CSS 模拟，移动端比例，圆角卡片 + 轻阴影）
  - [ ] `components/ImageCarousel.vue`：图片轮播（←/→ 切换，指示点）
  - [ ] 点击图片 → 全屏 lightbox 预览
- [ ] 右侧图片列表：序号 + caption + [下载] 按钮
  - [下载] → `<a :href="/api/images?path=..." download>` 触发浏览器下载
- [ ] 操作区：
  - [复制标题] → `navigator.clipboard.writeText(title)`
  - [复制正文] → `navigator.clipboard.writeText(body)`
  - [复制话题标签] → `navigator.clipboard.writeText(hashtags.join(' '))`
  - 复制后显示 "已复制" 短暂提示（1.5s 后消失）

### #5 AuditReport + PipelineLog

**AuditReport（`views/AuditReport.vue`）：**
- [ ] 总体结论横幅（✅通过 / ❌未通过 + 重试次数）
- [ ] 条目明细表格（12 行）：id / 类别 / 投票（X通/Y失）/ 结论 / 代表理由
- [ ] 展开每条目 → 显示 Auditor A/B/C 三票的具体理由

**PipelineLog（`views/PipelineLog.vue`）：**
- [ ] 各阶段折叠列表（默认全收起），显示完成时间 + 状态
- [ ] 每个阶段列出可查看文件（`.md` / `.json`）
- [ ] 点击文件 → 右侧预览面板（或 modal）：
  - Markdown 文件：marked.js 渲染为 HTML
  - JSON 文件：highlight.js 语法高亮

### #6 AssetLibrary + LessonMemory

**AssetLibrary（`views/AssetLibrary.vue`）：**
- [ ] 图片网格（4 列，`/api/images?path=` 作为 `<img src>`）
- [ ] 筛选条：source（全部 / generate / screenshot）+ 日期范围
- [ ] 点击图片 → 展开详情（prompt / asset_id / 使用日期 / used_in）+ [下载] 按钮

**LessonMemory（`views/LessonMemory.vue`）：**
- [ ] 平台选择器（当前只有 xiaohongshu）
- [ ] 经验列表：条目 id / 类别 / 违规次数 / 规则摘要
- [ ] 展开每条 → 完整规则文本 + 反例内容

---

## 执行顺序

```
#1 (FastAPI 基础路由)
    ↓
#2 (图片文件服务)
    ↓
#3 (Vue 脚手架 + Sidebar)
    ↓
#4 (Overview + PostDetail)     ← 完成后已有完整主干功能
    ↓
#5 (AuditReport + PipelineLog)
    ↓
#6 (AssetLibrary + LessonMemory)
```

**#1-#4 完成后**即可浏览帖子、下载图片、复制文案，是最小可用版本。

---

## 进度总览

| # | 任务 | 状态 |
|---|------|------|
| 1 | FastAPI 基础路由（8 个接口） | ⬜ 待开始 |
| 2 | 图片文件服务（路径安全） | ⬜ 待开始 |
| 3 | Vue 脚手架 + Sidebar 导航 | ⬜ 待开始 |
| 4 | Overview + PostDetail（含下载/复制） | ⬜ 待开始 |
| 5 | AuditReport + PipelineLog | ⬜ 待开始 |
| 6 | AssetLibrary + LessonMemory | ⬜ 待开始 |

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
