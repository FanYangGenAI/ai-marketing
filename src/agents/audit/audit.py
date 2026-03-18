"""
Audit Agent — 合规与质量审核团队。

角色构成（并行审核，无需 Debate）：
  PlatformAuditor (GPT-4o)   ：平台规则检查（字数、禁用词、图片规格）
  ContentAuditor  (Claude)   ：事实一致性、品牌调性
  SafetyAuditor   (Claude)   ：隐私、版权、安全风险

三个 Auditor 并行执行，结果汇总：
  - 全部通过 → 拷贝到 output/final/，输出 audit_result.json（passed=true）
  - 任一不通过 → 输出修改意见，passed=false

模型：GPT-4o（PlatformAuditor）+ Claude Opus（ContentAuditor + SafetyAuditor）
输出：{daily_folder}/output/audit_result.json
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.platform_adapter import PlatformAdapter


# ── Auditor Prompts ───────────────────────────────────────────────────────────

_PLATFORM_AUDITOR_SYSTEM = """你是一名平台合规审核员（PlatformAuditor）。
审核内容是否符合小红书平台规范：
1. 标题字数 ≤ 20 字
2. 正文字数 500-1000 字
3. 话题标签 3-8 个
4. 无绝对化用语（最强、第一、最佳等）
5. 无违禁词

输出格式（JSON）：
{
  "auditor": "PlatformAuditor",
  "passed": true/false,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}
只输出 JSON，不要其他内容。"""

_CONTENT_AUDITOR_SYSTEM = """你是一名内容质量审核员（ContentAuditor）。
审核内容的质量和一致性：
1. 文案与产品 PRD 描述是否一致（无夸大、无错误信息）
2. 品牌调性是否统一（不同段落语气是否一致）
3. 内容逻辑是否清晰（结构是否合理）
4. 标题是否与正文内容匹配

输出格式（JSON）：
{
  "auditor": "ContentAuditor",
  "passed": true/false,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}
只输出 JSON，不要其他内容。"""

_SAFETY_AUDITOR_SYSTEM = """你是一名内容安全审核员（SafetyAuditor）。
检查内容是否存在以下风险：
1. 隐私泄露风险（图片中是否有未遮挡的个人信息）
2. 版权风险（是否使用了有版权争议的素材描述）
3. 误导性内容（是否存在虚假宣传或误导消费者的内容）
4. 敏感话题（是否涉及政治、宗教、种族等敏感领域）

输出格式（JSON）：
{
  "auditor": "SafetyAuditor",
  "passed": true/false,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}
只输出 JSON，不要其他内容。"""


class AuditAgent(BaseAgent):
    def __init__(
        self,
        openai_client: BaseLLMClient,   # PlatformAuditor
        claude_client: BaseLLMClient,   # ContentAuditor + SafetyAuditor
        platform: str = "xiaohongshu",
    ):
        super().__init__(
            name="Audit",
            llm_client=claude_client,
            role_description="合规审核团队，三个 Auditor 并行审核",
        )
        self._openai = openai_client
        self._platform_adapter = PlatformAdapter(platform)

    async def run(self, context: AgentContext) -> AgentOutput:
        date_str = context.run_date.strftime("%Y-%m-%d")
        result_path = context.daily_folder / "output" / "audit_result.json"
        final_dir = context.subdir("output", "final")
        draft_dir = context.daily_folder / "output" / "draft"

        # ── 读取待审内容 ──────────────────────────────────────────────────────
        package_path = draft_dir / "post_package.json"
        content_path = draft_dir / "post_content.md"
        prd_text = self._read_optional(context.prd_path)
        package_text = self._read_optional(package_path)
        content_text = self._read_optional(content_path)
        platform_spec = self._platform_adapter.build_spec_prompt()

        audit_input = f"""## 待审内容（{date_str}）

### 发布包（JSON）
{package_text}

### 可读版本
{content_text}

### 产品 PRD（参考）
{prd_text[:2000] if prd_text else '（无 PRD）'}

{platform_spec}"""

        # ── 三个 Auditor 并行执行 ─────────────────────────────────────────────
        results = await asyncio.gather(
            self._audit(self._openai, _PLATFORM_AUDITOR_SYSTEM, audit_input),
            self._audit(self.llm_client, _CONTENT_AUDITOR_SYSTEM, audit_input),
            self._audit(self.llm_client, _SAFETY_AUDITOR_SYSTEM, audit_input),
        )

        # ── 汇总结果 ──────────────────────────────────────────────────────────
        all_passed = all(r.get("passed", False) for r in results)
        all_issues = []
        all_suggestions = []
        for r in results:
            all_issues.extend(r.get("issues", []))
            all_suggestions.extend(r.get("suggestions", []))

        audit_result = {
            "date": date_str,
            "passed": all_passed,
            "auditors": results,
            "summary_issues": all_issues,
            "summary_suggestions": all_suggestions,
        }

        result_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(result_path, audit_result)

        # ── 通过则拷贝到 final/ ───────────────────────────────────────────────
        if all_passed and draft_dir.exists():
            for f in draft_dir.iterdir():
                shutil.copy2(f, final_dir / f.name)

        status = "✅ 审核通过" if all_passed else f"❌ 审核未通过（{len(all_issues)} 个问题）"
        return AgentOutput(
            output_path=result_path,
            summary=status,
            success=all_passed,
            error="" if all_passed else "; ".join(all_issues[:3]),
            data=audit_result,
        )

    async def _audit(
        self, client: BaseLLMClient, system: str, content: str
    ) -> dict:
        """调用单个 Auditor，解析 JSON 结果。"""
        messages = [LLMMessage(role="user", content=content)]
        try:
            response = await client.chat(
                messages=messages,
                system=system,
                max_tokens=2048,
                temperature=0.1,
            )
            return self._parse_json(response.content)
        except Exception as e:
            return {
                "auditor": "Unknown",
                "passed": False,
                "issues": [f"Auditor 执行异常: {e}"],
                "suggestions": [],
            }

    @staticmethod
    def _parse_json(content: str) -> dict:
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        json_str = m.group(1) if m else content
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"passed": False, "issues": ["JSON 解析失败"], "suggestions": []}
