"""
Deterministic validation for platform copy (title/body) against hard_rules.

Character counts use Python len() (Unicode code points), per product spec.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class CopyViolation:
    code: str
    message: str
    actual: str | int | None = None
    limit: str | int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _norm(s: str | None) -> str:
    return (s or "").strip()


def validate_platform_copy(
    title: str | None,
    body: str | None,
    hard_rules: dict,
) -> list[CopyViolation]:
    """Return non-empty list if violations exist."""
    t = _norm(title)
    b = _norm(body)
    tr = hard_rules.get("title", {})
    br = hard_rules.get("body", {})
    t_req = bool(tr.get("required", True))
    t_max = int(tr.get("max_chars", 20))
    b_req = bool(br.get("required", True))
    b_max = int(br.get("max_chars", 1000))

    out: list[CopyViolation] = []
    if t_req and not t:
        out.append(CopyViolation(code="TITLE_MISSING", message="Title is required", actual=0))
    elif t and len(t) > t_max:
        out.append(
            CopyViolation(
                code="TITLE_TOO_LONG",
                message=f"Title exceeds {t_max} characters",
                actual=len(t),
                limit=t_max,
            )
        )

    if b_req and not b:
        out.append(CopyViolation(code="BODY_MISSING", message="Body is required", actual=0))
    elif b and len(b) > b_max:
        out.append(
            CopyViolation(
                code="BODY_TOO_LONG",
                message=f"Body exceeds {b_max} characters",
                actual=len(b),
                limit=b_max,
            )
        )
    return out


def enforce_platform_copy(
    title: str | None,
    body: str | None,
    hard_rules: dict,
    *,
    fallback_title: str = "今日分享",
    fallback_body: str = "（系统占位：正文未生成，请人工补充。）",
) -> tuple[str, str, list[CopyViolation], list[CopyViolation]]:
    """
    Apply deterministic fixes so output satisfies hard_rules.

    Returns: (final_title, final_body, violations_before, violations_after)
    """
    before = validate_platform_copy(title, body, hard_rules)
    tr = hard_rules.get("title", {})
    br = hard_rules.get("body", {})
    t_max = int(tr.get("max_chars", 20))
    b_max = int(br.get("max_chars", 1000))

    t = _norm(title)
    b = _norm(body)

    if not t:
        t = fallback_title[:t_max]
    elif len(t) > t_max:
        t = t[:t_max]

    if not b:
        b = fallback_body
        if len(b) > b_max:
            b = b[:b_max]
    elif len(b) > b_max:
        b = b[:b_max]

    after = validate_platform_copy(t, b, hard_rules)
    return t, b, before, after
