"""Central temperature defaults for pipeline agents (see docs/llm-clients-config-refactor-v1.md)."""

# Debate (Strategist + Planner): stable planning
DEBATE_STRATEGIST_PLANNER: float = 0.0

# Debate (Scriptwriter) + single-call creative agents
CREATIVE_SCRIPT_DIRECTOR_CREATOR: float = 0.7

# Audit (text + visual structured)
AUDIT: float = 0.0

# Reviser routing / instructions (low drift)
REVISER: float = 0.2
