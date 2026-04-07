"""
OpenAI client.
Used by: PlannerC, ScriptwriterA, ScriptwriterC,
         PlatformAuditor, StrategyReviewer.
"""

import os
from openai import AsyncOpenAI
from .base import BaseLLMClient, LLMMessage, LLMResponse


# gpt-5-nano 及以上新模型使用 max_completion_tokens；旧模型（gpt-4o 等）使用 max_tokens
_NEW_TOKEN_PARAM_MODELS = {"gpt-5-nano", "o1", "o3", "o4"}


class OpenAIClient(BaseLLMClient):
    def __init__(self, model: str = "gpt-5-nano"):
        self._model = model
        self._client = AsyncOpenAI(
            api_key=os.environ["OPENAI_API_KEY"]
        )
        # 判断当前模型是否需要 max_completion_tokens
        self._use_completion_tokens = any(
            model.startswith(prefix) for prefix in _NEW_TOKEN_PARAM_MODELS
        )

    def model_name(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        api_messages = []
        if system:
            api_messages.append({"role": "system", "content": system})
        api_messages += [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        token_param = (
            {"max_completion_tokens": max_tokens}
            if self._use_completion_tokens
            else {"max_tokens": max_tokens}
        )
        kwargs: dict = dict(model=self._model, messages=api_messages, **token_param)
        # gpt-5-nano 及新推理模型只支持 temperature=1（默认），不接受其他值
        if not self._use_completion_tokens:
            kwargs["temperature"] = temperature
        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=self._model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
