from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import AppConfig
from .schemas import MaterialInput


CATEGORY_LABELS = {
    "TALENT": "人才招聘/求职",
    "TECH_SERVICE": "技术服务",
    "BUILDING": "楼宇空间",
    "GOODS": "商品资源",
    "SERVICE": "服务资源",
}

TYPE_LABELS = {
    "SUPPLY": "供应",
    "DEMAND": "需求",
}


def build_external_database_url(config: AppConfig) -> str:
    if config.external_database_url:
        return config.external_database_url

    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    password = quote_plus(os.getenv("DB_PASSWORD", ""))
    database = os.getenv("DB_NAME", "operation_agent")
    charset = os.getenv("DB_CHARSET", "utf8mb4")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"


def create_external_engine(config: AppConfig) -> Engine:
    return create_engine(build_external_database_url(config), pool_pre_ping=True, pool_recycle=3600)


def parse_json_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def normalize_image_paths(cover_image: Any, images: Any) -> list[str]:
    paths: list[str] = []
    if cover_image:
        paths.append(str(cover_image))

    parsed_images = parse_json_value(images)
    if isinstance(parsed_images, list):
        paths.extend(str(item) for item in parsed_images if item)
    elif parsed_images:
        paths.append(str(parsed_images))

    return list(dict.fromkeys(paths))


def format_json_block(value: Any) -> str:
    parsed = parse_json_value(value)
    if not parsed:
        return ""
    if isinstance(parsed, str):
        return parsed
    return json.dumps(parsed, ensure_ascii=False)


def format_created_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value or "")


def fetch_recent_materials(config: AppConfig, limit: int = 5) -> list[MaterialInput]:
    limit = max(1, min(int(limit or 5), 20))
    engine = create_external_engine(config)
    sql = text(
        """
        SELECT
            s.supply_demand_id AS id,
            s.title,
            s.type,
            s.category,
            s.description,
            s.cover_image,
            s.images,
            s.address,
            s.contact_name,
            s.contact_phone,
            s.price,
            s.price_unit,
            s.extra_fields,
            s.create_time AS created_at,
            s.update_time AS updated_at,
            u.nickname AS publisher_name
        FROM t_supply_demand AS s
        LEFT JOIN t_c_user AS u
          ON u.user_id = s.publisher_id
         AND u.deleted_flag = 0
        WHERE s.status = 'PUBLISHED'
          AND s.deleted_flag = 0
        ORDER BY s.create_time DESC
        LIMIT :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).mappings().all()

    materials: list[MaterialInput] = []
    for row in rows:
        demand_type = str(row["type"] or "")
        category = str(row["category"] or "")
        type_label = TYPE_LABELS.get(demand_type, demand_type or "供需")
        category_label = CATEGORY_LABELS.get(category, category or "其他")
        title = str(row["title"] or "未命名供需信息")
        extra_fields = format_json_block(row["extra_fields"])

        content_lines = [
            f"供需类型：{type_label}",
            f"分类：{category_label}",
            f"标题：{title}",
            f"发布方：{row['publisher_name'] or '未知发布方'}",
            f"发布时间：{format_created_at(row['created_at'])}",
            f"地点：{row['address'] or '未填写'}",
            f"联系人：{row['contact_name'] or '未填写'}",
            f"联系电话：{row['contact_phone'] or '未填写'}",
            f"价格：{row['price'] or '面议'}{row['price_unit'] or ''}",
            f"详情：{row['description'] or '暂无详情'}",
        ]
        if extra_fields:
            content_lines.append(f"补充信息：{extra_fields}")

        keywords = [type_label, category_label, "商引羚航", "供需信息"]
        materials.append(
            MaterialInput(
                title_hint=f"{type_label}-{title}",
                raw_content="\n".join(content_lines),
                keywords=list(dict.fromkeys(keyword for keyword in keywords if keyword)),
                target_platforms=["xiaohongshu", "zhihu", "official_account", "toutiao", "shipinhao"],
                image_paths=normalize_image_paths(row["cover_image"], row["images"]),
                source_type="database",
                source_ref=str(row["id"]),
            )
        )
    return materials
