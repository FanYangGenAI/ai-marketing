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
  4. 将素材路径写入 director_task_result.json

模型：Gemini（多模态，理解视觉指令能力强）
输出：
  - {daily_folder}/assets/raw/        — 原始素材
  - {daily_folder}/assets/processed/  — 处理后素材
  - {daily_folder}/director_task_result.json
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

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
  "screenshot_url": "https://...（仅 source=screenshot 时填写）",
  "text_overlay": {"text": "...", "position": "top|bottom"} | null,
  "privacy_mask": [{"x": 0, "y": 0, "w": 100, "h": 50}] | null
}

source 选择规则：
- 如果图片是产品界面截图 → screenshot
- 如果 Asset Library 已有相似素材 → reuse（并填写 reuse_asset_id）
- 其他情况 → generate（调用 AI 图像生成）

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
        result_path = context.daily_folder / "director_task_result.json"
        raw_dir = context.subdir("assets", "raw")
        processed_dir = context.subdir("assets", "processed")

        # ── 读取脚本 ──────────────────────────────────────────────────────────
        script_path = context.daily_folder / "script" / "daily_marketing_script.md"
        script_text = self._read_optional(script_path)

        # ── 读取 Asset Library ────────────────────────────────────────────────
        asset_lib = AssetLibrary(context.asset_library_root)
        asset_summary = self._build_asset_summary(asset_lib)

        # ── 调用 LLM 规划 task_list ──────────────────────────────────────────
        task_list = await self._plan_tasks(script_text, asset_summary)

        # ── 执行每个任务 ──────────────────────────────────────────────────────
        executed: list[dict] = []
        for task in task_list:
            result = await self._execute_task(task, raw_dir, processed_dir, asset_lib, context)
            executed.append(result)

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

    async def _plan_tasks(self, script_text: str, asset_summary: str) -> list[dict]:
        """调用 LLM 解析脚本，输出 task_list JSON。"""
        user_msg = f"""## 营销脚本\n{script_text}

## Asset Library 现有素材摘要\n{asset_summary}

请根据脚本中的「配图列表」章节，为每张图片制定获取方案，输出 task_list JSON 数组。"""

        messages = [LLMMessage(role="user", content=user_msg)]
        response = await self.llm_client.chat(
            messages=messages,
            system=_DIRECTOR_SYSTEM,
            max_tokens=4096,
            temperature=0.3,
        )

        return self._parse_task_list(response.content)

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
        context: AgentContext,
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
                raw_path = await self._run_screenshot(task, raw_dir)
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
            if task.get("text_overlay"):
                ov = task["text_overlay"]
                overlay_path = processed_dir / f"{task_id}_overlay.png"
                self._run_skill(
                    "src/skills/text-overlay/scripts/text_overlay.py",
                    "--input", str(current_path),
                    "--output", str(overlay_path),
                    "--text", ov.get("text", ""),
                    "--position", ov.get("position", "top"),
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
            asset_id = asset_lib.add(
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
            result["asset_id"] = asset_id

        except Exception as e:
            result["error"] = str(e)

        return result

    # ── Skill 调用 ────────────────────────────────────────────────────────────

    async def _run_imagegen(self, task: dict, raw_dir: Path) -> Path:
        output = raw_dir / f"{task['id']}_raw.png"
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "src/skills/gemini-imagegen/scripts/imagegen.py",
            "--prompt", task.get("image_prompt", task.get("description", "")),
            "--output", str(output),
            "--size", self._aspect_to_size(task.get("aspect_ratio", "3:4")),
            "--level", "auto",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"imagegen 失败: {stderr.decode('utf-8', errors='replace')}")
        return output

    async def _run_screenshot(self, task: dict, raw_dir: Path) -> Path:
        url = task.get("screenshot_url", "")
        if not url:
            raise ValueError(f"screenshot 任务缺少 screenshot_url: {task.get('id')}")
        output = raw_dir / f"{task['id']}_raw.png"
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "src/skills/product-screenshot/scripts/screenshot.py",
            "--url", url,
            "--output", str(output),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"screenshot 失败: {stderr.decode('utf-8', errors='replace')}")
        return output

    @staticmethod
    def _resolve_reuse(task: dict, asset_lib: AssetLibrary) -> Path:
        asset_id = task.get("reuse_asset_id", "")
        assets = asset_lib.index.get("assets", [])
        for a in assets:
            if a["id"] == asset_id:
                return Path(asset_lib.root) / a["file"]
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
        assets = asset_lib.index.get("assets", [])
        if not assets:
            return "（Asset Library 暂无历史素材）"
        lines = [f"现有 {len(assets)} 个素材："]
        for a in assets[:20]:  # 最多展示 20 个
            lines.append(
                f"- [{a['id']}] {a.get('asset_type', 'image')} "
                f"tags={a.get('tags', [])} prompt=\"{a.get('prompt', '')[:60]}\""
            )
        return "\n".join(lines)
