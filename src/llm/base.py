"""
Base class for all LLM clients.
All providers (Claude, OpenAI, Gemini) implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str   # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int


class BaseLLMClient(ABC):
    """Unified interface for all LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a chat request and return the response."""
        ...

    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string."""
        ...
