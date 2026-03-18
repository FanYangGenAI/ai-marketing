"""
Skill: web_search
基于 Claude built-in web_search tool，返回搜索结果摘要。
用于 PlannerA 获取实时热点趋势。
"""

import os
import anthropic
from dataclasses import dataclass


@dataclass
class SearchResult:
    query: str
    summary: str          # Claude 综合搜索结果后的摘要
    raw_results: list[dict]  # 原始搜索条目


async def web_search(query: str, max_results: int = 5) -> SearchResult:
    """
    使用 Claude 内置的 web_search 工具搜索互联网。

    Args:
        query: 搜索关键词
        max_results: 最多返回条目数

    Returns:
        SearchResult，包含 Claude 对搜索结果的摘要
    """
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        tools=[
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": max_results,
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"请搜索：{query}\n\n"
                    "搜索完成后，请用中文总结最重要的 3-5 条信息，"
                    "每条注明来源和发布时间（如有）。"
                ),
            }
        ],
    )

    # 提取文本摘要
    summary = next(
        (b.text for b in response.content if b.type == "text"), ""
    )

    # 提取原始搜索条目（web_search_tool_result blocks）
    raw_results = []
    for block in response.content:
        if block.type == "web_search_tool_result":
            for item in getattr(block, "content", []):
                raw_results.append({
                    "title": getattr(item, "title", ""),
                    "url": getattr(item, "url", ""),
                    "snippet": getattr(item, "encrypted_content", ""),
                })

    return SearchResult(query=query, summary=summary, raw_results=raw_results)
