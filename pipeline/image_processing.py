from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .formatters import sanitize_filename


MAX_IMAGE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ImageSpec:
    platform: str
    usage: str
    width: int
    height: int


IMAGE_SPECS = [
    ImageSpec("official_account", "cover", 1080, 608),
    ImageSpec("official_account", "inline", 1080, 608),
    ImageSpec("xiaohongshu", "cover", 1080, 1920),
    ImageSpec("xiaohongshu", "square", 1080, 1080),
    ImageSpec("zhihu", "cover", 1080, 608),
    ImageSpec("toutiao", "cover", 1080, 608),
    ImageSpec("shipinhao", "cover", 1080, 1920),
]


def specs_for_platforms(platforms: list[str]) -> list[ImageSpec]:
    selected = set(platforms)
    return [spec for spec in IMAGE_SPECS if spec.platform in selected]


def center_crop_box(width: int, height: int, target_ratio: float) -> tuple[int, int, int, int]:
    current_ratio = width / height
    if current_ratio > target_ratio:
        new_width = int(height * target_ratio)
        left = (width - new_width) // 2
        return left, 0, left + new_width, height
    new_height = int(width / target_ratio)
    top = (height - new_height) // 2
    return 0, top, width, top + new_height


def save_jpeg_under_limit(image, output_path: Path, max_bytes: int = MAX_IMAGE_BYTES) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    quality = 92
    while quality >= 55:
        image.save(output_path, format="JPEG", quality=quality, optimize=True, progressive=True)
        size = output_path.stat().st_size
        if size <= max_bytes:
            return size
        quality -= 7
    image.save(output_path, format="JPEG", quality=55, optimize=True)
    return output_path.stat().st_size


def process_image(original_path: Path, output_root: Path, topic: str, platforms: list[str]) -> list[dict[str, Any]]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("图片处理需要安装 Pillow") from exc

    topic_slug = sanitize_filename(topic or "未命名选题", 50)
    date_dir = datetime.now().strftime("%Y-%m-%d")
    variants: list[dict[str, Any]] = []

    with Image.open(original_path) as opened:
        base_image = ImageOps.exif_transpose(opened).convert("RGB")
        for spec in specs_for_platforms(platforms):
            crop_box = center_crop_box(base_image.width, base_image.height, spec.width / spec.height)
            variant = base_image.crop(crop_box).resize((spec.width, spec.height))
            file_name = f"{platform_label(spec.platform)}-{usage_label(spec.usage)}.jpg"
            output_path = output_root / date_dir / topic_slug / spec.platform / file_name
            file_size = save_jpeg_under_limit(variant, output_path)
            variants.append(
                {
                    "platform": spec.platform,
                    "usage": spec.usage,
                    "width": spec.width,
                    "height": spec.height,
                    "output_path": str(output_path.resolve()),
                    "file_size": file_size,
                }
            )
    return variants


def platform_label(platform: str) -> str:
    return {
        "official_account": "公众号",
        "xiaohongshu": "小红书",
        "zhihu": "知乎",
        "toutiao": "头条",
        "shipinhao": "视频号",
    }.get(platform, platform)


def usage_label(usage: str) -> str:
    return {
        "cover": "封面",
        "inline": "内文图",
        "square": "方图",
    }.get(usage, usage)
