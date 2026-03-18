"""
Creator Agent — 物料组装团队。

职责：
  读取 daily_marketing_script.md + director_task_result.json + 平台规范，
  将文案和素材路径组装为「平台发布包」结构文件。

模型：Claude Opus（指令执行精准，组装逻辑清晰）
输出：{daily_folder}/output/draft/post_package.json + post_content.md
"""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.platform_adapter import PlatformAdapter


_CREATOR_SYSTEM = """你是一名内容发布打包专员（Creator）。
你将收到：
  1. 营销脚本（含推荐标题、正文、话题标签、配图列表）
  2. 素材清单（每张图的实际文件路径）
  3. 平台规范

你的任务是将两者对应整合，输出一份「发布包描述」。

输出格式（严格 JSON）：
{
  "platform": "xiaohongshu",
  "date": "YYYY-MM-DD",
  "title": "最终标题（≤20字）",
  "body": "正文全文（符合字数要求）",
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

如果某张图片在素材清单中标记为失败（success=false），
请在对应 caption 中注明「待补充」，并将 ready_for_audit 设为 false。"""


class CreatorAgent(BaseAgent):
    def __init__(self, claude_client: BaseLLMClient, platform: str = "xiaohongshu"):
        super().__init__(
            name="Creator",
            llm_client=claude_client,
            role_description="物料组装，将文案和素材整合为平台发布包",
        )
        self._platform_adapter = PlatformAdapter(platform)

    async def run(self, context: AgentContext) -> AgentOutput:
        date_str = context.run_date.strftime("%Y-%m-%d")
        draft_dir = context.subdir("output", "draft")
        package_path = draft_dir / "post_package.json"
        content_path = draft_dir / "post_content.md"

        # ── 读取上游输出 ──────────────────────────────────────────────────────
        script_text = self._read_optional(
            context.daily_folder / "script" / "daily_marketing_script.md"
        )
        task_result_path = context.daily_folder / "director_task_result.json"
        task_result_text = self._read_optional(task_result_path)
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
            temperature=0.2,
        )

        # ── 解析并写入输出 ────────────────────────────────────────────────────
        package = self._parse_json(response.content)
        self._write_json(package_path, package)

        # 同时输出一份可读的 Markdown
        readable = self._package_to_markdown(package, date_str)
        self._write_output(content_path, readable)

        ready = package.get("ready_for_audit", False)
        summary = f"发布包已组装，标题：{package.get('title', '未知')}，审核就绪：{ready}"

        return AgentOutput(
            output_path=package_path,
            summary=summary,
            data={"package": package, "ready_for_audit": ready},
        )

    @staticmethod
    def _parse_json(content: str) -> dict:
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            json_str = m.group(1)
        else:
            start = content.find("{")
            end = content.rfind("}")
            json_str = content[start:end + 1] if start != -1 else "{}"
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
