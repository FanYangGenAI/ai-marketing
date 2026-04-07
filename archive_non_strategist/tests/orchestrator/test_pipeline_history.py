import json
from datetime import date
from pathlib import Path

import pytest

from src.agents.base import AgentOutput


class _FakeReviser:
    def __init__(self):
        self.calls = 0

    async def run(self, context):
        self.calls += 1
        # first failed audit -> retry from scriptwriter
        if self.calls == 1:
            return AgentOutput(
                output_path=context.daily_folder / "audit" / "revision_plan.json",
                summary="route scriptwriter",
                success=True,
                data={
                    "route_to": "scriptwriter",
                    "retry_count": 1,
                    "revision_instructions": "revise",
                    "requires_human_review": False,
                },
            )
        # second failed audit -> stop
        return AgentOutput(
            output_path=context.daily_folder / "audit" / "human_review_required.json",
            summary="human required",
            success=False,
            data={
                "route_to": None,
                "retry_count": 2,
                "requires_human_review": True,
            },
        )


@pytest.mark.asyncio
async def test_pipeline_writes_run_history_attempts(tmp_path, monkeypatch):
    from src.orchestrator.pipeline import Pipeline

    campaigns_root = tmp_path / "campaigns"
    product = campaigns_root / "Prod"
    (product / "config").mkdir(parents=True)
    (product / "daily").mkdir(parents=True)
    (product / "memory").mkdir(parents=True)
    (product / "config" / "product_config.json").write_text(
        json.dumps({"platform": "xiaohongshu", "user_brief": "u"}), encoding="utf-8"
    )

    pipe = Pipeline(product_name="Prod", campaigns_root=campaigns_root)

    async def fake_run_step(step, context):
        out = context.daily_folder / step / f"{step}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"{step}-{context.attempt_id}", encoding="utf-8")
        if step == "audit":
            return AgentOutput(
                output_path=out,
                summary="audit failed",
                success=False,
                data={"summary_failed": ["title_length"], "attempt_artifacts": [str(out)]},
            )
        return AgentOutput(
            output_path=out,
            summary=f"{step} ok",
            success=True,
            data={"attempt_artifacts": [str(out)]},
        )

    monkeypatch.setattr(pipe, "_init_agents", lambda: None)
    monkeypatch.setattr(pipe, "_run_step", fake_run_step)
    pipe._reviser = _FakeReviser()

    await pipe.run(run_date=date(2026, 3, 23), dry_run=False)

    daily = product / "daily" / "2026-03-23"
    h = json.loads((daily / ".run_history.json").read_text(encoding="utf-8"))
    assert len(h["attempts"]) == 2
    assert h["attempts"][0]["attempt_id"] == "attempt_00"
    assert h["attempts"][1]["attempt_id"] == "attempt_01"
    assert h["attempts"][0]["reviser"]["route_to"] == "scriptwriter"
    assert h["attempts"][1]["reviser"]["requires_human_review"] is True
