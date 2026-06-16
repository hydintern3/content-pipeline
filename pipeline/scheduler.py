from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import AppConfig
from .database import session_scope
from .generation import generate_drafts
from .ingestion import fetch_recent_materials
from .publishers import publish_article
from .repository import create_articles, create_material


LOGGER = logging.getLogger(__name__)


def run_scheduled_pipeline(config: AppConfig, session_factory) -> None:
    try:
        materials = fetch_recent_materials(config, limit=5)
    except Exception:
        LOGGER.exception("Scheduled database pull failed")
        return

    for material_input in materials:
        with session_scope(session_factory) as session:
            material = create_material(session, material_input)
            _, drafts = generate_drafts(material_input, config)
            articles = create_articles(session, material, drafts)
            for article in articles:
                publish_article(session, article, config, requested_mode="file")


def start_scheduler(config: AppConfig, session_factory) -> BackgroundScheduler | None:
    if not config.scheduler_enabled:
        return None
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        run_scheduled_pipeline,
        "interval",
        minutes=config.scheduler_interval_minutes,
        args=[config, session_factory],
        id="content_pipeline_pull_generate_export",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler

