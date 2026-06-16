from __future__ import annotations

from datetime import datetime
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import AppConfig
from .schemas import MaterialInput


CATEGORY_LABELS = {
    "recruitment": "招聘",
    "building_rent": "楼宇出租",
}


def build_external_database_url(config: AppConfig) -> str:
    if config.external_database_url:
        return config.external_database_url

    import os

    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    password = quote_plus(os.getenv("DB_PASSWORD", ""))
    database = os.getenv("DB_NAME", "operation_agent")
    charset = os.getenv("DB_CHARSET", "utf8mb4")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"


def create_external_engine(config: AppConfig) -> Engine:
    return create_engine(build_external_database_url(config), pool_pre_ping=True, pool_recycle=3600)


def fetch_recent_materials(config: AppConfig, limit: int = 5) -> list[MaterialInput]:
    limit = max(1, min(int(limit or 5), 20))
    engine = create_external_engine(config)
    sql = text(
        """
        SELECT
            i.id,
            i.title,
            i.description,
            i.category,
            i.created_at,
            p.name AS publisher_name
        FROM information AS i
        INNER JOIN publisher AS p ON p.id = i.publisher_id
        WHERE i.created_at >= NOW() - INTERVAL 1 DAY
          AND i.category IN ('recruitment', 'building_rent')
        ORDER BY i.created_at DESC
        LIMIT :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).mappings().all()

    materials: list[MaterialInput] = []
    for row in rows:
        category = str(row["category"] or "")
        category_label = CATEGORY_LABELS.get(category, category or "其他")
        created_at = row["created_at"]
        if isinstance(created_at, datetime):
            created_text = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            created_text = str(created_at or "")
        title = str(row["title"] or "未命名信息")
        raw_content = "\n".join(
            [
                f"类型：{category_label}",
                f"标题：{title}",
                f"发布方：{row['publisher_name'] or '未知发布方'}",
                f"发布时间：{created_text}",
                f"详情：{row['description'] or '暂无详情'}",
            ]
        )
        materials.append(
            MaterialInput(
                title_hint=f"{category_label}｜{title}",
                raw_content=raw_content,
                keywords=[category_label, "供需信息"],
                target_platforms=["xiaohongshu", "zhihu", "official_account"],
                image_paths=[],
                source_type="database",
                source_ref=str(row["id"]),
            )
        )
    return materials

