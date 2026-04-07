"""单元测试：Pipeline 步骤顺序 + Strategist 集成"""

import pytest
from src.orchestrator.pipeline import STEPS


def test_strategist_is_first_step():
    """Strategist 必须是 Pipeline 的第一个步骤。"""
    assert STEPS[0] == "strategist"


def test_pipeline_has_six_steps():
    """Pipeline 应包含 6 个步骤（含 Strategist）。"""
    assert len(STEPS) == 6


def test_pipeline_step_order():
    """Pipeline 步骤顺序必须是固定的。"""
    expected = ["strategist", "planner", "scriptwriter", "director", "creator", "audit"]
    assert STEPS == expected


def test_audit_is_last_step():
    """Audit 必须是最后一个步骤。"""
    assert STEPS[-1] == "audit"


# ── LessonMemory 双向信号测试 ──────────────────────────────────────────────────

class TestLessonMemoryBidirectional:
    """测试 LessonMemory 双向信号功能。"""

    def test_write_acceptance_creates_positive_lesson(self, tmp_path):
        """write_acceptance 应写入 signal=positive 的 lesson。"""
        from src.orchestrator.lesson_memory import LessonMemory

        lm = LessonMemory(tmp_path, "xiaohongshu")
        lm.write_acceptance(title="测试标题", theme="产品体验", note="很好")

        lessons = lm.load()
        assert len(lessons) == 1
        assert lessons[0]["signal"] == "positive"
        assert lessons[0]["source"] == "user_acceptance"
        assert lessons[0]["title"] == "测试标题"

    def test_write_rejection_creates_negative_lesson(self, tmp_path):
        """write_rejection 应写入 signal=negative 的 lesson。"""
        from src.orchestrator.lesson_memory import LessonMemory

        lm = LessonMemory(tmp_path, "xiaohongshu")
        lm.write_rejection(reason="标题太商业化")

        lessons = lm.load()
        assert len(lessons) == 1
        assert lessons[0]["signal"] == "negative"
        assert lessons[0]["source"] == "user_rejection"
        assert "标题太商业化" in lessons[0]["rule"]

    def test_inject_prompt_shows_both_signals(self, tmp_path):
        """inject_prompt 应同时显示正向和负向信号。"""
        from src.orchestrator.lesson_memory import LessonMemory

        lm = LessonMemory(tmp_path, "xiaohongshu")
        lm.write_acceptance(title="好标题", theme="功能体验", note="用户喜欢")
        lm.write_rejection(reason="太广告")

        prompt = lm.inject_prompt()
        assert "成功经验参考" in prompt
        assert "需要避免的规则" in prompt

    def test_write_rejection_empty_reason_skipped(self, tmp_path):
        """write_rejection 空原因时不写入。"""
        from src.orchestrator.lesson_memory import LessonMemory

        lm = LessonMemory(tmp_path, "xiaohongshu")
        lm.write_rejection(reason="")

        lessons = lm.load()
        assert len(lessons) == 0

    def test_rejection_same_day_increments_fail_count(self, tmp_path):
        """同一天重复拒绝应累计 fail_count。"""
        from src.orchestrator.lesson_memory import LessonMemory

        lm = LessonMemory(tmp_path, "xiaohongshu")
        lm.write_rejection(reason="第一次拒绝")
        lm.write_rejection(reason="第二次拒绝（同天 key 相同）")

        lessons = lm.load()
        # Same-day rejection key, so should be merged
        rejection_lessons = [l for l in lessons if l.get("source") == "user_rejection"]
        assert len(rejection_lessons) == 1
        assert rejection_lessons[0]["fail_count"] == 2

    def test_inject_prompt_empty_when_no_lessons(self, tmp_path):
        """无 lessons 时 inject_prompt 应返回空字符串。"""
        from src.orchestrator.lesson_memory import LessonMemory

        lm = LessonMemory(tmp_path, "xiaohongshu")
        assert lm.inject_prompt() == ""


# ── AgentContext 字段测试 ───────────────────────────────────────────────────────

class TestAgentContextFields:
    """测试 AgentContext 的新字段。"""

    def test_user_brief_default_empty(self, tmp_path):
        """user_brief 默认应为空字符串。"""
        from datetime import date
        from src.agents.base import AgentContext

        ctx = AgentContext(
            campaign_root=tmp_path,
            daily_folder=tmp_path,
            run_date=date.today(),
            product_name="Test",
        )
        assert ctx.user_brief == ""

    def test_suppress_version_in_copy_default_true(self, tmp_path):
        """suppress_version_in_copy 默认应为 True。"""
        from datetime import date
        from src.agents.base import AgentContext

        ctx = AgentContext(
            campaign_root=tmp_path,
            daily_folder=tmp_path,
            run_date=date.today(),
            product_name="Test",
        )
        assert ctx.suppress_version_in_copy is True

    def test_user_brief_can_be_set(self, tmp_path):
        """user_brief 可以被正确赋值。"""
        from datetime import date
        from src.agents.base import AgentContext

        ctx = AgentContext(
            campaign_root=tmp_path,
            daily_folder=tmp_path,
            run_date=date.today(),
            product_name="Test",
            user_brief="产品描述",
        )
        assert ctx.user_brief == "产品描述"

    def test_attempt_id_default_and_custom(self, tmp_path):
        """attempt_id 默认为 attempt_00，且支持通过 extra 覆盖。"""
        from datetime import date
        from src.agents.base import AgentContext

        ctx = AgentContext(
            campaign_root=tmp_path,
            daily_folder=tmp_path,
            run_date=date.today(),
            product_name="Test",
        )
        assert ctx.attempt_id == "attempt_00"

        ctx2 = AgentContext(
            campaign_root=tmp_path,
            daily_folder=tmp_path,
            run_date=date.today(),
            product_name="Test",
            extra={"attempt_id": "attempt_07"},
        )
        assert ctx2.attempt_id == "attempt_07"
        p = ctx2.stage_attempt_dir("scriptwriter")
        assert p.exists()
        assert "attempt_07" in str(p)
