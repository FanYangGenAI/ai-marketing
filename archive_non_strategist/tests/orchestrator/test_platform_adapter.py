"""单元测试：PlatformAdapter"""

import pytest

from src.orchestrator.platform_adapter import PlatformAdapter


@pytest.fixture
def adapter() -> PlatformAdapter:
    return PlatformAdapter("xiaohongshu")


def test_load_xiaohongshu_config(adapter):
    assert adapter.platform == "xiaohongshu"
    assert adapter.config is not None


def test_build_spec_prompt_contains_key_sections(adapter):
    prompt = adapter.build_spec_prompt()
    assert "平台硬约束" in prompt
    assert "图片规格" in prompt
    assert "文字规范" in prompt
    assert "20" in prompt          # 标题最多20字


def test_validate_title_empty(adapter):
    issues = adapter.validate_title("   ")
    assert any("缺失" in i for i in issues)


def test_validate_body_empty(adapter):
    issues = adapter.validate_body("")
    assert any("缺失" in i for i in issues)


def test_validate_title_pass(adapter):
    issues = adapter.validate_title("这款产品真的绝了")
    assert issues == []


def test_validate_title_too_long(adapter):
    long_title = "这是一个超过二十个字的标题用来测试字数限制是否正常工作的标题"
    issues = adapter.validate_title(long_title)
    assert any("超长" in i for i in issues)


def test_validate_title_banned_word(adapter):
    issues = adapter.validate_title("最强产品推荐")
    assert any("禁用词" in i for i in issues)


def test_validate_body_too_short(adapter):
    issues = adapter.validate_body("太短了")
    assert any("太短" in i for i in issues)


def test_validate_body_pass(adapter):
    body = "亲测好用！" * 120  # ~600字
    issues = adapter.validate_body(body)
    assert issues == []


def test_validate_hashtags_too_few(adapter):
    issues = adapter.validate_hashtags(["#好物"])
    assert any("太少" in i for i in issues)


def test_validate_hashtags_pass(adapter):
    tags = ["#好物推荐", "#亲测有效", "#种草", "#日常", "#分享"]
    issues = adapter.validate_hashtags(tags)
    assert issues == []


def test_invalid_platform_raises(adapter):
    with pytest.raises(FileNotFoundError):
        PlatformAdapter("nonexistent_platform")
