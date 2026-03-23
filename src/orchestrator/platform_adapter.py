"""
PlatformAdapter — 平台规范注入器。

读取 src/config/platforms/{platform}.json，
将字数限制、图片规格、禁用词、风格要求
转换为一段结构化文本，注入到 Scriptwriter / Audit 的 LLM 上下文。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator.platform_rules import get_hard_rules_dict


_CONFIG_DIR = Path(__file__).parent.parent / "config" / "platforms"


class PlatformAdapter:
    def __init__(self, platform: str = "xiaohongshu"):
        config_path = _CONFIG_DIR / f"{platform}.json"
        if not config_path.exists():
            raise FileNotFoundError(
                f"平台配置文件未找到: {config_path}\n"
                f"支持的平台: {[p.stem for p in _CONFIG_DIR.glob('*.json')]}"
            )
        with config_path.open(encoding="utf-8") as f:
            self._config: dict = json.load(f)
        self.platform = platform

    @property
    def hard_rules(self) -> dict:
        """Platform-mandatory rules (title/body); not user-overridable."""
        return get_hard_rules_dict(self._config)

    def build_hard_rules_prompt(self) -> str:
        """Short block for Planner / Scriptwriter / Creator context injection."""
        hr = self.hard_rules
        tr = hr.get("title", {})
        br = hr.get("body", {})
        return "\n".join(
            [
                f"## 平台硬约束（{self._config.get('display_name', self.platform)}，不可违反）",
                f"- 标题：必填={tr.get('required', True)}，最多 {int(tr.get('max_chars', 20))} 个字符（len 计数）",
                f"- 正文：必填={br.get('required', True)}，最多 {int(br.get('max_chars', 1000))} 个字符（len 计数）",
                "- 以上约束优先于用户偏好与创意自由度。",
            ]
        )

    # ── 原始配置访问 ──────────────────────────────────────────────────────────

    @property
    def config(self) -> dict:
        return self._config

    @property
    def _specs(self) -> dict:
        """兼容 {specs: {...}} 和扁平结构两种 JSON 格式。"""
        return self._config.get("specs", self._config)

    @property
    def image_spec(self) -> dict:
        specs = self._specs
        img_count = specs.get("image_count", {})
        return {
            "min_count": img_count.get("min", 1),
            "max_count": img_count.get("max", 9),
            "aspect_ratios": specs.get("image_ratio", []),
            "recommended_size": str(specs.get("image_size_px", "未指定")),
        }

    @property
    def text_spec(self) -> dict:
        specs = self._specs
        body = specs.get("body_chars", {})
        tags = specs.get("hashtags", {})
        hr = self.hard_rules
        tmax = int(hr.get("title", {}).get("max_chars", specs.get("title_max_chars", 20)))
        bmax = int(hr.get("body", {}).get("max_chars", body.get("max", 1000)))
        return {
            "title_max_chars": tmax,
            "body_min_chars": body.get("min", 0),
            "body_max_chars": bmax,
            "hashtag_min": tags.get("min", 1),
            "hashtag_max": tags.get("max", 8),
        }

    @property
    def style_guide(self) -> dict:
        return self._config.get("style_guide", {})

    # ── LLM 上下文生成 ─────────────────────────────────────────────────────────

    def build_spec_prompt(self) -> str:
        """
        生成一段结构化的平台规范说明文本，
        直接追加到 Scriptwriter / Audit 的 system prompt 或 user message 末尾。
        """
        img = self.image_spec
        txt = self.text_spec
        sty = self.style_guide

        lines = [
            self.build_hard_rules_prompt(),
            "",
            f"## 平台规范：{self.platform}",
            "",
            "### 图片规格",
            f"- 数量：{img.get('min_count', 1)}–{img.get('max_count', 9)} 张",
            f"- 推荐比例：{', '.join(img.get('aspect_ratios', []))}",
            f"- 推荐尺寸：{img.get('recommended_size', '未指定')}",
            "",
            "### 文字规范",
            f"- 标题：最多 {txt.get('title_max_chars', 20)} 字",
            f"- 正文：{txt.get('body_min_chars', 0)}–{txt.get('body_max_chars', 1000)} 字",
            f"- 话题标签：{txt.get('hashtag_min', 1)}–{txt.get('hashtag_max', 8)} 个",
        ]

        if sty.get("avoid_words"):
            lines += [
                "",
                "### 禁用/敏感词（避免使用）",
                "  " + "、".join(sty["avoid_words"]),
            ]

        _pref = sty.get("preferred_words") or sty.get("prefer_words")
        if _pref:
            lines += [
                "",
                "### 推荐用词（鼓励使用）",
                "  " + "、".join(_pref),
            ]

        if sty.get("tone"):
            lines += ["", f"### 内容调性", f"  {sty['tone']}"]

        return "\n".join(lines)

    def validate_title(self, title: str) -> list[str]:
        """检查标题是否符合规范，返回问题列表（空列表表示通过）。"""
        issues = []
        t = (title or "").strip()
        hr = self.hard_rules.get("title", {})
        if hr.get("required", True) and not t:
            issues.append("标题缺失：必须提供非空标题")
        max_chars = self.text_spec.get("title_max_chars", 20)
        if t and len(t) > max_chars:
            issues.append(f"标题超长：{len(t)} 字 > {max_chars} 字上限")
        for word in self.style_guide.get("avoid_words", []):
            if word in t:
                issues.append(f"标题含禁用词：「{word}」")
        return issues

    def validate_body(self, body: str) -> list[str]:
        """检查正文是否符合规范，返回问题列表。"""
        issues = []
        txt = self.text_spec
        b = (body or "").strip()
        hr = self.hard_rules.get("body", {})
        if hr.get("required", True) and not b:
            issues.append("正文缺失：必须提供非空正文")
        length = len(b)
        if length < txt.get("body_min_chars", 0):
            issues.append(f"正文太短：{length} 字 < {txt['body_min_chars']} 字下限")
        if length > txt.get("body_max_chars", 99999):
            issues.append(f"正文超长：{length} 字 > {txt['body_max_chars']} 字上限")
        for word in self.style_guide.get("avoid_words", []):
            if word in b:
                issues.append(f"正文含禁用词：「{word}」")
        return issues

    def validate_hashtags(self, hashtags: list[str]) -> list[str]:
        """检查话题标签数量是否符合规范，返回问题列表。"""
        issues = []
        txt = self.text_spec
        count = len(hashtags)
        if count < txt.get("hashtag_min", 1):
            issues.append(f"话题标签太少：{count} 个 < {txt['hashtag_min']} 个下限")
        if count > txt.get("hashtag_max", 8):
            issues.append(f"话题标签太多：{count} 个 > {txt['hashtag_max']} 个上限")
        return issues
