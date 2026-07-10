from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

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

DEFAULT_TARGET_PLATFORMS = ["xiaohongshu", "zhihu", "official_account", "toutiao", "shipinhao"]


def ensure_mysql_utf8mb4(database_url: str) -> str:
    if not database_url.startswith("mysql"):
        return database_url
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("charset", "utf8mb4")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_external_database_url(config: AppConfig) -> str:
    if config.external_database_url:
        return ensure_mysql_utf8mb4(config.external_database_url)

    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    password = quote_plus(os.getenv("DB_PASSWORD", ""))
    database = os.getenv("DB_NAME", "operation_agent")
    charset = os.getenv("DB_CHARSET", "utf8mb4")
    return ensure_mysql_utf8mb4(f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}")


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


def is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def resolve_image_url(path: str, base_url: str = "") -> str:
    path = str(path or "").strip()
    base_url = str(base_url or "").strip()
    if not path:
        return ""
    if is_http_url(path) or path.startswith("//"):
        return path
    if not base_url:
        return ""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def resolve_image_urls(paths: list[str], base_url: str = "") -> list[str]:
    urls = [resolve_image_url(path, base_url) for path in paths]
    return [url for url in urls if url]


def format_created_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value or "")


def safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def list_text(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value if item)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def range_text(value: Any) -> str:
    if not isinstance(value, dict):
        return list_text(value)
    minimum = value.get("min")
    maximum = value.get("max")
    unit = value.get("unit") or ""
    if minimum is not None and maximum is not None:
        return f"{minimum}-{maximum}{unit}"
    if minimum is not None:
        return f"{minimum}{unit}起"
    if maximum is not None:
        return f"{maximum}{unit}以内"
    return list_text(value)


def format_extra_fields(value: Any) -> list[str]:
    parsed = parse_json_value(value)
    if not parsed:
        return []
    if not isinstance(parsed, dict):
        text_value = list_text(parsed)
        return [f"补充信息：{text_value}"] if text_value else []

    label_map = {
        "skills": "技能",
        "requirements": "要求",
        "tech_requirements": "技术要求",
        "responsibilities": "职责",
        "deliverables": "交付物",
        "service_scope": "服务范围",
        "education": "学历",
        "experience": "经验",
        "salary_range": "薪资范围",
        "budget": "预算",
        "duration": "周期",
    }
    lines: list[str] = []
    for key, label in label_map.items():
        item = parsed.get(key)
        if item in (None, "", []):
            continue
        value_text = range_text(item) if key in {"salary_range", "budget"} else list_text(item)
        if value_text:
            lines.append(f"{label}：{value_text}")

    known_keys = set(label_map) | {"__priceUnit"}
    extras = {key: item for key, item in parsed.items() if key not in known_keys and item not in (None, "", [])}
    if extras:
        lines.append(f"其他补充：{json.dumps(extras, ensure_ascii=False)}")
    return lines


def extra_keywords(value: Any) -> list[str]:
    parsed = parse_json_value(value)
    if not isinstance(parsed, dict):
        return []
    keywords: list[str] = []
    for key in ("skills", "requirements", "tech_requirements", "deliverables"):
        item = parsed.get(key)
        if isinstance(item, list):
            keywords.extend(str(value) for value in item if value)
        elif item:
            keywords.append(str(item))
    service_scope = parsed.get("service_scope")
    if service_scope:
        keywords.append(str(service_scope))
    return keywords


def row_to_material(row: Any) -> MaterialInput:
    demand_type = str(row["type"] or "")
    category = str(row["category"] or "")
    type_label = TYPE_LABELS.get(demand_type, demand_type or "供需")
    category_label = CATEGORY_LABELS.get(category, category or "其他")
    title = str(row["title"] or "未命名供需信息")
    price = row["price"]
    price_text = f"{price}{row['price_unit'] or ''}" if price is not None else "面议"

    content_lines = [
        f"供需类型：{type_label}",
        f"分类：{category_label}",
        f"标题：{title}",
        f"发布方：{row['publisher_name'] or '未知发布方'}",
        f"发布时间：{format_created_at(row['created_at'])}",
        f"地点：{row['address'] or '未填写'}",
        f"联系人：{row['contact_name'] or '未填写'}",
        f"联系电话：{row['contact_phone'] or '未填写'}",
        f"价格：{price_text}",
        f"详情：{row['description'] or '暂无详情'}",
    ]
    content_lines.extend(format_extra_fields(row["extra_fields"]))

    keywords = [type_label, category_label, "商引羚航", "供需信息", *extra_keywords(row["extra_fields"])]
    return MaterialInput(
        title_hint=f"{category_label}｜{title}",
        raw_content="\n".join(content_lines),
        keywords=list(dict.fromkeys(keyword for keyword in keywords if keyword)),
        target_platforms=list(DEFAULT_TARGET_PLATFORMS),
        image_paths=normalize_image_paths(row["cover_image"], row["images"]),
        source_type="database",
        source_ref=str(row["id"]),
    )


def material_payload(material: MaterialInput) -> dict[str, Any]:
    return {
        "title_hint": material.title_hint,
        "raw_content": material.raw_content,
        "keywords": material.keywords,
        "target_platforms": material.target_platforms,
        "image_paths": material.image_paths,
        "source_type": material.source_type,
        "source_ref": material.source_ref,
    }


def row_to_database_item(row: Any, image_base_url: str = "") -> dict[str, Any]:
    material = row_to_material(row)
    demand_type = str(row["type"] or "")
    category = str(row["category"] or "")
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "type": demand_type,
        "type_label": TYPE_LABELS.get(demand_type, demand_type or "供需"),
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, category or "其他"),
        "description": row["description"] or "",
        "publisher_name": row["publisher_name"] or "",
        "address": row["address"] or "",
        "contact_name": row["contact_name"] or "",
        "contact_phone": row["contact_phone"] or "",
        "price": str(row["price"]) if row["price"] is not None else "",
        "price_unit": row["price_unit"] or "",
        "created_at": format_created_at(row["created_at"]),
        "updated_at": format_created_at(row["updated_at"]),
        "image_paths": material.image_paths,
        "image_urls": resolve_image_urls(material.image_paths, image_base_url),
        "extra_fields": parse_json_value(row["extra_fields"]) or {},
        "material": material_payload(material),
    }


def supply_demand_base_sql() -> str:
    return """
        FROM t_supply_demand AS s
        LEFT JOIN t_c_user AS u
          ON u.user_id = s.publisher_id
         AND u.deleted_flag = 0
        WHERE s.status = 'PUBLISHED'
          AND s.deleted_flag = 0
    """


def build_supply_demand_filters(query: str = "", demand_type: str = "", category: str = "") -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    query = str(query or "").strip()
    demand_type = str(demand_type or "").strip().upper()
    category = str(category or "").strip().upper()

    if query:
        clauses.append(
            """
            AND (
                s.title LIKE :query
                OR s.description LIKE :query
                OR s.address LIKE :query
                OR s.contact_name LIKE :query
                OR u.nickname LIKE :query
            )
            """
        )
        params["query"] = f"%{query}%"
    if demand_type:
        clauses.append("AND s.type = :demand_type")
        params["demand_type"] = demand_type
    if category:
        clauses.append("AND s.category = :category")
        params["category"] = category
    return "\n".join(clauses), params


def search_supply_demand_materials(
    config: AppConfig,
    query: str = "",
    demand_type: str = "",
    category: str = "",
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    limit = safe_int(limit, 10, 1, 50)
    offset = safe_int(offset, 0, 0, 10000)
    engine = create_external_engine(config)
    filters, params = build_supply_demand_filters(query, demand_type, category)
    base_sql = supply_demand_base_sql()
    count_sql = text(f"SELECT COUNT(*) AS total {base_sql} {filters}")
    list_sql = text(
        f"""
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
        {base_sql}
        {filters}
        ORDER BY s.create_time DESC
        LIMIT :limit OFFSET :offset
        """
    )

    with engine.connect() as conn:
        total = int(conn.execute(count_sql, params).scalar() or 0)
        rows = conn.execute(list_sql, {**params, "limit": limit, "offset": offset}).mappings().all()

    return {
        "items": [row_to_database_item(row, config.external_image_base_url) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def fetch_recent_materials(config: AppConfig, limit: int = 5) -> list[MaterialInput]:
    limit = safe_int(limit, 5, 1, 20)
    engine = create_external_engine(config)
    sql = text(
        f"""
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
        {supply_demand_base_sql()}
        ORDER BY s.create_time DESC
        LIMIT :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).mappings().all()

    return [row_to_material(row) for row in rows]
