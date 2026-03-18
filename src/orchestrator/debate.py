"""
Debate → Synthesize 通用收敛机制。
所有多 agent 讨论节点（Planner / Scriptwriter / Audit / Strategist）均使用此模块。

流程：
  Round 1 (并行): 各 agent 独立发言
  Round 2 (并行): 各 agent 对其他人的观点进行点评
  Round 3 (串行): Moderator 综合所有观点，输出最终结论
  最多 MAX_ROUNDS 轮，超时则 Moderator 强制收敛。
"""

import asyncio
import logging
from dataclasses import dataclass

from src.llm.base import BaseLLMClient, LLMMessage

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class AgentOpinion:
    agent_name: str
    model: str
    content: str
    agree: bool = False      # 是否认同当前综合方向（Round 2 开始有效）


@dataclass
class DebateResult:
    final_output: str        # Moderator 最终综合结论
    rounds: int              # 实际进行的轮数
    opinions: list[list[AgentOpinion]]  # 每轮各 agent 的发言


# ── Agent 角色定义 ─────────────────────────────────────────────────────────────

@dataclass
class DebateAgent:
    name: str
    role_description: str    # 该 agent 的角色定位（注入 system prompt）
    client: BaseLLMClient


# ── 主函数 ────────────────────────────────────────────────────────────────────

async def debate_and_synthesize(
    agents: list[DebateAgent],
    moderator_client: BaseLLMClient,
    context: str,
    moderator_system: str = "",
    max_rounds: int = MAX_ROUNDS,
) -> DebateResult:
    """
    执行多 agent 辩论并由 Moderator 收敛输出。

    Args:
        agents:           参与辩论的 agent 列表（非 Moderator）
        moderator_client: Moderator 使用的 LLM 客户端（通常为 Claude Opus）
        context:          辩论的背景信息和任务描述
        moderator_system: Moderator 的 system prompt
        max_rounds:       最大讨论轮数

    Returns:
        DebateResult
    """
    all_round_opinions: list[list[AgentOpinion]] = []
    current_summary = ""

    for round_num in range(1, max_rounds + 1):
        logger.info(f"[Debate] Round {round_num}/{max_rounds} starting...")

        if round_num == 1:
            # Round 1: 各 agent 独立基于 context 发言
            tasks = [
                _agent_speak_round1(agent, context)
                for agent in agents
            ]
        else:
            # Round 2+: 各 agent 基于其他人的观点进行点评
            prev_opinions = all_round_opinions[-1]
            tasks = [
                _agent_speak_round2(agent, context, prev_opinions, current_summary)
                for agent in agents
            ]

        opinions = await asyncio.gather(*tasks)
        all_round_opinions.append(list(opinions))

        # 检查是否所有 agent 都表示同意 → 提前收敛
        if round_num > 1 and all(op.agree for op in opinions):
            logger.info(f"[Debate] All agents agree. Converging after round {round_num}.")
            break

        # 生成本轮小结（供下一轮参考）
        current_summary = _format_opinions(opinions, round_num)

    # Moderator 综合所有轮次发言，输出最终结论
    final_output = await _moderator_synthesize(
        moderator_client,
        context,
        all_round_opinions,
        moderator_system,
    )

    return DebateResult(
        final_output=final_output,
        rounds=len(all_round_opinions),
        opinions=all_round_opinions,
    )


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────

async def _agent_speak_round1(agent: DebateAgent, context: str) -> AgentOpinion:
    """Round 1：agent 基于 context 独立发表观点。"""
    system = (
        f"你是{agent.role_description}。\n"
        "请根据以下背景信息，从你的专业视角独立发表看法，"
        "提出 2-3 个具体建议或观点，言简意赅。"
    )
    response = await agent.client.chat(
        messages=[LLMMessage(role="user", content=context)],
        system=system,
        max_tokens=1024,
    )
    return AgentOpinion(
        agent_name=agent.name,
        model=agent.client.model_name(),
        content=response.content,
    )


async def _agent_speak_round2(
    agent: DebateAgent,
    context: str,
    prev_opinions: list[AgentOpinion],
    current_summary: str,
) -> AgentOpinion:
    """Round 2+：agent 点评其他人的观点，并说明是否同意当前方向。"""
    others = [op for op in prev_opinions if op.agent_name != agent.name]
    others_text = "\n\n".join(
        f"【{op.agent_name}】{op.content}" for op in others
    )
    system = (
        f"你是{agent.role_description}。\n"
        "请评价其他角色的观点：指出你认同和不认同的地方，"
        "并补充你认为被忽视的重要点。\n"
        "最后一行必须是：同意 或 不同意（仅此二字）。"
    )
    user_msg = (
        f"背景：\n{context}\n\n"
        f"其他角色的观点：\n{others_text}"
    )
    response = await agent.client.chat(
        messages=[LLMMessage(role="user", content=user_msg)],
        system=system,
        max_tokens=1024,
    )
    agree = response.content.strip().endswith("同意")
    return AgentOpinion(
        agent_name=agent.name,
        model=agent.client.model_name(),
        content=response.content,
        agree=agree,
    )


async def _moderator_synthesize(
    client: BaseLLMClient,
    context: str,
    all_opinions: list[list[AgentOpinion]],
    system: str,
) -> str:
    """Moderator 综合所有轮次发言，输出最终结论。"""
    opinions_text = ""
    for i, round_opinions in enumerate(all_opinions, 1):
        opinions_text += f"\n=== Round {i} ===\n"
        for op in round_opinions:
            opinions_text += f"\n【{op.agent_name} / {op.model}】\n{op.content}\n"

    default_system = (
        "你是讨论的主持人（Moderator），负责综合多方观点，给出最终结论。\n"
        "要求：客观平衡，吸收各方精华，消除矛盾，输出可直接使用的结构化结果。"
    )
    user_msg = (
        f"任务背景：\n{context}\n\n"
        f"各方讨论记录：\n{opinions_text}\n\n"
        "请综合以上所有观点，输出最终结论（直接给出结果，无需解释讨论过程）。"
    )
    response = await client.chat(
        messages=[LLMMessage(role="user", content=user_msg)],
        system=system or default_system,
        max_tokens=4096,
    )
    return response.content


def _format_opinions(opinions: list[AgentOpinion], round_num: int) -> str:
    """格式化一轮发言，用于传给下一轮作为参考。"""
    lines = [f"[Round {round_num} 小结]"]
    for op in opinions:
        lines.append(f"{op.agent_name}: {op.content[:200]}...")
    return "\n".join(lines)
