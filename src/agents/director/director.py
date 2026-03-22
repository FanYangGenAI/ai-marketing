"""
Director Agent — 素材编排团队。

职责：
  1. 读取 daily_marketing_script.md，提取配图列表
  2. 查询 Asset Library，检查是否有可复用素材
  3. 对每张需要生成的图片，依次调用 Skills：
     - gemini-imagegen（生成）
     - product-screenshot（截图）
     - crop-resize（裁剪至平台规格）
     - text-overlay（叠加文字，可选）
     - privacy-mask（隐私遮挡，可选）
  4. 将素材路径写入 director/director_task_result.json

模型：Gemini（多模态，理解视觉指令能力强）
输出：
  - {daily_folder}/director/director_raw.md          — LLM 原始规划日志
  - {daily_folder}/director/director_task_result.json — 任务执行结果
  - {daily_folder}/assets/raw/                       — 原始素材
  - {daily_folder}/assets/processed/                 — 处理后素材
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from src.agents.base import AgentContext, AgentOutput, BaseAgent
from src.llm.base import BaseLLMClient, LLMMessage
from src.orchestrator.asset_library import AssetLibrary


_DIRECTOR_SYSTEM = """你是一名内容素材导演（Director）。
你将读取一份营销脚本，其中包含配图列表（序号、画面描述、Image Prompt、尺寸）。
你的任务是为每张图片制定获取方案，并以 JSON 格式输出 task_list。

task_list 中每个任务的格式如下：
{
  "id": "img_01",
  "description": "画面描述（中文）",
  "image_prompt": "Image Prompt（English）",
  "aspect_ratio": "3:4",
  "source": "generate" | "screenshot" | "reuse",
  "reuse_asset_id": "asset_xxx（仅 source=reuse 时填写）",
  "account": "zh" | "en" | null,
  "actions": [...] | null,
  "text_overlay": {"text": "...", "position": "top|bottom"} | null,
  "privacy_mask": [{"x": 0, "y": 0, "w": 100, "h": 50}] | null
}

source 选择规则：
- 如果图片是产品界面截图 → screenshot（需填写 account 和 actions）
- 如果 Asset Library 已有相似素材 → reuse（并填写 reuse_asset_id）
- 其他情况 → generate（调用 AI 图像生成）

account 选择规则（仅 source=screenshot 时有效）：
- 内容面向中文用户 / 展示中文界面 → "zh"
- 内容面向英文用户 / 展示英文界面 → "en"

actions 格式（描述截图前需要执行的操作序列）：
[
  {"type": "navigate", "url": "/path/to/page"},
  {"type": "click", "selector": "CSS选择器"},
  {"type": "fill", "selector": "CSS选择器", "value": "填入内容"},
  {"type": "wait_for", "selector": "CSS选择器"},
  {"type": "wait_ms", "ms": 1000},
  {"type": "screenshot", "selector": "截图区域CSS选择器（省略则全页）"}
]

注意：如果图片包含中文文字，请不要在 image_prompt 中包含中文文字内容，
而是用 text_overlay 字段叠加，避免 AI 生成模型的中文字体渲染问题。

请只输出 JSON 数组，不要有其他内容。"""


class DirectorAgent(BaseAgent):
    """
    Director Agent：解析脚本 → 规划素材任务 → 调用 Skills → 返回素材清单。
    """

    def __init__(self, gemini_client: BaseLLMClient, platform: str = "xiaohongshu"):
        super().__init__(
            name="Director",
            llm_client=gemini_client,
            role_description="素材编排导演，调用 Skills 生成和处理图片素材",
        )
        self.platform = platform

    async def run(self, context: AgentContext) -> AgentOutput:
        director_dir = context.subdir("director")
        result_path = director_dir / "director_task_result.json"
        log_path = director_dir / "director_raw.md"
        raw_dir = context.subdir("assets", "raw")
        processed_dir = context.subdir("assets", "processed")

        # ── 读取脚本 ──────────────────────────────────────────────────────────
        script_path = context.daily_folder / "script" / "daily_marketing_script.md"
        script_text = self._read_optional(script_path)

        # ── 读取 Asset Library ────────────────────────────────────────────────
        asset_lib = AssetLibrary(context.asset_library_root)
        asset_summary = self._build_asset_summary(asset_lib)

        # ── 调用 LLM 规划 task_list ──────────────────────────────────────────
        task_list, llm_raw = await self._plan_tasks(script_text, asset_summary)
        self._write_plan_log(log_path, script_text, asset_summary, llm_raw, task_list)

        # ── 执行每个任务 ──────────────────────────────────────────────────────
        executed: list[dict] = []
        for task in task_list:
            result = await self._execute_task(task, raw_dir, processed_dir, asset_lib, context.campaign_root)
            executed.append(result)
            self._append_task_log(log_path, result)

        # ── 写入结果 ──────────────────────────────────────────────────────────
        self._write_json(result_path, executed)

        success_count = sum(1 for t in executed if t.get("success"))
        summary = f"素材编排完成：{success_count}/{len(executed)} 张成功"

        return AgentOutput(
            output_path=result_path,
            summary=summary,
            data={"tasks": executed},
        )

    # ── 规划 ─────────────────────────────────────────────────────────────────

    async def _plan_tasks(self, script_text: str, asset_summary: str) -> tuple[list[dict], str]:
        """调用 LLM 解析脚本，输出 task_list JSON。返回 (task_list, 原始响应)。"""
        user_msg = f"""## 营销脚本\n{script_text}

## Asset Library 现有素材摘要\n{asset_summary}

请根据脚本中的「配图列表」章节，为每张图片制定获取方案，输出 task_list JSON 数组。"""

        messages = [LLMMessage(role="user", content=user_msg)]
        response = await self.llm_client.chat(
            messages=messages,
            system=_DIRECTOR_SYSTEM,
            max_tokens=16000,
            temperature=0.3,
        )

        return self._parse_task_list(response.content), response.content

    @staticmethod
    def _parse_task_list(content: str) -> list[dict]:
        """从 LLM 响应中提取 JSON 数组。"""
        # 尝试提取 markdown 代码块或裸 JSON
        m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
        if m:
            json_str = m.group(1)
        else:
            # 尝试直接解析
            start = content.find("[")
            end = content.rfind("]")
            if start == -1 or end == -1:
                return []
            json_str = content[start:end + 1]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return []

    # ── 执行 ─────────────────────────────────────────────────────────────────

    async def _execute_task(
        self,
        task: dict,
        raw_dir: Path,
        processed_dir: Path,
        asset_lib: AssetLibrary,
        campaign_root: Path,
    ) -> dict:
        task_id = task.get("id", "img_unknown")
        source = task.get("source", "generate")
        aspect = task.get("aspect_ratio", "3:4")
        result = {**task, "success": False, "final_path": None, "error": None}

        try:
            # Step 1：获取原始图片
            if source == "reuse":
                raw_path = self._resolve_reuse(task, asset_lib)
            elif source == "screenshot":
                try:
                    raw_path = await self._run_screenshot(task, raw_dir, campaign_root)
                except Exception as screenshot_err:
                    # screenshot 失败（selector 不存在、页面未加载等）→ 降级为 AI 生成
                    logger.warning(f"{task_id}: screenshot 失败，降级为 generate: {screenshot_err}")
                    raw_path = await self._run_imagegen(task, raw_dir)
            else:  # generate
                raw_path = await self._run_imagegen(task, raw_dir)

            # Step 2：裁剪缩放
            processed_path = processed_dir / f"{task_id}_cropped.png"
            self._run_skill(
                "src/skills/crop-resize/scripts/crop_resize.py",
                "--input", str(raw_path),
                "--output", str(processed_path),
                "--size", self._aspect_to_size(aspect),
                "--mode", "center",
            )

            current_path = processed_path

            # Step 3：文字叠加（可选）
            text_overlay = task.get("text_overlay")
            # LLM 有时返回列表，取第一个元素
            if isinstance(text_overlay, list):
                text_overlay = text_overlay[0] if text_overlay else None
            if text_overlay and isinstance(text_overlay, dict):
                ov = text_overlay
                overlay_path = processed_dir / f"{task_id}_overlay.png"
                self._run_skill(
                    "src/skills/text-overlay/scripts/text_overlay.py",
                    "--input", str(current_path),
                    "--output", str(overlay_path),
                    "--text", ov.get("text", ""),
                    "--position", ov.get("position") or "top",
                )
                current_path = overlay_path

            # Step 4：隐私遮挡（可选）
            if task.get("privacy_mask"):
                regions = task["privacy_mask"]
                masked_path = processed_dir / f"{task_id}_masked.png"
                region_args = [f"{r['x']},{r['y']},{r['w']},{r['h']}" for r in regions]
                self._run_skill(
                    "src/skills/privacy-mask/scripts/privacy_mask.py",
                    "--input", str(current_path),
                    "--output", str(masked_path),
                    "--regions", *region_args,
                )
                current_path = masked_path

            # Step 5：入库
            record = asset_lib.add(
                file_path=current_path,
                source=source,
                prompt=task.get("image_prompt", ""),
                tags=[task_id, source, aspect],
                size=self._aspect_to_size(aspect),
                platform=self.platform,
                asset_type="image",
            )

            result["success"] = True
            result["final_path"] = str(current_path)
            result["asset_id"] = record.id

        except Exception as e:
            import traceback
            result["error"] = str(e)
            logger.error(f"{task_id} 失败: {e}\n{traceback.format_exc()}")

        return result

    # ── Skill 调用 ────────────────────────────────────────────────────────────

    async def _run_imagegen(self, task: dict, raw_dir: Path) -> Path:
        output = raw_dir / f"{task['id']}_raw.png"
        prompt = task.get("image_prompt") or task.get("description", "")
        aspect_ratio = task.get("aspect_ratio", "3:4")
        return await self.llm_client.generate_image(prompt, output, aspect_ratio)

    async def _run_screenshot(self, task: dict, raw_dir: Path, campaign_root: Path) -> Path:
        output = raw_dir / f"{task['id']}_raw.png"
        account = task.get("account") or "zh"
        actions = task.get("actions")
        base_url = __import__("os").environ.get("PRODUCT_LOGIN_URL", "")

        # 确保 auth state 存在（不存在则自动调用 product-login Skill 登录）
        auth_state_path = campaign_root / "config" / f"auth_state_{account}.json"
        if not auth_state_path.exists():
            await self._run_login(account, auth_state_path, campaign_root)

        cmd = [
            sys.executable,
            "src/skills/product-screenshot/scripts/screenshot.py",
            "--output", str(output),
            "--auth-state", str(auth_state_path),
            "--base-url", base_url,
        ]

        if actions:
            cmd += ["--actions", json.dumps(actions, ensure_ascii=False)]
        else:
            url = task.get("screenshot_url", base_url)
            cmd += ["--url", url]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"screenshot 失败: {stderr.decode('utf-8', errors='replace')}")
        return output

    async def _run_login(self, account: str, auth_state_path: Path, campaign_root: Path) -> None:
        """调用 product-login Skill 登录并保存 auth state。"""
        login_config = campaign_root / "config" / "login_config.json"
        cmd = [
            sys.executable,
            "src/skills/product-login/scripts/login.py",
            "--account", account,
            "--auth-state", str(auth_state_path),
        ]
        if login_config.exists():
            cmd += ["--login-config", str(login_config)]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        if out:
            logger.info(out.strip())
        if proc.returncode != 0:
            raise RuntimeError(f"product-login 失败（account={account}）:\n{err}")

    @staticmethod
    def _resolve_reuse(task: dict, asset_lib: AssetLibrary) -> Path:
        asset_id = task.get("reuse_asset_id", "")
        record = asset_lib.get_by_id(asset_id)
        if record:
            return Path(asset_lib.get_full_path(record))
        raise FileNotFoundError(f"Asset Library 中未找到 asset_id: {asset_id}")

    @staticmethod
    def _run_skill(script: str, *args: str) -> None:
        """同步调用 Skill 脚本。"""
        cmd = [sys.executable, script, *args]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        if res.returncode != 0:
            raise RuntimeError(f"{script} 失败: {res.stderr}")

    @staticmethod
    def _aspect_to_size(aspect: str) -> str:
        mapping = {
            "3:4": "1080x1440",
            "1:1": "1080x1080",
            "9:16": "1080x1920",
            "4:3": "1440x1080",
            "16:9": "1920x1080",
        }
        return mapping.get(aspect, "1080x1440")

    @staticmethod
    def _build_asset_summary(asset_lib: AssetLibrary) -> str:
        assets = asset_lib._index.assets
        if not assets:
            return "（Asset Library 暂无历史素材）"
        lines = [f"现有 {len(assets)} 个素材："]
        for a in assets[:20]:  # 最多展示 20 个
            lines.append(
                f"- [{a.id}] {a.type} tags={a.tags} prompt=\"{a.prompt[:60]}\""
            )
        return "\n".join(lines)

    @staticmethod
    def _write_plan_log(
        log_path: Path,
        script_text: str,
        asset_summary: str,
        llm_raw: str,
        task_list: list[dict],
    ) -> None:
        """写入 LLM 规划阶段的输入输出。"""
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("# Director 原始输出日志\n\n")
            f.write("## 规划阶段\n\n")
            f.write("### 输入：脚本\n\n")
            f.write(script_text or "（无脚本）")
            f.write("\n\n### 输入：Asset Library 摘要\n\n")
            f.write(asset_summary)
            f.write("\n\n### LLM 原始输出\n\n")
            f.write(llm_raw)
            f.write("\n\n### 解析后 task_list\n\n```json\n")
            f.write(json.dumps(task_list, ensure_ascii=False, indent=2))
            f.write("\n```\n\n---\n\n")
            f.write("## 任务执行\n\n")

    @staticmethod
    def _append_task_log(log_path: Path, result: dict) -> None:
        """将单个任务的执行结果追加写入日志。"""
        task_id = result.get("id", "unknown")
        source = result.get("source", "?")
        success = result.get("success", False)
        status = "✅" if success else "❌"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"### {status} {task_id}  `{source}`\n\n")
            if result.get("description"):
                f.write(f"**描述**：{result['description']}\n\n")
            if result.get("image_prompt"):
                f.write(f"**Image Prompt**：{result['image_prompt']}\n\n")
            if success:
                f.write(f"**最终路径**：`{result.get('final_path')}`\n\n")
                f.write(f"**Asset ID**：`{result.get('asset_id')}`\n\n")
            else:
                f.write(f"**错误**：{result.get('error')}\n\n")
            f.write("---\n\n")
