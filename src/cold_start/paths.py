"""Filesystem layout for cold-start artifacts under a campaign root."""

from pathlib import Path

ATTACHMENTS_SUBDIR = "attachments"
RAW_SUBDIR = "raw"
MANIFEST_NAME = "manifest.json"
UNDERSTANDING_STATE_NAME = "understanding_state.json"
PRODUCT_PROFILE_NAME = "product_profile.json"
PRODUCT_KNOWLEDGE_NAME = "product_knowledge.json"


def attachments_dir(campaign_root: Path) -> Path:
    return campaign_root / ATTACHMENTS_SUBDIR


def attachments_raw_dir(campaign_root: Path) -> Path:
    return attachments_dir(campaign_root) / RAW_SUBDIR


def manifest_path(campaign_root: Path) -> Path:
    return attachments_dir(campaign_root) / MANIFEST_NAME


def understanding_state_path(campaign_root: Path) -> Path:
    return attachments_dir(campaign_root) / UNDERSTANDING_STATE_NAME


def product_profile_path(campaign_root: Path) -> Path:
    return campaign_root / "config" / PRODUCT_PROFILE_NAME


def product_knowledge_path(campaign_root: Path) -> Path:
    return campaign_root / "memory" / PRODUCT_KNOWLEDGE_NAME


def ensure_attachment_dirs(campaign_root: Path) -> None:
    attachments_raw_dir(campaign_root).mkdir(parents=True, exist_ok=True)
