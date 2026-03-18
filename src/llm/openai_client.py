"""
OpenAI client.
Used by: PlannerC, ScriptwriterA, ScriptwriterC,
         PlatformAuditor, StrategyReviewer.
"""

import os
from openai import AsyncOpenAI
from .base import BaseLLMClient, LLMMessage, LLMResponse


class OpenAIClient(BaseLLMClient):
    def __init__(self, model: str = "gpt-4o"):
        self._model = model
        self._client = AsyncOpenAI(
            api_key=os.environ["OPENAI_API_KEY"]
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

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=self._model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
