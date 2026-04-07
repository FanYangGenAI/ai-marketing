# Strategist Refactor Todo

## Plan

- [x] Refactor `src/orchestrator/adversarial_debate.py` to split Round 3 into 3a and 3b.
- [x] Split temperature config into `round1_temperature` and `discussion_temperature`.
- [x] Add controversy points feedback loop from Moderator to next Round 2.
- [x] Write agent-specific search context into debate log before Round 1.
- [x] Update `src/agents/strategist/strategist.py` for Strategist A/B naming and new params.
- [x] Update `run_strategist.py` with new temperature constants and constructor args.
- [x] Run `python run_strategist.py` and validate generated artifacts.

## Review

- [ ] Verify debate log includes search context, Round 1, Round 2, Round 3a, Round 3b, and Moderator decision. (Current run converged after Round 1 quick check)
- [x] Verify selected plan output and alternative plan memory are both generated.
