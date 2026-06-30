from __future__ import annotations

import logging
import os
import json
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy import select
from werkzeug.utils import secure_filename

from pipeline.batch import batch_job_payload, create_batch_job, parse_batch_file, process_batch_job
from pipeline.compliance import check_articles, check_text
from pipeline.config import build_config, config_from_dict, default_json_config, load_json_config
from pipeline.database import create_app_engine, create_session_factory, init_database, session_scope
from pipeline.generation import follow_up_article_with_llm, generate_drafts
from pipeline.image_processing import process_image
from pipeline.ingestion import fetch_recent_materials
from pipeline.models import BatchJob, ImageAsset, ImageVariant
from pipeline.publishers import publish_article
from pipeline.repository import (
    article_payload,
    create_articles,
    create_follow_up_article,
    create_material,
    follow_up_payload,
    generation_run_detail_payload,
    generation_run_payload,
    get_generation_run,
    get_or_create_generation_run,
    get_article,
    link_generation_articles,
    list_article_followups,
    list_generation_runs,
    material_payload,
    recent_tasks,
    task_payload,
)
from pipeline.scheduler import start_scheduler
from pipeline.schemas import normalize_list, normalize_material


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
LOGGER = logging.getLogger("content_pipeline")

config = build_config()
engine = create_app_engine(config)
try:
    init_database(engine)
except Exception:
    logging.getLogger("content_pipeline").warning(
        "Database initialization failed for %s; falling back to a temporary writable database.",
        config.app_database_url,
    )
    fallback_db = Path(tempfile.gettempdir()) / "content_pipeline" / "pipeline.db"
    fallback_db.parent.mkdir(parents=True, exist_ok=True)
    config = replace(config, app_database_url=f"sqlite:///{fallback_db.as_posix()}")
    engine = create_app_engine(config)
    init_database(engine)
SessionLocal = create_session_factory(engine)
scheduler = start_scheduler(config, SessionLocal)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


def writable_runtime_dir(name: str, default_path: Path) -> Path:
    configured = os.getenv(f"CONTENT_PIPELINE_{name.upper()}_DIR")
    candidate = Path(configured) if configured else default_path
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return candidate
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "content_pipeline" / name
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


UPLOAD_DIR = writable_runtime_dir("uploads", BASE_DIR / "data" / "uploads")
IMAGE_OUTPUT_DIR = writable_runtime_dir("images", BASE_DIR / "data" / "images")

app = Flask(__name__, static_folder=None)
HISTORY_LOCK = Lock()


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
        "generation_concurrency": os.getenv("CONTENT_GENERATION_CONCURRENCY") is not None,
        "compliance_mock": os.getenv("CONTENT_LLM_MOCK") is not None,
        "compliance_llm_model": os.getenv("CONTENT_LLM_COMPLIANCE_MODEL") is not None,
        "compliance_cache_size": os.getenv("CONTENT_COMPLIANCE_CACHE_SIZE") is not None,
        "compliance_auto_check": os.getenv("CONTENT_COMPLIANCE_AUTO_CHECK") is not None,
        "compliance_concurrency": os.getenv("CONTENT_COMPLIANCE_CONCURRENCY") is not None,
        "external_database_url": os.getenv("DATABASE_URL") is not None,
        "pending_output_dir": os.getenv("PENDING_OUTPUT_DIR") is not None,
        "wechat_app_id": os.getenv("WECHAT_APP_ID") is not None,
        "wechat_app_secret": os.getenv("WECHAT_APP_SECRET") is not None,
        "wechat_auto_publish": os.getenv("WECHAT_AUTO_PUBLISH") is not None,
        "wechat_enable_mass_send": os.getenv("WECHAT_ENABLE_MASS_SEND") is not None,
        "scheduler_enabled": os.getenv("SCHEDULER_ENABLED") is not None,
        "scheduler_interval_minutes": os.getenv("SCHEDULER_INTERVAL_MINUTES") is not None,
    }


def default_config_payload() -> dict[str, Any]:
    saved_config = load_json_config()
    defaults = default_json_config()

    def saved(path: str, default: Any = "") -> Any:
        return nested_value(saved_config, path, nested_value(defaults, path, default))

    return {
        "env_overrides": env_overrides(),
        "config": {
            "app_database_url": saved("app_database_url", "sqlite:///data/pipeline.db"),
            "llm": {
                "api_key": "",
                "api_key_configured": config.has_llm,
                "base_url": saved("llm.base_url", "https://api.openai.com/v1"),
                "model": saved("llm.model", "gpt-4o-mini"),
            },
            "generation": {
                "concurrency": saved("generation.concurrency", 3),
            },
            "compliance": {
                "mock": clean_bool(saved("compliance.mock", False)),
                "llm_model": saved("compliance.llm_model", ""),
                "cache_size": saved("compliance.cache_size", 512),
                "auto_check": clean_bool(saved("compliance.auto_check", True)),
                "concurrency": saved("compliance.concurrency", 2),
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
    generation = source.get("generation") if isinstance(source.get("generation"), dict) else {}
    compliance = source.get("compliance") if isinstance(source.get("compliance"), dict) else {}
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
    try:
        generation_concurrency = max(
            1,
            int(generation.get("concurrency", nested_value(existing, "generation.concurrency", 3)) or 3),
        )
        compliance_cache_size = max(
            0,
            int(compliance.get("cache_size", nested_value(existing, "compliance.cache_size", 512)) or 512),
        )
        compliance_concurrency = max(
            1,
            int(compliance.get("concurrency", nested_value(existing, "compliance.concurrency", 2)) or 2),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("并发数和缓存大小必须是数字") from exc

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
    updated["generation"] = {
        "concurrency": generation_concurrency,
    }
    updated["compliance"] = {
        "mock": clean_bool(compliance.get("mock", nested_value(existing, "compliance.mock", False))),
        "llm_model": clean_text(compliance.get("llm_model", nested_value(existing, "compliance.llm_model", ""))),
        "cache_size": compliance_cache_size,
        "auto_check": clean_bool(
            compliance.get("auto_check", nested_value(existing, "compliance.auto_check", True))
        ),
        "concurrency": compliance_concurrency,
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


def config_for_request(payload: dict[str, Any]):
    personal_config = payload.get("config")
    if not isinstance(personal_config, dict):
        return config
    normalized = normalize_config_update(personal_config, load_json_config())
    return config_from_dict(normalized)


def config_from_form() -> Any:
    raw_config = request.form.get("config") or "{}"
    try:
        parsed = json.loads(raw_config)
    except json.JSONDecodeError:
        parsed = {}
    return config_for_request({"config": parsed})


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
                "generation": {
                    "concurrency": config.generation_concurrency,
                },
                "compliance": {
                    "mock": config.compliance_mock,
                    "llm_model": config.compliance_llm_model or config.llm_model,
                    "cache_size": config.compliance_cache_size,
                    "auto_check": config.compliance_auto_check,
                    "concurrency": config.compliance_concurrency,
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
    return ok({"data": default_config_payload()})


@app.post("/api/config")
def preview_config():
    return ok({"data": default_config_payload()})


@app.post("/api/materials/generate")
def generate_from_material():
    try:
        payload = request.get_json(silent=True) or {}
        material_input = normalize_material(payload.get("material") or payload)
        history_run_id = clean_text(payload.get("history_run_id"))[:80]
        history_expected_platforms = normalize_list(payload.get("history_expected_platforms"))
        request_config = config_for_request(payload)
        source, drafts = generate_drafts(material_input, request_config)
        with session_scope(SessionLocal) as session:
            material = create_material(session, material_input)
            articles = create_articles(session, material, drafts)
            if history_run_id:
                with HISTORY_LOCK:
                    run = get_or_create_generation_run(
                        session,
                        history_run_id,
                        material_input,
                        history_expected_platforms or material_input.target_platforms,
                    )
                    link_generation_articles(session, run, articles)
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
        request_config = config_for_request(payload)
        materials = fetch_recent_materials(request_config, limit=limit)
        with session_scope(SessionLocal) as session:
            persisted = [create_material(session, material) for material in materials]
            return ok({"materials": [material_payload(material) for material in persisted]})
    except Exception as exc:
        LOGGER.exception("Recent material pull failed")
        return error(f"数据库拉取失败：{exc}", 500)


@app.post("/api/publish")
def publish():
    payload = request.get_json(silent=True) or {}
    request_config = config_for_request(payload)
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
            task = publish_article(session, article, request_config, requested_mode=requested_mode)
            tasks.append(task)
        return ok({"tasks": [task_payload(task) for task in tasks]})


@app.get("/api/tasks")
def tasks():
    limit = int(request.args.get("limit") or 30)
    with session_scope(SessionLocal) as session:
        return ok({"tasks": [task_payload(task) for task in recent_tasks(session, limit=limit)]})


@app.post("/api/articles/<int:article_id>/follow_up")
def follow_up_article(article_id: int):
    payload = request.get_json(silent=True) or {}
    instruction = clean_text(payload.get("instruction"))
    if not instruction:
        return error("缺少追问修改要求")
    instruction = instruction[:2000]
    request_config = config_for_request(payload)
    if not request_config.has_llm:
        return error("追问优化需要先配置 LLM API Key", 400)

    with session_scope(SessionLocal) as session:
        source_article = get_article(session, article_id)
        if not source_article:
            return error(f"文章不存在：{article_id}", 404)
        source_payload = article_payload(source_article)

    class ArticleSnapshot:
        pass

    snapshot = ArticleSnapshot()
    snapshot.id = source_payload["id"]
    snapshot.material_id = source_payload["material_id"]
    snapshot.platform = source_payload["platform"]
    snapshot.title = source_payload["title"]
    snapshot.content = source_payload["content"]
    snapshot.content_format = source_payload["format"]

    try:
        draft = follow_up_article_with_llm(snapshot, instruction, request_config)
    except ValueError as exc:
        return error(str(exc), 502)
    except Exception as exc:
        LOGGER.exception("Article follow-up failed")
        return error(f"追问优化失败：{exc}", 502)

    with session_scope(SessionLocal) as session:
        source_article = get_article(session, article_id)
        if not source_article:
            return error(f"文章不存在：{article_id}", 404)
        article, follow_up = create_follow_up_article(
            session,
            source_article,
            draft,
            instruction,
            request_config.llm_model,
        )
        return ok(
            {
                "article": article_payload(article),
                "follow_up": follow_up_payload(follow_up),
                "follow_ups": [follow_up_payload(item) for item in list_article_followups(session, article.id)],
            }
        )


@app.get("/api/history/generations")
def generation_history():
    limit = int(request.args.get("limit") or 20)
    offset = int(request.args.get("offset") or 0)
    query = clean_text(request.args.get("q"))
    platform = clean_text(request.args.get("platform"))
    with session_scope(SessionLocal) as session:
        runs = list_generation_runs(
            session,
            limit=limit,
            offset=offset,
            query=query,
            platform=platform,
        )
        return ok({"items": [generation_run_payload(run) for run in runs]})


@app.get("/api/history/generations/<run_id>")
def generation_history_detail(run_id: str):
    with session_scope(SessionLocal) as session:
        run = get_generation_run(session, run_id)
        if not run:
            return error(f"生成历史不存在：{run_id}", 404)
        return ok({"item": generation_run_detail_payload(run)})


@app.post("/api/compliance/check")
def compliance_check():
    payload = request.get_json(silent=True) or {}
    articles = payload.get("articles")
    request_config = config_for_request(payload)
    force_refresh = clean_bool(payload.get("force_refresh", False))
    if isinstance(articles, list):
        return ok({"data": check_articles(articles, config=request_config, force_refresh=force_refresh)})

    text = str(payload.get("text") or "")
    platform = str(payload.get("platform") or "")
    article_id = payload.get("article_id")
    if article_id:
        with session_scope(SessionLocal) as session:
            article = get_article(session, int(article_id))
            if not article:
                return error(f"文章不存在：{article_id}", 404)
            text = f"{article.title}\n{article.content}"
            platform = article.platform
    if not text.strip():
        return error("缺少待检查文本")
    return ok({"data": check_text(text, platform, config=request_config, force_refresh=force_refresh)})


@app.post("/api/materials/batch_generate")
def batch_generate():
    if "file" not in request.files:
        return error("缺少批量导入文件")
    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return error("文件名不能为空")

    try:
        materials = parse_batch_file(uploaded_file.filename, uploaded_file.read())
        if not materials:
            return error("文件中没有可用素材")
        request_config = config_from_form()
        with session_scope(SessionLocal) as session:
            job = create_batch_job(session, uploaded_file.filename, materials)
            job_id = job.id
        worker = Thread(
            target=process_batch_job,
            args=(job_id, request_config, SessionLocal),
            daemon=True,
        )
        worker.start()
        with session_scope(SessionLocal) as session:
            job = session.get(BatchJob, job_id)
            return ok({"job": batch_job_payload(job, include_items=True)})
    except Exception as exc:
        LOGGER.exception("Batch generate failed")
        return error(f"批量任务创建失败：{exc}", 500)


@app.get("/api/batch_jobs")
def list_batch_jobs():
    limit = int(request.args.get("limit") or 20)
    with session_scope(SessionLocal) as session:
        stmt = select(BatchJob).order_by(BatchJob.created_at.desc()).limit(max(1, min(limit, 100)))
        jobs = list(session.scalars(stmt).all())
        return ok({"jobs": [batch_job_payload(job) for job in jobs]})


@app.get("/api/batch_jobs/<int:job_id>")
def get_batch_job(job_id: int):
    with session_scope(SessionLocal) as session:
        job = session.get(BatchJob, job_id)
        if not job:
            return error(f"批量任务不存在：{job_id}", 404)
        return ok({"job": batch_job_payload(job, include_items=True)})


@app.post("/api/images/process")
def process_images():
    files = request.files.getlist("files")
    if not files:
        single = request.files.get("file")
        files = [single] if single else []
    if not files:
        return error("缺少图片文件")

    topic = clean_text(request.form.get("topic") or "未命名选题")
    platforms = normalize_list(request.form.get("platforms")) or [
        "official_account",
        "xiaohongshu",
        "zhihu",
        "toutiao",
        "shipinhao",
    ]
    upload_day = datetime.now().strftime("%Y-%m-%d")
    saved_root = UPLOAD_DIR / "images" / upload_day
    saved_root.mkdir(parents=True, exist_ok=True)

    assets_payload = []
    try:
        for uploaded_file in files:
            if not uploaded_file or not uploaded_file.filename:
                continue
            original_name = secure_filename(uploaded_file.filename) or "image.jpg"
            original_path = saved_root / original_name
            uploaded_file.save(original_path)
            variants = process_image(original_path, IMAGE_OUTPUT_DIR, topic, platforms)

            with session_scope(SessionLocal) as session:
                asset = ImageAsset(
                    original_name=uploaded_file.filename,
                    original_path=str(original_path.resolve()),
                    topic=topic,
                    status="processed",
                )
                session.add(asset)
                session.flush()
                variant_models = []
                for variant in variants:
                    model = ImageVariant(asset=asset, **variant)
                    session.add(model)
                    variant_models.append(model)
                session.flush()
                assets_payload.append(
                    {
                        "id": asset.id,
                        "original_name": asset.original_name,
                        "original_path": asset.original_path,
                        "topic": asset.topic,
                        "status": asset.status,
                        "variants": [
                            {
                                "id": variant.id,
                                "platform": variant.platform,
                                "usage": variant.usage,
                                "width": variant.width,
                                "height": variant.height,
                                "output_path": variant.output_path,
                                "file_size": variant.file_size,
                            }
                            for variant in variant_models
                        ],
                    }
                )
        return ok({"assets": assets_payload})
    except Exception as exc:
        LOGGER.exception("Image processing failed")
        return error(f"图片处理失败：{exc}", 500)


@app.get("/")
@app.get("/<path:path>")
def serve_frontend(path: str = ""):
    if path.startswith("api/"):
        return error("API endpoint not found", 404)

    if FRONTEND_DIST.exists():
        requested_file = FRONTEND_DIST / path
        if path and requested_file.is_file():
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")

    return ok(
        {
            "message": (
                "Frontend build not found. Run the Vue dev server from content_pipeline/frontend "
                "during development, or build it into frontend/dist for Flask production serving."
            )
        }
    )


if __name__ == "__main__":
    debug_enabled = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0", port=5000, debug=debug_enabled, use_reloader=False)
