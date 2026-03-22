"""
Claude client (Anthropic SDK).
Used by: PlannerB, PlannerModerator, ScriptwriterModerator,
         Creator, ContentAuditor, SafetyAuditor, StrategyModerator.
"""

import os
import anthropic
from .base import BaseLLMClient, LLMMessage, LLMResponse


class ClaudeClient(BaseLLMClient):
    def __init__(self, model: str = "claude-opus-4-6"):
        self._model = model
        # 优先 ANTHROPIC_API_KEY，fallback 到 Claude Code 的 OAuth token
        api_key = (
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        )
        if not api_key:
            raise EnvironmentError(
                "未找到 Anthropic 认证信息，请设置 ANTHROPIC_API_KEY 或 CLAUDE_CODE_OAUTH_TOKEN"
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens,
            messages=api_messages,
            thinking={"type": "adaptive"},
            temperature=1,  # adaptive thinking requires temperature=1
        )
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)

        text = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        return LLMResponse(
            content=text,
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
