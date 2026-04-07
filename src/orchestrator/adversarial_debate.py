"""
Adversarial debate orchestrator.

Key behavior:
  - Round 1: each agent proposes A/B/C and recommends one plan.
  - Round 2: cross challenges only, no defense.
  - Round 3a: defense against received challenges.
  - Round 3b: score opponent plans (A/B/C) after full defense.
  - Moderator may continue with controversy points or converge.
  - Finalize one selected plan and archive alternatives.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.alternative_plan_memory import AlternativePlanRecord, SelectedPlanRecord

logger = logging.getLogger(__name__)


@dataclass
class DebateAgent:
    name: str
    role_description: str
    client: BaseLLMClient


@dataclass
class PlanProposal:
    label: str
    core_claim: str
    audience_logic: str
    expected_outcome: str
    assumptions: str


@dataclass
class AgentRound1:
    agent_name: str
    model: str
    proposals: list[PlanProposal]
    recommended_label: str
    recommended_reason: str
    raw_text: str


@dataclass
class Challenge:
    from_agent: str
    to_agent: str
    to_plan_label: str
    question: str


@dataclass
class AgentRound2:
    agent_name: str
    model: str
    challenges_given: list[Challenge]
    challenges_received: list[Challenge] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ProposalDefense:
    plan_label: str
    response_type: str  # maintain / revise / switch
    response_text: str


@dataclass
class AgentRound3a:
    agent_name: str
    model: str
    defenses: list[ProposalDefense]
    final_plan_label: str
    full_text: str


@dataclass
class ProposalScore:
    plan_label: str
    score: float
    reason: str


@dataclass
class AgentRound3b:
    from_agent: str
    to_agent: str
    scores: list[ProposalScore]
    raw_text: str


@dataclass
class AdversarialDebateResult:
    selected_plan: SelectedPlanRecord
    selected_plan_full_text: str
    alternative_plans: list[AlternativePlanRecord]
    rounds_conducted: int
    round1_outputs: list[AgentRound1]
    round2_outputs: list[AgentRound2]
    round3a_outputs: list[AgentRound3a]
    round3b_outputs: list[AgentRound3b]


async def adversarial_debate(
    agents: list[DebateAgent],
    moderator_client: BaseLLMClient,
    context: str,
    moderator_system: str = "",
    max_extra_rounds: int = 1,
    log_path: Path | None = None,
    round1_temperature: float = 1.0,
    discussion_temperature: float = 0.0,
    agent_contexts: dict[str, str] | None = None,
) -> AdversarialDebateResult:
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    private_contexts = agent_contexts or {}
    _log_search_contexts(log_path, private_contexts)

    round1_outputs = await _run_round1(agents, context, round1_temperature, private_contexts)
    _log_round1(log_path, round1_outputs)

    skip_debate = await _moderator_quick_check(moderator_client, round1_outputs)
    if skip_debate:
        selected_text, selected, alternatives = await _moderator_finalize(
            moderator_client,
            context,
            moderator_system,
            round1_outputs,
            [],
            [],
            [],
        )
        _log_final(log_path, selected_text)
        return AdversarialDebateResult(
            selected_plan=selected,
            selected_plan_full_text=selected_text,
            alternative_plans=alternatives,
            rounds_conducted=0,
            round1_outputs=round1_outputs,
            round2_outputs=[],
            round3a_outputs=[],
            round3b_outputs=[],
        )

    round2_outputs: list[AgentRound2] = []
    round3a_outputs: list[AgentRound3a] = []
    round3b_outputs: list[AgentRound3b] = []
    controversy_points: list[str] = []
    rounds_conducted = 0

    for i in range(max_extra_rounds + 1):
        cycle = i + 1
        round2_outputs = await _run_round2(
            agents=agents,
            round1_outputs=round1_outputs,
            context=context,
            controversy_points=controversy_points,
            temperature=discussion_temperature,
        )
        _fill_received_challenges(round2_outputs)
        _log_round2(log_path, cycle, round2_outputs)

        round3a_outputs = await _run_round3a(
            agents=agents,
            round1_outputs=round1_outputs,
            round2_outputs=round2_outputs,
            context=context,
            temperature=discussion_temperature,
        )
        _log_round3a(log_path, cycle, round3a_outputs)

        round3b_outputs = await _run_round3b(
            agents=agents,
            round1_outputs=round1_outputs,
            round2_outputs=round2_outputs,
            round3a_outputs=round3a_outputs,
            context=context,
            temperature=discussion_temperature,
        )
        _log_round3b(log_path, cycle, round3b_outputs)

        rounds_conducted += 1
        if i >= max_extra_rounds:
            break

        should_continue, controversy_points = await _moderator_decide_continue(
            moderator_client=moderator_client,
            round1_outputs=round1_outputs,
            round3a_outputs=round3a_outputs,
            round3b_outputs=round3b_outputs,
        )
        _log_continue_decision(log_path, should_continue, controversy_points)
        if not should_continue:
            break

    selected_text, selected, alternatives = await _moderator_finalize(
        moderator_client,
        context,
        moderator_system,
        round1_outputs,
        round2_outputs,
        round3a_outputs,
        round3b_outputs,
    )
    _log_final(log_path, selected_text)

    return AdversarialDebateResult(
        selected_plan=selected,
        selected_plan_full_text=selected_text,
        alternative_plans=alternatives,
        rounds_conducted=rounds_conducted,
        round1_outputs=round1_outputs,
        round2_outputs=round2_outputs,
        round3a_outputs=round3a_outputs,
        round3b_outputs=round3b_outputs,
    )


_ROUND1_SYSTEM = """\
你是{role_description}。

你的任务：基于以下背景信息，独立提出 3 个备选营销策略方案。

【输出格式（严格遵守）】

## 方案A
- 核心主张：（一句话）
- 目标受众与触达逻辑：
- 预期效果：
- 关键假设前提：

## 方案B
- 核心主张：
- 目标受众与触达逻辑：
- 预期效果：
- 关键假设前提：

## 方案C
- 核心主张：
- 目标受众与触达逻辑：
- 预期效果：
- 关键假设前提：

## 我的推荐
推荐方案：A / B / C（选一个）
推荐理由：（2-3句）
"""


async def _run_round1(
    agents: list[DebateAgent],
    context: str,
    temperature: float,
    agent_contexts: dict[str, str],
) -> list[AgentRound1]:
    tasks = [_agent_round1(a, context, temperature, agent_contexts.get(a.name, "")) for a in agents]
    return list(await asyncio.gather(*tasks))


async def _agent_round1(
    agent: DebateAgent,
    context: str,
    temperature: float,
    agent_context: str,
) -> AgentRound1:
    system = _ROUND1_SYSTEM.format(role_description=agent.role_description)
    user_content = f"{agent_context}\n\n{context}".strip() if agent_context else context
    response = await agent.client.chat(
        messages=[LLMMessage(role="user", content=user_content)],
        system=system,
        max_tokens=8192,
        temperature=temperature,
    )
    proposals, rec_label, rec_reason = _parse_round1(response.content)
    return AgentRound1(
        agent_name=agent.name,
        model=agent.client.model_name(),
        proposals=proposals,
        recommended_label=rec_label,
        recommended_reason=rec_reason,
        raw_text=response.content,
    )


def _parse_round1(text: str) -> tuple[list[PlanProposal], str, str]:
    proposals: list[PlanProposal] = []
    for label in ["A", "B", "C"]:
        m = re.search(rf"##\s*方案{label}\s*\n(.*?)(?=##\s*方案[A-Z]|##\s*我的推荐|\Z)", text, re.DOTALL)
        section = m.group(1) if m else ""
        proposals.append(
            PlanProposal(
                label=label,
                core_claim=_extract_field(section, ["核心主张"]),
                audience_logic=_extract_field(section, ["目标受众与触达逻辑", "目标受众"]),
                expected_outcome=_extract_field(section, ["预期效果"]),
                assumptions=_extract_field(section, ["关键假设前提", "假设前提"]),
            )
        )

    rec = re.search(r"推荐方案[：:]\s*\**([ABC])\**", text)
    reason = re.search(r"推荐理由[：:]\s*(.+?)(?:\n\n|\Z)", text, re.DOTALL)
    return proposals, rec.group(1) if rec else "A", reason.group(1).strip() if reason else ""


_ROUND2_SYSTEM = """\
你是{role_description}。

以下是另一位策略师在 Round 1 中提出的方案，请以对抗性态度审视：

{other_agent_round1_output}

【你的任务】
对对方的推荐方案（及其他方案，如有必要），提出 1-3 个具有挑战性的质疑：
- 方案的逻辑漏洞或内部矛盾
- 关键假设是否成立
- 执行可行性或资源依赖
- 是否与已知失败规律重叠

{controversy_context}

【输出格式】
## 质疑
1. [质疑1]
2. [质疑2]
3. [质疑3（可选）]

【禁止】：不得在本轮为自己的方案辩护，也不得回应对自己的质疑。
"""


async def _run_round2(
    agents: list[DebateAgent],
    round1_outputs: list[AgentRound1],
    context: str,
    controversy_points: list[str],
    temperature: float,
) -> list[AgentRound2]:
    tasks = [_agent_round2(a, round1_outputs, context, controversy_points, temperature) for a in agents]
    return list(await asyncio.gather(*tasks))


async def _agent_round2(
    agent: DebateAgent,
    round1_outputs: list[AgentRound1],
    context: str,
    controversy_points: list[str],
    temperature: float,
) -> AgentRound2:
    others = [r for r in round1_outputs if r.agent_name != agent.name]
    challenges: list[Challenge] = []
    raw_blocks: list[str] = []
    controversy_context = ""
    if controversy_points:
        bullets = "\n".join(f"- {p}" for p in controversy_points[:3])
        controversy_context = f"Moderator 争议点（优先聚焦）：\n{bullets}"

    for target in others:
        target_text = target.raw_text
        system = _ROUND2_SYSTEM.format(
            role_description=agent.role_description,
            other_agent_round1_output=target_text,
            controversy_context=controversy_context,
        )
        user_msg = f"任务背景：\n{context}\n\n请聚焦评估 {target.agent_name} 的方案。"
        resp = await agent.client.chat(
            messages=[LLMMessage(role="user", content=user_msg)],
            system=system,
            max_tokens=4096,
            temperature=temperature,
        )
        raw_blocks.append(f"## 对 {target.agent_name} 的质疑\n{resp.content}")
        for label, question in _parse_round2_questions(resp.content):
            plan_label = label if label in {"A", "B", "C"} else target.recommended_label
            challenges.append(
                Challenge(
                    from_agent=agent.name,
                    to_agent=target.agent_name,
                    to_plan_label=plan_label,
                    question=question,
                )
            )

    return AgentRound2(
        agent_name=agent.name,
        model=agent.client.model_name(),
        challenges_given=challenges,
        raw_text="\n\n".join(raw_blocks),
    )


def _parse_round2_questions(text: str) -> list[tuple[str, str]]:
    items = re.findall(r"\d+\.\s*(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL)
    if not items:
        items = [text.strip()] if text.strip() else []
    parsed: list[tuple[str, str]] = []
    for it in items:
        m = re.search(r"方案\s*([ABC])", it)
        parsed.append((m.group(1) if m else "", it.strip()))
    return parsed[:3]


def _fill_received_challenges(round2_outputs: list[AgentRound2]) -> None:
    by_agent = {r.agent_name: r for r in round2_outputs}
    for out in round2_outputs:
        for ch in out.challenges_given:
            target = by_agent.get(ch.to_agent)
            if target:
                target.challenges_received.append(ch)


_ROUND3A_SYSTEM = """\
你是一位独立的营销策略师。

另一位策略师在 Round 2 中对你的方案提出了以下质疑：

{challenges_received}

【任务：答辩】
逐一回应每条质疑，选择以下之一：
- 坚持（maintain）：说明质疑不成立或已在方案中考虑
- 修正（revise）：接受质疑，说明如何调整方案使其自洽
- 切换（switch）：承认质疑有效，改推 Round 1 中的另一备选方案

最后明确声明你的最终推荐方案（A/B/C）。
"""


async def _run_round3a(
    agents: list[DebateAgent],
    round1_outputs: list[AgentRound1],
    round2_outputs: list[AgentRound2],
    context: str,
    temperature: float,
) -> list[AgentRound3a]:
    tasks = [_agent_round3a(a, round1_outputs, round2_outputs, context, temperature) for a in agents]
    return list(await asyncio.gather(*tasks))


async def _agent_round3a(
    agent: DebateAgent,
    round1_outputs: list[AgentRound1],
    round2_outputs: list[AgentRound2],
    context: str,
    temperature: float,
) -> AgentRound3a:
    my_r2 = next((r for r in round2_outputs if r.agent_name == agent.name), None)
    received = my_r2.challenges_received if my_r2 else []
    challenge_text = "\n".join(
        f"- 来自 {c.from_agent} 对方案{c.to_plan_label}：{c.question}" for c in received
    ) or "（无）"
    system = _ROUND3A_SYSTEM.format(challenges_received=challenge_text)
    my_round1 = next((r.raw_text for r in round1_outputs if r.agent_name == agent.name), "")
    user_msg = f"任务背景：\n{context}\n\n你的 Round 1 输出：\n{my_round1}"
    resp = await agent.client.chat(
        messages=[LLMMessage(role="user", content=user_msg)],
        system=system,
        max_tokens=8192,
        temperature=temperature,
    )
    final_label = _extract_plan_label(resp.content, default="A")
    response_type = _infer_response_type(resp.content)
    defenses = [
        ProposalDefense(
            plan_label=c.to_plan_label,
            response_type=response_type,
            response_text=resp.content,
        )
        for c in received
    ]
    return AgentRound3a(
        agent_name=agent.name,
        model=agent.client.model_name(),
        defenses=defenses,
        final_plan_label=final_label,
        full_text=resp.content,
    )


_ROUND3B_SYSTEM = """\
你是一位独立的营销策略师。

你在 Round 2 中对另一位策略师的方案提出了质疑。
以下是他们在 Round 3a 中的完整答辩：

{other_agent_round3a_full_text}

【任务：评分】
结合你之前的质疑，对对方的方案 A/B/C 逐一评分（0-10）。

评分对象是「方案内容本身」，不是答辩表现。
评分依据：你的质疑是否被有效回应，方案是否在答辩后仍然可执行。

【输出格式】
## 对方案A的评分
分数：X/10
理由：（1-2句）

## 对方案B的评分
分数：X/10
理由：（1-2句）

## 对方案C的评分
分数：X/10
理由：（1-2句）
"""


async def _run_round3b(
    agents: list[DebateAgent],
    round1_outputs: list[AgentRound1],
    round2_outputs: list[AgentRound2],
    round3a_outputs: list[AgentRound3a],
    context: str,
    temperature: float,
) -> list[AgentRound3b]:
    tasks: list[asyncio.Future] = []
    for agent in agents:
        others = [r for r in round1_outputs if r.agent_name != agent.name]
        for target in others:
            target_r3a = next((x for x in round3a_outputs if x.agent_name == target.agent_name), None)
            target_r2 = next((x for x in round2_outputs if x.agent_name == agent.name), None)
            tasks.append(
                _agent_round3b(
                    scorer=agent,
                    target=target,
                    target_r3a=target_r3a.full_text if target_r3a else "",
                    my_round2=target_r2.raw_text if target_r2 else "",
                    context=context,
                    temperature=temperature,
                )
            )
    return list(await asyncio.gather(*tasks))


async def _agent_round3b(
    scorer: DebateAgent,
    target: AgentRound1,
    target_r3a: str,
    my_round2: str,
    context: str,
    temperature: float,
) -> AgentRound3b:
    system = _ROUND3B_SYSTEM.format(other_agent_round3a_full_text=target_r3a)
    user_msg = (
        f"任务背景：\n{context}\n\n"
        f"你在 Round 2 的质疑：\n{my_round2}\n\n"
        f"被评分方 Round 1 输出：\n{target.raw_text}"
    )
    resp = await scorer.client.chat(
        messages=[LLMMessage(role="user", content=user_msg)],
        system=system,
        max_tokens=4096,
        temperature=temperature,
    )
    return AgentRound3b(
        from_agent=scorer.name,
        to_agent=target.agent_name,
        scores=_parse_round3b_scores(resp.content),
        raw_text=resp.content,
    )


def _parse_round3b_scores(text: str) -> list[ProposalScore]:
    scores: list[ProposalScore] = []
    for label in ["A", "B", "C"]:
        m = re.search(
            rf"##\s*对方案{label}的评分\s*\n.*?分数[：:]\s*(\d+(?:\.\d+)?)[/／]10.*?理由[：:]\s*(.+?)(?=##|\Z)",
            text,
            re.DOTALL,
        )
        if not m:
            continue
        score = min(10.0, max(0.0, float(m.group(1))))
        reason = m.group(2).strip().split("\n")[0]
        scores.append(ProposalScore(plan_label=label, score=score, reason=reason))
    return scores


async def _moderator_quick_check(
    client: BaseLLMClient,
    round1_outputs: list[AgentRound1],
) -> bool:
    summary = "\n\n".join(
        f"【{r.agent_name}】推荐方案{r.recommended_label}：{r.recommended_reason}" for r in round1_outputs
    )
    system = (
        "你是辩论主持人。若各推荐方案高度雷同且无实质分歧，回答 收敛；否则回答 继续。"
        "只回答一个词：收敛 或 继续。"
    )
    try:
        resp = await client.chat(
            messages=[LLMMessage(role="user", content=summary)],
            system=system,
            max_tokens=64,
            temperature=0.0,
        )
        decision = resp.content.strip()
        return decision.startswith("收敛")
    except Exception as exc:
        logger.warning("[AdversarialDebate] quick check failed: %s", exc)
        return False


async def _moderator_decide_continue(
    moderator_client: BaseLLMClient,
    round1_outputs: list[AgentRound1],
    round3a_outputs: list[AgentRound3a],
    round3b_outputs: list[AgentRound3b],
) -> tuple[bool, list[str]]:
    score_map = _compute_plan_avg_scores(round3b_outputs)
    rows = []
    for r1 in round1_outputs:
        for p in r1.proposals:
            rows.append(f"{r1.agent_name}-方案{p.label}: {score_map.get((r1.agent_name, p.label), 0.0):.2f}")
    finals = [f"{r.agent_name} 最终推荐 {r.final_plan_label}" for r in round3a_outputs]
    user_msg = "方案评分：\n" + "\n".join(rows) + "\n\n最终推荐：\n" + "\n".join(finals)
    system = (
        "你是 Moderator。若需要继续，请输出：continue，然后列出 1-3 条争议点编号列表。"
        "若可以收敛，请输出：converge。"
    )
    try:
        resp = await moderator_client.chat(
            messages=[LLMMessage(role="user", content=user_msg)],
            system=system,
            max_tokens=512,
            temperature=0.0,
        )
        text = resp.content.strip()
    except Exception:
        return False, []

    if text.lower().startswith("continue") or text.startswith("继续"):
        points = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|[-*])\s*(.+)", text)
        return True, [p.strip() for p in points[:3] if p.strip()]
    return False, []


async def _moderator_finalize(
    client: BaseLLMClient,
    context: str,
    moderator_system: str,
    round1_outputs: list[AgentRound1],
    round2_outputs: list[AgentRound2],
    round3a_outputs: list[AgentRound3a],
    round3b_outputs: list[AgentRound3b],
) -> tuple[str, SelectedPlanRecord, list[AlternativePlanRecord]]:
    summary = _format_debate_summary(round1_outputs, round2_outputs, round3a_outputs, round3b_outputs)
    strategy_resp = await client.chat(
        messages=[
            LLMMessage(
                role="user",
                content=f"任务背景：\n{context}\n\n辩论记录：\n{summary}\n\n请输出最终策略建议文档。",
            )
        ],
        system=moderator_system or "你是 Moderator，请输出最终策略建议文档。",
        max_tokens=8192,
        temperature=0.0,
    )
    full_text = strategy_resp.content

    plan_scores = _compute_plan_avg_scores(round3b_outputs)
    best_agent, best_label = _pick_best_plan(round1_outputs, round3a_outputs, plan_scores)
    best_proposal = _find_proposal(round1_outputs, best_agent, best_label)
    selected = SelectedPlanRecord(
        source_agent=best_agent,
        source_plan_label=best_label,
        core_claim=best_proposal.core_claim if best_proposal else "",
        selection_reason=f"Round 3b plan score highest: {plan_scores.get((best_agent, best_label), 0.0):.2f}/10",
    )

    alternatives: list[AlternativePlanRecord] = []
    for r1 in round1_outputs:
        for proposal in r1.proposals:
            if r1.agent_name == best_agent and proposal.label == best_label:
                continue
            score = plan_scores.get((r1.agent_name, proposal.label), 0.0)
            reuse = "high" if score >= 7 else "medium" if score >= 4 else "low"
            alternatives.append(
                AlternativePlanRecord(
                    source_agent=r1.agent_name,
                    source_plan_label=proposal.label,
                    core_claim=proposal.core_claim,
                    why_not_selected="Round 3b average score is lower than selected plan",
                    avg_score=score,
                    reuse_potential=reuse,
                )
            )

    return full_text, selected, alternatives


def _compute_plan_avg_scores(round3b_outputs: list[AgentRound3b]) -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], list[float]] = {}
    for out in round3b_outputs:
        for s in out.scores:
            key = (out.to_agent, s.plan_label)
            totals.setdefault(key, []).append(s.score)
    return {k: sum(v) / len(v) for k, v in totals.items() if v}


def _pick_best_plan(
    round1_outputs: list[AgentRound1],
    round3a_outputs: list[AgentRound3a],
    plan_scores: dict[tuple[str, str], float],
) -> tuple[str, str]:
    if plan_scores:
        (agent, label), _score = max(plan_scores.items(), key=lambda kv: kv[1])
        return agent, label

    if round3a_outputs:
        fallback_agent = round3a_outputs[0].agent_name
        return fallback_agent, round3a_outputs[0].final_plan_label

    if round1_outputs:
        return round1_outputs[0].agent_name, round1_outputs[0].recommended_label

    return "unknown", "A"


def _find_proposal(round1_outputs: list[AgentRound1], agent_name: str, label: str) -> PlanProposal | None:
    for r1 in round1_outputs:
        if r1.agent_name != agent_name:
            continue
        for p in r1.proposals:
            if p.label == label:
                return p
    return None


def _format_debate_summary(
    round1_outputs: list[AgentRound1],
    round2_outputs: list[AgentRound2],
    round3a_outputs: list[AgentRound3a],
    round3b_outputs: list[AgentRound3b],
) -> str:
    lines = ["## Round 1"]
    for out in round1_outputs:
        lines.append(f"### {out.agent_name}\n{out.raw_text}")

    if round2_outputs:
        lines.append("\n## Round 2")
        for out in round2_outputs:
            lines.append(f"### {out.agent_name}\n{out.raw_text}")

    if round3a_outputs:
        lines.append("\n## Round 3a")
        for out in round3a_outputs:
            lines.append(f"### {out.agent_name}\n{out.full_text}")

    if round3b_outputs:
        lines.append("\n## Round 3b")
        for out in round3b_outputs:
            lines.append(f"### {out.from_agent} -> {out.to_agent}\n{out.raw_text}")

    return "\n\n".join(lines)


def _extract_field(text: str, keys: list[str]) -> str:
    for key in keys:
        m = re.search(
            rf"-\s*\**{re.escape(key)}\**[：:]\s*(.+?)(?=\n-\s*\S|\Z)",
            text,
            re.DOTALL,
        )
        if m:
            return m.group(1).strip()
    return ""


def _extract_plan_label(text: str, default: str) -> str:
    m = re.search(r"最终推荐方案[：:]\s*\**([ABC])\**", text)
    return m.group(1) if m else default


def _infer_response_type(text: str) -> str:
    if "switch" in text.lower() or "切换" in text or "改推" in text:
        return "switch"
    if "revise" in text.lower() or "修正" in text or "调整" in text:
        return "revise"
    return "maintain"


def _log_search_contexts(log_path: Path | None, agent_contexts: dict[str, str]) -> None:
    if not log_path:
        return
    lines = ["# 策略辩论日志\n", "## 联网搜索结果\n\n"]
    if not agent_contexts:
        lines.append("（未执行）\n\n---\n\n")
    else:
        # Same body for multiple agents (e.g. one shared search) → one log section
        by_body: dict[str, list[str]] = {}
        for agent, text in agent_contexts.items():
            key = text.strip()
            by_body.setdefault(key, []).append(agent)
        for body, agents in by_body.items():
            title = " & ".join(sorted(agents)) if len(agents) > 1 else agents[0]
            lines.append(f"### {title} 搜索摘要\n{body or '（未执行）'}\n\n")
        lines.append("---\n\n")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))


def _log_round1(log_path: Path | None, round1_outputs: list[AgentRound1]) -> None:
    _append_log(log_path, "## Round 1：独立提案\n\n")
    for out in round1_outputs:
        _append_log(log_path, f"### {out.agent_name}（{out.model}）\n{out.raw_text}\n\n")
    _append_log(log_path, "---\n\n")


def _log_round2(log_path: Path | None, cycle: int, round2_outputs: list[AgentRound2]) -> None:
    _append_log(log_path, f"## Round 2：交叉质疑（轮次 {cycle}）\n\n")
    for out in round2_outputs:
        _append_log(log_path, f"### {out.agent_name} 的质疑\n{out.raw_text}\n\n")
    _append_log(log_path, "---\n\n")


def _log_round3a(log_path: Path | None, cycle: int, round3a_outputs: list[AgentRound3a]) -> None:
    _append_log(log_path, f"## Round 3a：答辩（轮次 {cycle}）\n\n")
    for out in round3a_outputs:
        _append_log(log_path, f"### {out.agent_name} 的答辩\n{out.full_text}\n\n")
    _append_log(log_path, "---\n\n")


def _log_round3b(log_path: Path | None, cycle: int, round3b_outputs: list[AgentRound3b]) -> None:
    _append_log(log_path, f"## Round 3b：方案评分（轮次 {cycle}）\n\n")
    for out in round3b_outputs:
        _append_log(log_path, f"### {out.from_agent} 对 {out.to_agent} 的评分\n{out.raw_text}\n\n")
    _append_log(log_path, "---\n\n")


def _log_continue_decision(log_path: Path | None, should_continue: bool, points: list[str]) -> None:
    if should_continue:
        text = "continue\n" + "\n".join(f"- {p}" for p in points) if points else "continue"
    else:
        text = "converge"
    _append_log(log_path, f"## Moderator 轮次决策\n{text}\n\n---\n\n")


def _log_final(log_path: Path | None, final_text: str) -> None:
    _append_log(log_path, f"## Moderator 裁定\n\n{final_text}\n")


def _append_log(log_path: Path | None, content: str) -> None:
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(content)
