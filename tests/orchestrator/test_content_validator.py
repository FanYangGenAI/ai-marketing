"""Unit tests: platform copy hard-rule validation."""

from src.orchestrator.content_validator import (
    CopyViolation,
    enforce_platform_copy,
    validate_platform_copy,
)

_HARD = {
    "title": {"required": True, "max_chars": 20},
    "body": {"required": True, "max_chars": 1000},
}


def test_validate_title_missing():
    v = validate_platform_copy("", "hello", _HARD)
    assert any(x.code == "TITLE_MISSING" for x in v)


def test_validate_title_too_long():
    t = "x" * 21
    v = validate_platform_copy(t, "b" * 10, _HARD)
    assert any(x.code == "TITLE_TOO_LONG" for x in v)


def test_validate_body_too_long():
    b = "y" * 1001
    v = validate_platform_copy("ok", b, _HARD)
    assert any(x.code == "BODY_TOO_LONG" for x in v)


def test_enforce_truncates_and_clears_violations():
    t, b, before, after = enforce_platform_copy(
        "x" * 30,
        "z" * 1200,
        _HARD,
    )
    assert any(v.code == "TITLE_TOO_LONG" for v in before)
    assert any(v.code == "BODY_TOO_LONG" for v in before)
    assert len(t) == 20
    assert len(b) == 1000
    assert after == []


def test_enforce_fills_empty_title():
    t, b, before, after = enforce_platform_copy("", "hello world", _HARD)
    assert any(v.code == "TITLE_MISSING" for v in before)
    assert t
    assert len(t) <= 20
    assert after == []


def test_copy_violation_to_dict():
    v = CopyViolation(code="X", message="m", actual=1, limit=2)
    d = v.to_dict()
    assert d["code"] == "X"
    assert d["limit"] == 2
