"""
Gemini client (google-genai SDK — 新 SDK，替代已弃用的 google-generativeai)。
用于：PlannerA, ScriptwriterB, Director, StrategyDataAnalyst。

SDK 迁移说明：
  旧：import google.generativeai as genai  (已于 2025-11-30 停止维护)
  新：from google import genai             (google-genai 包)
"""

import os
from google import genai
from google.genai import types

from .base import BaseLLMClient, LLMMessage, LLMResponse


class GeminiClient(BaseLLMClient):
    def __init__(self, model: str = "gemini-2.5-flash"):
        self._model_name = model
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def model_name(self) -> str:
        return self._model_name

    async def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        # 构建多轮对话历史（新 SDK 使用 types.Content 对象列表）
        contents: list[types.Content] = []

        for m in messages:
            if m.role == "system":
                continue  # system 通过 GenerateContentConfig.system_instruction 注入
            role = "user" if m.role == "user" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=m.content)])
            )

        config = types.GenerateContentConfig(
            system_instruction=system or "",
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )

        text = response.text or ""
        usage = response.usage_metadata
        return LLMResponse(
            content=text,
            model=self._model_name,
            input_tokens=getattr(usage, "prompt_token_count", 0),
            output_tokens=getattr(usage, "candidates_token_count", 0),
        )
