---
name: web-search
description: >
  Use this skill whenever you need to search the internet for real-time information.
  Triggers when: (1) researching trending topics or hot keywords for marketing plans,
  (2) checking competitor content or industry news, (3) finding platform-specific
  best practices or algorithm updates. NOT for: reading local files or querying
  the asset library.
user-invocable: false
metadata:
  openclaw:
    requires:
      env: [ANTHROPIC_API_KEY]
---

# Skill: web-search

## 用途
通过 Claude 内置的 `web_search` 工具搜索互联网，获取实时信息。
主要用于 **Planner** 阶段搜索当日热点话题和行业趋势。

## 使用方式

直接在你的 `client.messages.create()` 调用中声明工具：

```python
tools = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 5,  # 每次调用最多搜索 5 次
    }
]
```

然后在 prompt 中描述你要搜索的内容，Claude 会自动决定何时调用搜索。

## Prompt 最佳实践

搜索热点话题时，建议使用如下 prompt 结构：

```
请搜索以下主题的今日热点：{topic}

搜索完成后，请输出：
1. 最热门的 3-5 个话题方向（附来源和时间）
2. 每个方向的核心关键词
3. 哪个方向与我们的产品【{product_name}】结合度最高
```

## 输出格式

搜索结果应整理为以下结构（供 Planner 讨论使用）：

```markdown
## 今日热点搜索结果 - {date}

### 话题一：{标题}
- 来源：{URL}
- 热度：{描述}
- 与产品的结合点：{分析}

### 话题二：...
```

## 注意事项

- 搜索结果可能包含过时信息，关注结果中的发布时间
- 如果搜索结果质量低，尝试更换关键词重新搜索
- 每次 Planner 调用此 Skill 时，搜索数量控制在 3-5 次以内，避免过度消耗 token
