from .base import BaseLLMClient, LLMMessage, LLMResponse

# 具体客户端按需导入（避免在未安装 SDK 的环境中 import 报错）
def __getattr__(name: str):
    if name == "ClaudeClient":
        from .claude_client import ClaudeClient
        return ClaudeClient
    if name == "OpenAIClient":
        from .openai_client import OpenAIClient
        return OpenAIClient
    if name == "GeminiClient":
        from .gemini_client import GeminiClient
        return GeminiClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BaseLLMClient",
    "LLMMessage",
    "LLMResponse",
    "ClaudeClient",
    "OpenAIClient",
    "GeminiClient",
]
