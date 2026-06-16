from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


SUPPORTED_PLATFORMS = {"xiaohongshu", "zhihu", "official_account"}
DEFAULT_PLATFORMS = ["xiaohongshu", "zhihu", "official_account"]


@dataclass(frozen=True)
class MaterialInput:
    title_hint: str
    raw_content: str
    keywords: list[str]
    target_platforms: list[str]
    image_paths: list[str]
    source_type: str = "manual"
    source_ref: str = ""


@dataclass(frozen=True)
class ArticleDraft:
    platform: str
    title: str
    content: str
    content_format: str = "text"


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().lstrip("#") for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip().lstrip("#") for item in value.split(",") if item.strip()]
    return [str(value).strip()] if str(value).strip() else []


def normalize_material(payload: dict[str, Any]) -> MaterialInput:
    if not isinstance(payload, dict):
        raise ValueError("素材必须是 JSON 对象")

    title_hint = str(payload.get("title_hint") or payload.get("title") or "").strip()
    raw_content = str(payload.get("raw_content") or payload.get("content") or "").strip()
    if not title_hint:
        raise ValueError("缺少 title_hint")
    if not raw_content:
        raise ValueError("缺少 raw_content")

    platforms = normalize_list(payload.get("target_platforms")) or DEFAULT_PLATFORMS
    invalid = [platform for platform in platforms if platform not in SUPPORTED_PLATFORMS]
    if invalid:
        raise ValueError(f"不支持的平台：{', '.join(invalid)}")

    return MaterialInput(
        title_hint=title_hint,
        raw_content=raw_content,
        keywords=normalize_list(payload.get("keywords")),
        target_platforms=platforms,
        image_paths=normalize_list(payload.get("image_paths")),
        source_type=str(payload.get("source_type") or "manual").strip(),
        source_ref=str(payload.get("source_ref") or "").strip(),
    )


def dumps_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def loads_list(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []

