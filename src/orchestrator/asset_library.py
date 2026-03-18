"""
Asset Library 管理器
混合索引策略：MD5 哈希精确去重 + JSON 标签索引语义复用。
"""

import hashlib
import json
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class AssetRecord:
    id: str                        # 格式：asset_{hash[:8]}
    hash: str                      # md5:{hex}
    type: str                      # "image" | "video"
    file: str                      # 相对于 asset_library/ 的路径
    size: str                      # 如 "1080x1440"
    created_at: str                # ISO date
    source: str                    # "gemini_web" | "gemini_cli" | "gemini_api" | "screenshot"
    prompt: str                    # 生成时的 prompt（截图则为 URL）
    tags: list[str] = field(default_factory=list)
    platform: str = "xiaohongshu"
    used_in: list[str] = field(default_factory=list)  # 哪些 daily output 用了此素材
    reuse_count: int = 0


@dataclass
class AssetLibraryIndex:
    version: str = "1.0"
    assets: list[AssetRecord] = field(default_factory=list)


# ── 主类 ──────────────────────────────────────────────────────────────────────

class AssetLibrary:
    """
    管理 campaigns/{product}/asset_library/ 目录下的所有素材。
    线程安全：所有写操作会立即持久化到 index.json。
    """

    def __init__(self, library_root: str):
        """
        Args:
            library_root: campaigns/{product}/asset_library/ 的绝对路径
        """
        self.root = Path(library_root)
        self.images_dir = self.root / "images"
        self.videos_dir = self.root / "videos"
        self.index_path = self.root / "index.json"

        self.root.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(exist_ok=True)
        self.videos_dir.mkdir(exist_ok=True)

        self._index = self._load_index()

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def find_by_hash(self, file_path: str) -> AssetRecord | None:
        """精确查重：计算文件 MD5，返回已存在的记录（无则返回 None）。"""
        h = self._md5(file_path)
        return next(
            (a for a in self._index.assets if a.hash == f"md5:{h}"), None
        )

    def find_by_tags(self, tags: list[str], asset_type: str = "image") -> list[AssetRecord]:
        """标签检索：返回包含所有指定标签的素材列表。"""
        tag_set = set(tags)
        return [
            a for a in self._index.assets
            if a.type == asset_type and tag_set.issubset(set(a.tags))
        ]

    def get_by_id(self, asset_id: str) -> AssetRecord | None:
        """按 ID 获取素材记录。"""
        return next(
            (a for a in self._index.assets if a.id == asset_id), None
        )

    def get_full_path(self, record: AssetRecord) -> str:
        """返回素材的完整绝对路径。"""
        return str(self.root / record.file)

    # ── 入库 ──────────────────────────────────────────────────────────────────

    def add(
        self,
        file_path: str,
        source: str,
        prompt: str = "",
        tags: list[str] | None = None,
        size: str = "",
        platform: str = "xiaohongshu",
        asset_type: str = "image",
    ) -> AssetRecord:
        """
        将新素材加入 Asset Library。
        如果文件 hash 已存在，直接返回已有记录（不重复存储）。

        Args:
            file_path:  原始文件路径（生成/截图后的临时路径）
            source:     生成来源
            prompt:     生成 prompt 或截图 URL
            tags:       标签列表
            size:       尺寸字符串，如 "1080x1440"
            platform:   目标平台
            asset_type: "image" | "video"

        Returns:
            AssetRecord（新建或已有）
        """
        # 精确去重
        existing = self.find_by_hash(file_path)
        if existing:
            return existing

        h = self._md5(file_path)
        suffix = Path(file_path).suffix
        sub_dir = self.images_dir if asset_type == "image" else self.videos_dir
        dest_name = f"{h}{suffix}"
        dest_path = sub_dir / dest_name
        relative_path = str(dest_path.relative_to(self.root))

        # 复制文件到 library 目录（以 hash 命名，确保唯一）
        shutil.copy2(file_path, dest_path)

        record = AssetRecord(
            id=f"asset_{h[:8]}",
            hash=f"md5:{h}",
            type=asset_type,
            file=relative_path,
            size=size,
            created_at=datetime.now().strftime("%Y-%m-%d"),
            source=source,
            prompt=prompt,
            tags=tags or [],
            platform=platform,
        )
        self._index.assets.append(record)
        self._save_index()
        return record

    def mark_used(self, asset_id: str, daily_output_path: str) -> None:
        """记录某个素材被哪个 daily output 使用了。"""
        record = self.get_by_id(asset_id)
        if record and daily_output_path not in record.used_in:
            record.used_in.append(daily_output_path)
            record.reuse_count += 1
            self._save_index()

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _load_index(self) -> AssetLibraryIndex:
        if self.index_path.exists():
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            assets = [AssetRecord(**a) for a in data.get("assets", [])]
            return AssetLibraryIndex(version=data.get("version", "1.0"), assets=assets)
        return AssetLibraryIndex()

    def _save_index(self) -> None:
        data = {
            "version": self._index.version,
            "assets": [asdict(a) for a in self._index.assets],
        }
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _md5(file_path: str) -> str:
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
