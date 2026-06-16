from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any

from flask import Flask, jsonify, render_template, request

from pipeline.config import build_config, default_json_config, load_json_config, save_json_config, resolve_config_path
from pipeline.database import create_app_engine, create_session_factory, init_database, session_scope
from pipeline.generation import generate_drafts
from pipeline.ingestion import fetch_recent_materials
from pipeline.publishers import publish_article
from pipeline.repository import (
    article_payload,
    create_articles,
    create_material,
    get_article,
    material_payload,
    recent_tasks,
    task_payload,
)
from pipeline.scheduler import start_scheduler
from pipeline.schemas import normalize_material


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
LOGGER = logging.getLogger("content_pipeline")

config = build_config()
engine = create_app_engine(config)
init_database(engine)
SessionLocal = create_session_factory(engine)
scheduler = start_scheduler(config, SessionLocal)
CONFIG_LOCK = Lock()

app = Flask(__name__)


def ok(payload: dict[str, Any]):
    return jsonify({"success": True, **payload})


def error(message: str, status: int = 400):
    return jsonify({"success": False, "message": message}), status


def env_overrides() -> dict[str, bool]:
    return {
        "app_database_url": os.getenv("APP_DATABASE_URL") is not None,
        "llm_api_key": os.getenv("CONTENT_LLM_API_KEY") is not None,
        "llm_base_url": os.getenv("CONTENT_LLM_BASE_URL") is not None,
        "llm_model": os.getenv("CONTENT_LLM_MODEL") is not None,
        "external_database_url": os.getenv("DATABASE_URL") is not None,
        "pending_output_dir": os.getenv("PENDING_OUTPUT_DIR") is not None,
        "wechat_app_id": os.getenv("WECHAT_APP_ID") is not None,
        "wechat_app_secret": os.getenv("WECHAT_APP_SECRET") is not None,
        "wechat_auto_publish": os.getenv("WECHAT_AUTO_PUBLISH") is not None,
        "wechat_enable_mass_send": os.getenv("WECHAT_ENABLE_MASS_SEND") is not None,
        "scheduler_enabled": os.getenv("SCHEDULER_ENABLED") is not None,
        "scheduler_interval_minutes": os.getenv("SCHEDULER_INTERVAL_MINUTES") is not None,
    }


def editable_config_payload() -> dict[str, Any]:
    saved_config = load_json_config()
    defaults = default_json_config()

    def saved(path: str, default: Any = "") -> Any:
        return nested_value(saved_config, path, nested_value(defaults, path, default))

    return {
        "config_path": str(resolve_config_path()),
        "env_overrides": env_overrides(),
        "config": {
            "app_database_url": saved("app_database_url", "sqlite:///data/pipeline.db"),
            "llm": {
                "api_key": "",
                "api_key_configured": config.has_llm,
                "base_url": saved("llm.base_url", "https://api.openai.com/v1"),
                "model": saved("llm.model", "gpt-4o-mini"),
            },
            "database": {
                "url": "",
                "configured": config.has_external_database,
            },
            "publish": {
                "pending_output_dir": saved("publish.pending_output_dir", "data/pending"),
            },
            "wechat": {
                "app_id": saved("wechat.app_id", ""),
                "app_secret": "",
                "app_secret_configured": bool(config.wechat_app_secret),
                "auto_publish": clean_bool(saved("wechat.auto_publish", False)),
                "enable_mass_send": clean_bool(saved("wechat.enable_mass_send", False)),
            },
            "scheduler": {
                "enabled": clean_bool(saved("scheduler.enabled", False)),
                "interval_minutes": saved("scheduler.interval_minutes", 240),
            },
        },
    }


def nested_value(config_data: dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = config_data
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part, default)
    return current


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_config_update(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    if not isinstance(source, dict):
        raise ValueError("配置内容格式不正确")

    llm = source.get("llm") if isinstance(source.get("llm"), dict) else {}
    database = source.get("database") if isinstance(source.get("database"), dict) else {}
    publish = source.get("publish") if isinstance(source.get("publish"), dict) else {}
    wechat = source.get("wechat") if isinstance(source.get("wechat"), dict) else {}
    scheduler_data = source.get("scheduler") if isinstance(source.get("scheduler"), dict) else {}

    interval_raw = scheduler_data.get(
        "interval_minutes",
        nested_value(existing, "scheduler.interval_minutes", 240),
    )
    try:
        interval_minutes = max(5, int(interval_raw or 240))
    except (TypeError, ValueError) as exc:
        raise ValueError("定时任务间隔必须是数字") from exc

    updated = default_json_config()
    updated["app_database_url"] = clean_text(
        source.get("app_database_url", existing.get("app_database_url", updated["app_database_url"]))
    )
    if not updated["app_database_url"]:
        updated["app_database_url"] = "sqlite:///data/pipeline.db"

    api_key = clean_text(llm.get("api_key"))
    updated["llm"] = {
        "api_key": api_key or clean_text(nested_value(existing, "llm.api_key", "")),
        "base_url": clean_text(
            llm.get("base_url", nested_value(existing, "llm.base_url", "https://api.openai.com/v1"))
        )
        or "https://api.openai.com/v1",
        "model": clean_text(llm.get("model", nested_value(existing, "llm.model", "gpt-4o-mini")))
        or "gpt-4o-mini",
    }

    database_url = clean_text(database.get("url"))
    updated["database"] = {
        "url": database_url or clean_text(nested_value(existing, "database.url", "")),
    }
    updated["publish"] = {
        "pending_output_dir": clean_text(
            publish.get(
                "pending_output_dir",
                nested_value(existing, "publish.pending_output_dir", "data/pending"),
            )
        )
        or "data/pending",
    }

    app_secret = clean_text(wechat.get("app_secret"))
    updated["wechat"] = {
        "app_id": clean_text(wechat.get("app_id", nested_value(existing, "wechat.app_id", ""))),
        "app_secret": app_secret or clean_text(nested_value(existing, "wechat.app_secret", "")),
        "auto_publish": clean_bool(
            wechat.get("auto_publish", nested_value(existing, "wechat.auto_publish", False))
        ),
        "enable_mass_send": clean_bool(
            wechat.get("enable_mass_send", nested_value(existing, "wechat.enable_mass_send", False))
        ),
    }
    updated["scheduler"] = {
        "enabled": clean_bool(scheduler_data.get("enabled", nested_value(existing, "scheduler.enabled", False))),
        "interval_minutes": interval_minutes,
    }
    return updated


def reload_runtime_config() -> None:
    global config, engine, SessionLocal, scheduler

    next_config = build_config()
    next_engine = create_app_engine(next_config)
    init_database(next_engine)
    next_session_local = create_session_factory(next_engine)
    next_scheduler = start_scheduler(next_config, next_session_local)

    old_engine = engine
    old_scheduler = scheduler
    config = next_config
    engine = next_engine
    SessionLocal = next_session_local
    scheduler = next_scheduler

    if old_scheduler:
        old_scheduler.shutdown(wait=False)
    old_engine.dispose()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config/status")
def config_status():
    return ok(
        {
            "data": {
                "llm": {
                    "configured": config.has_llm,
                    "base_url": config.llm_base_url,
                    "model": config.llm_model,
                },
                "database": {
                    "configured": config.has_external_database,
                    "app_database_url": config.app_database_url,
                },
                "wechat": {
                    "configured": config.has_wechat,
                    "auto_publish_enabled": config.wechat_auto_publish,
                    "mass_send_enabled": config.wechat_enable_mass_send,
                },
                "publish": {
                    "pending_output_dir": str(config.pending_output_dir),
                },
                "scheduler": {
                    "enabled": bool(scheduler),
                    "interval_minutes": config.scheduler_interval_minutes,
                },
            }
        }
    )


@app.get("/api/config")
def get_config():
    with CONFIG_LOCK:
        return ok({"data": editable_config_payload()})


@app.post("/api/config")
def save_config():
    payload = request.get_json(silent=True) or {}
    try:
        with CONFIG_LOCK:
            existing = load_json_config()
            updated = normalize_config_update(payload, existing)
            save_json_config(updated)
            reload_runtime_config()
            return ok({"data": editable_config_payload()})
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        LOGGER.exception("Config save failed")
        return error(f"配置保存失败：{exc}", 500)


@app.post("/api/materials/generate")
def generate_from_material():
    try:
        payload = request.get_json(silent=True) or {}
        material_input = normalize_material(payload.get("material") or payload)
        source, drafts = generate_drafts(material_input, config)
        with session_scope(SessionLocal) as session:
            material = create_material(session, material_input)
            articles = create_articles(session, material, drafts)
            return ok(
                {
                    "source": source,
                    "material": material_payload(material),
                    "articles": [article_payload(article) for article in articles],
                }
            )
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        LOGGER.exception("Generate request failed")
        return error(f"生成失败：{exc}", 500)


@app.post("/api/materials/pull_recent")
def pull_recent_materials():
    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit") or 5)
    try:
        materials = fetch_recent_materials(config, limit=limit)
        with session_scope(SessionLocal) as session:
            persisted = [create_material(session, material) for material in materials]
            return ok({"materials": [material_payload(material) for material in persisted]})
    except Exception as exc:
        LOGGER.exception("Recent material pull failed")
        return error(f"数据库拉取失败：{exc}", 500)


@app.post("/api/publish")
def publish():
    payload = request.get_json(silent=True) or {}
    article_ids = payload.get("article_ids") or payload.get("article_id")
    requested_mode = (payload.get("mode") or "").strip() or None
    if isinstance(article_ids, int):
        article_ids = [article_ids]
    if not isinstance(article_ids, list) or not article_ids:
        return error("缺少 article_id 或 article_ids")

    with session_scope(SessionLocal) as session:
        tasks = []
        for raw_article_id in article_ids:
            article = get_article(session, int(raw_article_id))
            if not article:
                return error(f"文章不存在：{raw_article_id}", 404)
            task = publish_article(session, article, config, requested_mode=requested_mode)
            tasks.append(task)
        return ok({"tasks": [task_payload(task) for task in tasks]})


@app.get("/api/tasks")
def tasks():
    limit = int(request.args.get("limit") or 30)
    with session_scope(SessionLocal) as session:
        return ok({"tasks": [task_payload(task) for task in recent_tasks(session, limit=limit)]})


if __name__ == "__main__":
    debug_enabled = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0", port=5000, debug=debug_enabled, use_reloader=False)
