"""
Gemini client (Google Generative AI SDK).
Used by: PlannerA, ScriptwriterB, Director,
         StrategyDataAnalyst.
"""

import os
import google.generativeai as genai
from .base import BaseLLMClient, LLMMessage, LLMResponse


class GeminiClient(BaseLLMClient):
    def __init__(self, model: str = "gemini-2.0-flash"):
        self._model_name = model
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._model = genai.GenerativeModel(model)

    def model_name(self) -> str:
        return self._model_name

    async def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        # Build Gemini history format
        history = []
        pending_user = None

        for m in messages:
            if m.role == "system":
                continue
            if m.role == "user":
                pending_user = m.content
            elif m.role == "assistant" and pending_user is not None:
                history.append({"role": "user", "parts": [pending_user]})
                history.append({"role": "model", "parts": [m.content]})
                pending_user = None

        # System prompt injected as the first user turn if provided
        system_prefix = f"{system}\n\n" if system else ""
        final_user_msg = system_prefix + (pending_user or "")

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        chat_session = self._model.start_chat(history=history)
        response = await chat_session.send_message_async(
            final_user_msg,
            generation_config=generation_config,
        )

        text = response.text or ""
        usage = response.usage_metadata
        return LLMResponse(
            content=text,
            model=self._model_name,
            input_tokens=getattr(usage, "prompt_token_count", 0),
            output_tokens=getattr(usage, "candidates_token_count", 0),
        )
