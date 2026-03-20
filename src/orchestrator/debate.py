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
from pathlib import Path

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
    log_path: Path | None = None,
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

        # 打印本轮各 Agent 输出
        for op in opinions:
            logger.debug(
                "\n%s\n[Round %d] %s (%s)\n%s\n%s",
                "─" * 60, round_num, op.agent_name, op.model,
                op.content,
                "─" * 60,
            )

        # 写入原始输出日志
        if log_path:
            _write_round_log(log_path, round_num, list(opinions))

        # Round 1 后：让 Moderator 判断是否需要继续讨论
        if round_num == 1 and max_rounds > 1:
            should_continue = await _moderator_should_continue(
                moderator_client, context, list(opinions), log_path=log_path
            )
            if not should_continue:
                logger.info("[Debate] Moderator: opinions convergent after Round 1, skipping further rounds.")
                break

        # Round 2+ 超过半数同意 → 提前收敛
        if round_num > 1:
            agree_count = sum(op.agree for op in opinions)
            if agree_count > len(opinions) / 2:
                logger.info(
                    f"[Debate] Majority agree ({agree_count}/{len(opinions)}). "
                    f"Converging after round {round_num}."
                )
                break

        # 生成本轮小结（供下一轮参考）
        current_summary = _format_opinions(opinions, round_num)

    # Moderator 综合所有轮次发言，输出最终结论
    final_output = await _moderator_synthesize(
        moderator_client,
        context,
        all_round_opinions,
        moderator_system,
        log_path=log_path,
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
        max_tokens=8192,  # thinking 模式下需要足够预算，确保末尾"同意/不同意"不被截断
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
    log_path: Path | None = None,
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
    logger.debug(
        "\n%s\n[Moderator 输入]\n系统提示:\n%s\n\n用户消息:\n%s\n%s",
        "=" * 60, system or default_system, user_msg, "=" * 60,
    )
    response = await client.chat(
        messages=[LLMMessage(role="user", content=user_msg)],
        system=system or default_system,
        max_tokens=4096,
    )
    logger.debug(
        "\n%s\n[Moderator 输出]\n%s\n%s",
        "=" * 60, response.content, "=" * 60,
    )
    if log_path:
        _write_moderator_log(log_path, system or default_system, user_msg, response.content)
    return response.content


def _format_opinions(opinions: list[AgentOpinion], round_num: int) -> str:
    """格式化一轮发言，用于传给下一轮作为参考。"""
    lines = [f"[Round {round_num} 小结]"]
    for op in opinions:
        lines.append(f"{op.agent_name}: {op.content[:200]}...")
    return "\n".join(lines)


async def _moderator_should_continue(
    client: BaseLLMClient,
    context: str,
    opinions: list[AgentOpinion],
    log_path: Path | None = None,
) -> bool:
    """Round 1 后，让 Moderator 快速判断是否需要继续讨论。"""
    opinions_text = "\n\n".join(
        f"【{op.agent_name}】\n{op.content}" for op in opinions
    )
    system = (
        "你是讨论主持人。请判断各方 Round 1 观点是否已充分互补、方向一致，"
        "可以直接综合出结论，无需进一步讨论。\n"
        "只需回答：收敛 或 继续（仅此二字）。"
    )
    user_msg = f"各方观点：\n{opinions_text}"
    response = await client.chat(
        messages=[LLMMessage(role="user", content=user_msg)],
        system=system,
        max_tokens=1024,  # thinking 模式需要足够 token 预算，实际回复只有 2 字
    )
    decision = response.content.strip()
    if not decision:
        logger.warning("[Debate] Moderator convergence check returned empty response, defaulting to 继续")
        decision = "继续"
    logger.info(f"[Debate] Moderator convergence check → {decision!r}")
    should_continue = not decision.startswith("收敛")
    if log_path:
        _write_convergence_log(log_path, system, user_msg, decision, should_continue)
    return should_continue


def _write_round_log(log_path: Path, round_num: int, opinions: list[AgentOpinion]) -> None:
    """将本轮原始输出追加写入日志文件。"""
    mode = "w" if round_num == 1 else "a"
    with open(log_path, mode, encoding="utf-8") as f:
        if round_num == 1:
            f.write("# Debate 原始输出日志\n\n")
        f.write(f"## Round {round_num}\n\n")
        for op in opinions:
            f.write(f"### {op.agent_name}  `{op.model}`\n\n")
            f.write(op.content)
            f.write("\n\n")
            if round_num > 1:
                f.write(f"> agree={op.agree}\n\n")
            f.write("---\n\n")


def _write_convergence_log(
    log_path: Path, system: str, user_msg: str, decision: str, should_continue: bool
) -> None:
    """将 Round 1 后的收敛判断写入日志文件。"""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("## Moderator 收敛判断（Round 1 后）\n\n")
        f.write("### 系统提示\n\n")
        f.write(system)
        f.write("\n\n### 用户消息\n\n")
        f.write(user_msg)
        f.write("\n\n### 判断结果\n\n")
        f.write(f"> **{decision}** → {'继续讨论' if should_continue else '提前收敛，跳过后续轮次'}\n\n")
        f.write("---\n\n")


def _write_moderator_log(log_path: Path, system: str, user_msg: str, output: str) -> None:
    """将 Moderator 输入输出追加写入日志文件。"""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("## Moderator\n\n")
        f.write("### 系统提示\n\n")
        f.write(system)
        f.write("\n\n### 用户消息\n\n")
        f.write(user_msg)
        f.write("\n\n### 输出\n\n")
        f.write(output)
        f.write("\n")
