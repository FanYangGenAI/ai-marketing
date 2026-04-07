"""
Creator Agent — 物料组装团队。

职责：
  读取 daily_marketing_script.md + director/director_task_result.json + 平台规范，
  将文案和素材路径组装为「平台发布包」结构文件。

模型：见 llm_config.json creator（默认 Gemini）
输出：
  - {daily_folder}/creator/creator_raw.md          — LLM 原始响应日志
  - {daily_folder}/creator/post_package.json        — 发布包结构（JSON）
  - {daily_folder}/creator/post_content.md          — 可读版发布物料（Markdown）
"""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.content_validator import enforce_platform_copy
from src.orchestrator.llm_temperatures import CREATIVE_SCRIPT_DIRECTOR_CREATOR
from src.orchestrator.platform_adapter import PlatformAdapter


_CREATOR_SYSTEM = """你是一名内容发布打包专员（Creator）。
你将收到：
  1. 营销脚本（含推荐标题、正文、话题标签、配图列表）
  2. 素材清单（每张图的实际文件路径）
  3. 平台规范

你的任务是将两者对应整合，输出两个独立的代码块：

【第一块】正文全文，使用 ```body 标记：
```body
（正文内容，可自由使用任何标点符号，不受 JSON 转义限制）
```

【第二块】结构化元数据，使用 ```json 标记（body 字段留空字符串）：
```json
{
  "platform": "xiaohongshu",
  "date": "YYYY-MM-DD",
  "title": "最终标题（≤20字）",
  "body": "",
  "hashtags": ["#标签1", "#标签2"],
  "images": [
    {
      "order": 1,
      "path": "实际文件路径",
      "caption": "可选的图片说明"
    }
  ],
  "ready_for_audit": true
}
```

注意：
- 如果某张图片在素材清单中标记为失败（success=false），在 caption 中注明「待补充」，并将 ready_for_audit 设为 false。
- 必须先输出 ```body 块，再输出 ```json 块，顺序不能颠倒。"""


class CreatorAgent(BaseAgent):
    def __init__(self, llm_client: BaseLLMClient, platform: str = "xiaohongshu"):
        super().__init__(
            name="Creator",
            llm_client=llm_client,
            role_description="物料组装，将文案和素材整合为平台发布包",
        )
        self._platform_adapter = PlatformAdapter(platform)

    async def run(self, context: AgentContext) -> AgentOutput:
        date_str = context.run_date.strftime("%Y-%m-%d")
        creator_dir = context.subdir("creator")
        attempt_dir = context.stage_attempt_dir("creator")
        raw_path = creator_dir / "creator_raw.md"
        package_path = creator_dir / "post_package.json"
        content_path = creator_dir / "post_content.md"

        # ── 读取上游输出 ──────────────────────────────────────────────────────
        script_text = self._read_optional(
            context.daily_folder / "script" / "daily_marketing_script.md"
        )
        task_result_text = self._read_optional(
            context.daily_folder / "director" / "director_task_result.json"
        )
        platform_spec = self._platform_adapter.build_spec_prompt()

        # ── 调用 LLM 组装 ─────────────────────────────────────────────────────
        user_msg = f"""## 日期：{date_str}

## 营销脚本
{script_text}

## 素材清单（Director 执行结果）
{task_result_text}

{platform_spec}

请按格式输出发布包 JSON。"""

        messages = [LLMMessage(role="user", content=user_msg)]
        response = await self.llm_client.chat(
            messages=messages,
            system=_CREATOR_SYSTEM,
            max_tokens=4096,
            temperature=CREATIVE_SCRIPT_DIRECTOR_CREATOR,
        )

        # ── 保存原始输出 ──────────────────────────────────────────────────────
        self._write_raw_log(raw_path, user_msg, response.content, date_str)

        # ── 解析并写入输出 ────────────────────────────────────────────────────
        body_text = self._extract_body_block(response.content)
        package = self._parse_json(response.content)
        package["body"] = body_text

        hard = self._platform_adapter.hard_rules
        new_title, new_body, viol_before, viol_after = enforce_platform_copy(
            package.get("title"),
            package.get("body"),
            hard,
        )
        package["title"] = new_title
        package["body"] = new_body
        package["platform_hard_rules_applied"] = True
        if viol_before:
            package["copy_violations_before_enforce"] = [v.to_dict() for v in viol_before]

        validation_path = creator_dir / "copy_validation.json"
        validation_path.write_text(
            json.dumps(
                {
                    "violations_before": [v.to_dict() for v in viol_before],
                    "violations_after": [v.to_dict() for v in viol_after],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self._write_json(package_path, package)

        readable = self._package_to_markdown(package, date_str)
        self._write_output(content_path, readable)
        self._copy_attempt_file(raw_path, attempt_dir / "creator_raw.md")
        self._copy_attempt_file(package_path, attempt_dir / "post_package.json")
        self._copy_attempt_file(content_path, attempt_dir / "post_content.md")
        self._copy_attempt_file(validation_path, attempt_dir / "copy_validation.json")

        ready = package.get("ready_for_audit", False)
        summary = f"发布包已组装，标题：{package.get('title', '未知')}，审核就绪：{ready}"

        return AgentOutput(
            output_path=package_path,
            summary=summary,
            data={
                "package": package,
                "ready_for_audit": ready,
                "attempt_artifacts": [
                    str(attempt_dir / "creator_raw.md"),
                    str(attempt_dir / "post_package.json"),
                    str(attempt_dir / "post_content.md"),
                    str(attempt_dir / "copy_validation.json"),
                ],
            },
        )

    @staticmethod
    def _write_raw_log(raw_path: Path, user_msg: str, llm_response: str, date_str: str) -> None:
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(f"# Creator 原始输出日志 — {date_str}\n\n")
            f.write("## 输入\n\n")
            f.write(user_msg)
            f.write("\n\n---\n\n## LLM 原始响应\n\n")
            f.write(llm_response)
            f.write("\n")

    @staticmethod
    def _extract_body_block(content: str) -> str:
        """提取 ```body ... ``` 块中的正文内容。"""
        import re
        m = re.search(r"```body\s*([\s\S]*?)\s*```", content)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _parse_json(content: str) -> dict:
        import re
        # 提取 ```json ... ``` 块，再找最外层 JSON 对象
        m = re.search(r"```json\s*([\s\S]*?)\s*```", content)
        inner = m.group(1) if m else content
        start = inner.find("{")
        end = inner.rfind("}")
        json_str = inner[start:end + 1] if start != -1 else "{}"
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"raw_response": content, "ready_for_audit": False}

    @staticmethod
    def _package_to_markdown(package: dict, date_str: str) -> str:
        lines = [
            f"# 发布物料 — {date_str}",
            f"\n**平台**：{package.get('platform', '')}",
            f"\n## 标题\n{package.get('title', '')}",
            f"\n## 正文\n{package.get('body', '')}",
            f"\n## 话题标签\n{' '.join(package.get('hashtags', []))}",
            "\n## 配图清单",
        ]
        for img in package.get("images", []):
            lines.append(f"- 图{img.get('order', '?')}：`{img.get('path', '')}` {img.get('caption', '')}")
        lines.append(f"\n**审核就绪**：{'✅ 是' if package.get('ready_for_audit') else '⚠️ 否'}")
        return "\n".join(lines)
