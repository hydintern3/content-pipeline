from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, jsonify, render_template, request

from pipeline.config import build_config
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

app = Flask(__name__)


def ok(payload: dict[str, Any]):
    return jsonify({"success": True, **payload})


def error(message: str, status: int = 400):
    return jsonify({"success": False, "message": message}), status


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
