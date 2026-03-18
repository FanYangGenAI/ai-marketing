# Lessons Learned

开发过程中踩过的坑和学到的设计决策，供后续参考。

---

## 1. OpenClaw SKILL 模式

**坑**：最初把 Skills 实现为普通 Python 模块（`from src.skills.image_edit.crop_resize import crop_resize`），可以被程序化 import 和调用。

**正确做法**：Skills 应遵循 OpenClaw 模式：
```
src/skills/{skill-name}/
    SKILL.md        ← Agent 的 SOP 文档（YAML frontmatter + 操作说明）
    scripts/
        xxx.py      ← 纯 CLI 脚本，由 Agent 通过 bash 调用
```

**原因**：SKILL.md 是给 Agent 看的指令文档，不是代码接口。Agent 通过读取 SKILL.md 知道"应该在什么情况下调用这个技能，怎么调用"，然后通过 bash 执行对应脚本。这保持了 Agent 和工具之间的松耦合。

---

## 2. load_dotenv 的 override 行为

**坑**：Windows 系统环境变量中存在 `ANTHROPIC_API_KEY=`（空字符串）。`load_dotenv()` 默认不覆盖已存在的环境变量，导致 .env 里的真实 key 被忽略，API 调用返回 401。

**修复**：
```python
load_dotenv(override=True)  # 强制用 .env 的值覆盖系统空变量
```

**教训**：在 Windows 开发环境中，`load_dotenv()` 不加 `override=True` 是隐患。

---

## 3. Windows 控制台 UTF-8 编码

**坑**：Python 脚本在 Windows 上打印 emoji（✅ ❌ 🚀）时报 `UnicodeEncodeError: 'charmap' codec can't encode character`。Windows 控制台默认使用 cp1252 编码。

**修复方案**：
```python
# 在脚本入口处
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

对于 subprocess 调用（测试中）：
```python
env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
subprocess.run(..., encoding="utf-8", env=env)
```

---

## 4. Anthropic thinking 参数

**坑**：`thinking={"type": "enabled", "budget_tokens": 2000}` 会触发 deprecation warning。

**正确用法**：
```python
thinking={"type": "adaptive"}
```
`adaptive` 是当前推荐模式，让模型自动决定是否启用 extended thinking，性能更好。

---

## 5. Gemini SDK 迁移

**坑**：`google-generativeai`（旧 SDK）已被 `google-genai`（新 SDK）取代，部分 API 接口不同。

**新 SDK 用法**：
```python
import google.genai as genai
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=...,
)
```

注意：`GOOGLE_API_KEY` 和 `GEMINI_API_KEY` 同时设置时，新 SDK 优先使用 `GOOGLE_API_KEY`，会有警告。建议统一使用一个。

---

## 6. Pipeline 顶层 import 导致 dry-run 失败

**坑**：`pipeline.py` 顶层 import 了 `ClaudeClient`、`OpenAIClient` 等，只要 import pipeline 模块就会触发 SDK 导入，即使是 dry-run 也需要安装所有依赖。

**修复**：将 LLM 客户端和 Agent 的 import 移入 `_init_agents()` 方法，在真正 `run()` 时才执行（dry_run 时跳过）。

```python
def _init_agents(self):
    from src.llm.claude_client import ClaudeClient  # 延迟 import
    ...
```

**教训**：任何需要外部 API key 或重型依赖的模块，应该延迟 import，保持 dry-run / 测试 的快速启动。

---

## 7. Debate→Synthesize 收敛判断

**当前实现**：Round 2 后检测所有 Agent 的最后一行是否为「同意」二字，若全部同意则提前收敛，跳过后续轮次。

**观察**：实际运行中，三个来自不同 LLM 的 Agent 在 Round 2 很少全部输出"同意"，通常跑满 3 轮。这是合理的——不同模型有不同视角，分歧是有价值的输出。Moderator 的综合质量反而更高。

**建议**：`max_rounds=3` 是合适的默认值，不需要调高。如果希望加速可降为 2，质量略有下降但可接受。

---

## 8. 测试策略：CLI 脚本用 subprocess 测试

**原则**：Skills 的脚本是 CLI 工具，测试方式应与 Agent 使用方式一致——通过 subprocess 调用，而不是 import 内部函数。

```python
result = subprocess.run(
    [sys.executable, str(SCRIPT), "--input", ..., "--output", ...],
    capture_output=True, text=True, encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
)
assert result.returncode == 0
assert "✅" in result.stdout
```

**好处**：测试真实的 CLI 接口，捕获真实的退出码和输出，与 Agent 调用路径完全一致。

---

## 9. 图片马赛克测试的陷阱

**坑**：测试隐私马赛克效果时，如果测试图片的遮挡区域是**纯色**（如纯红色矩形），马赛克处理后像素值不变（纯色区域平均值还是原色），导致 `assert pixel != (255, 0, 0)` 永远失败。

**修复**：测试图片的敏感区域需要包含**多种颜色**（如左半红右半蓝），马赛克才能产生可观测的混色效果。
