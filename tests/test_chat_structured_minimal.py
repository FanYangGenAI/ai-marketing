"""
最小测试：验证 GeminiClient.chat_structured() 能正常工作。
运行方式：python -m pytest tests/test_chat_structured_minimal.py -s -v
或：python tests/test_chat_structured_minimal.py
"""

import asyncio
import os
import sys

sys.path.insert(0, str(__file__).split("tests")[0])

from src.llm.gemini_client import GeminiClient
from src.llm.base import LLMMessage


# ── 测试 1：最简单 schema，无 temperature ────────────────────────────────────
async def test_simple_no_temperature():
    print("\n=== Test 1: simple schema, no temperature ===")
    client = GeminiClient(model="gemini-2.5-flash")

    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING"},
                "score": {"type": "INTEGER"},
            },
            "required": ["name", "score"],
        },
    }

    messages = [LLMMessage(role="user", content="给我3个水果，每个给一个甜度分数(1-10)。")]

    # 不传 temperature
    from google import genai
    from google.genai import types

    client2 = GeminiClient(model="gemini-2.5-flash")
    contents = [types.Content(role="user", parts=[types.Part(text="给我3个水果，每个给一个甜度分数(1-10)。")])]
    config = types.GenerateContentConfig(
        max_output_tokens=512,
        response_mime_type="application/json",
        response_schema=schema,
    )
    response = await client2._client.aio.models.generate_content(
        model=client2._model_name, contents=contents, config=config
    )
    print(f"raw response.text: {repr(response.text)}")
    import json
    result = json.loads(response.text or "[]")
    print(f"parsed result: {result}")
    print("✅ Test 1 PASSED")
    return result


# ── 测试 2：带 temperature=0.1 ───────────────────────────────────────────────
async def test_with_temperature():
    print("\n=== Test 2: schema with temperature=0.1 ===")
    from google import genai
    from google.genai import types
    import json

    client = GeminiClient(model="gemini-2.5-flash")
    contents = [types.Content(role="user", parts=[types.Part(text="给我2个颜色，各一个英文名。")])]
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {"color": {"type": "STRING"}},
            "required": ["color"],
        },
    }
    config = types.GenerateContentConfig(
        max_output_tokens=256,
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=schema,
    )
    try:
        response = await client._client.aio.models.generate_content(
            model=client._model_name, contents=contents, config=config
        )
        print(f"raw response.text: {repr(response.text)}")
        result = json.loads(response.text or "[]")
        print(f"parsed result: {result}")
        print("✅ Test 2 PASSED (temperature=0.1 is accepted)")
    except Exception as e:
        print(f"❌ Test 2 FAILED with temperature=0.1: {e}")
        print("→ Gemini does NOT accept temperature for this model")


# ── 测试 3：通过 GeminiClient.chat_structured() 调用 ─────────────────────────
async def test_via_client_method():
    print("\n=== Test 3: via GeminiClient.chat_structured() ===")
    client = GeminiClient(model="gemini-2.5-flash")

    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "id":     {"type": "STRING"},
                "passed": {"type": "BOOLEAN"},
                "reason": {"type": "STRING"},
            },
            "required": ["id", "passed", "reason"],
        },
    }

    messages = [LLMMessage(role="user", content='对以下两个条目审核一个虚构的帖子，帖子内容："今天天气真好！"。条目：[{"id":"title_length","description":"标题不超过20字"},{"id":"no_superlatives","description":"不使用绝对化用语"}]')]

    result = await client.chat_structured(
        messages=messages,
        response_schema=schema,
        max_tokens=512,
    )
    print(f"result type: {type(result)}")
    print(f"result: {result}")
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    print("✅ Test 3 PASSED")


async def main():
    await test_simple_no_temperature()
    await test_with_temperature()
    await test_via_client_method()
    print("\n=== All tests done ===")


if __name__ == "__main__":
    asyncio.run(main())
