# TODO List — develop/develop-skills

> 分支：`develop/develop-skills`
> 创建日期：2026-03-17
> 目标：完成 Skill 体系、LLM 客户端封装、Asset Library 及基础编排机制

---

## 阶段一：项目基础

- [ ] **#1** 搭建项目目录结构（`src/skills`, `src/llm`, `src/agents`, `src/orchestrator`, `src/config`）
- [ ] **#2** 完善 `requirements.txt`、`.gitignore`、`.env.example`

---

## 阶段二：LLM 统一封装

- [ ] **#3** 实现 LLM 统一抽象层：Claude / OpenAI / Gemini 三个客户端封装（`src/llm/`）

---

## 阶段三：Skill 体系（本分支核心）

- [ ] **#4** 实现 Skill：`web_search`（基于 Claude built-in web_search tool）
- [ ] **#5** 实现 Skill：`product_screenshot`（基于 Playwright，截取产品界面）
- [ ] **#6** 实现 Skill：`gemini_imagegen`（三级降级：Playwright Web → CLI → API）
- [ ] **#7** 实现 Skill：`crop_resize`（图片裁剪缩放到平台规范尺寸，基于 Pillow）
- [ ] **#8** 实现 Skill：`text_overlay`（图片文字叠加，封面标题/说明，基于 Pillow）
- [ ] **#9** 实现 Skill：`watermark`（隐私遮挡打码，截图中的用户数据，基于 Pillow）

---

## 阶段四：基础设施

- [ ] **#10** 实现 Asset Library 管理器（MD5 哈希去重 + JSON 标签索引，`src/orchestrator/asset_library.py`）
- [ ] **#11** 实现 Debate→Synthesize 通用收敛机制（`src/orchestrator/debate.py`）

---

## 阶段五：测试 & 合并

- [ ] **#12** 编写各 Skill 单元测试（mock LLM / 本地素材测试）
- [ ] **#13** 执行 Skill 集成冒烟测试：`screenshot → gemini_imagegen → text_overlay → crop_resize` 完整链路
- [ ] **#14** 将 `develop/develop-skills` 合并回 `main`，开启下一阶段分支（`develop/develop-agents`）

---

## 执行顺序

```
#1 → #2 → #3 → #4 → #5 → #6 ┐
                              ├─ 并行 → #10 → #11 → #12 → #13 → #14
                   #7 → #8 → #9 ┘
```

## 进度总览

| # | 任务 | 状态 |
|---|------|------|
| 1 | 搭建项目目录结构 | ⬜ 待开始 |
| 2 | 完善配置文件 | ⬜ 待开始 |
| 3 | LLM 统一抽象层 | ⬜ 待开始 |
| 4 | Skill: web_search | ⬜ 待开始 |
| 5 | Skill: product_screenshot | ⬜ 待开始 |
| 6 | Skill: gemini_imagegen | ⬜ 待开始 |
| 7 | Skill: crop_resize | ⬜ 待开始 |
| 8 | Skill: text_overlay | ⬜ 待开始 |
| 9 | Skill: watermark | ⬜ 待开始 |
| 10 | Asset Library 管理器 | ⬜ 待开始 |
| 11 | Debate→Synthesize 机制 | ⬜ 待开始 |
| 12 | Skill 单元测试 | ⬜ 待开始 |
| 13 | Skill 集成冒烟测试 | ⬜ 待开始 |
| 14 | 合并分支，开启下一阶段 | ⬜ 待开始 |
