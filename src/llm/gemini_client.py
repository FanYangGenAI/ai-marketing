"""
Gemini client (google-genai SDK — 新 SDK，替代已弃用的 google-generativeai)。
用于：PlannerA, ScriptwriterB, Director, StrategyDataAnalyst。

SDK 迁移说明：
  旧：import google.generativeai as genai  (已于 2025-11-30 停止维护)
  新：from google import genai             (google-genai 包)
"""

import os
from pathlib import Path
from google import genai
from google.genai import types

from .base import BaseLLMClient, LLMMessage, LLMResponse

_IMAGE_MODEL = "nano-banana-pro-preview"

_VALID_ASPECT_RATIOS = {"1:1", "3:4", "4:3", "9:16", "16:9"}


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

    async def generate_image(
        self,
        prompt: str,
        output_path: str | Path,
        aspect_ratio: str = "3:4",
    ) -> Path:
        """
        使用 nano-banana-pro-preview 生成图片，保存到 output_path。

        Args:
            prompt:       图片描述（支持中文）
            output_path:  保存路径（.png）
            aspect_ratio: 图片比例，支持 1:1 / 3:4 / 4:3 / 9:16 / 16:9

        Returns:
            保存成功的文件路径
        """
        if aspect_ratio not in _VALID_ASPECT_RATIOS:
            aspect_ratio = "3:4"

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        response = await self._client.aio.models.generate_content(
            model=_IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                out.write_bytes(part.inline_data.data)
                return out

        raise ValueError(f"generate_image: API 未返回图像数据（model={_IMAGE_MODEL}）")
