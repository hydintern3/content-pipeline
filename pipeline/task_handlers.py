from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from .batch import process_batch_job
from .config import AppConfig
from .database import session_scope
from .generation import generate_drafts, generate_variants, material_for_platform, set_llm_observer
from .observability import record_llm_call
from .repository import (
    article_payload,
    create_articles,
    create_material,
    get_or_create_generation_run,
    link_generation_articles,
    material_payload,
)
from .schemas import normalize_list, normalize_material
from .task_queue import TaskProgress


LOGGER = logging.getLogger(__name__)


def execute_registered_task(
    task_type: str,
    payload: dict[str, Any],
    config: AppConfig,
    session_factory: sessionmaker[Session],
    task_id: str,
) -> dict[str, Any] | None:
    set_llm_observer(lambda metric: record_llm_call(session_factory, metric))
    progress = TaskProgress(session_factory, task_id)
    if task_type == "material_generation":
        return run_generation_task(payload, config, session_factory, progress)
    if task_type == "variant_generation":
        return run_variant_generation_task(payload, config, session_factory, progress)
    if task_type == "batch_generation":
        return run_batch_generation_task(payload, config, session_factory, progress)
    raise ValueError(f"Unknown task type: {task_type}")


def run_generation_task(
    payload: dict[str, Any],
    config: AppConfig,
    session_factory: sessionmaker[Session],
    progress: TaskProgress,
) -> dict[str, Any]:
    material_input = normalize_material(payload.get("material") or payload)
    history_run_id = str(payload.get("history_run_id") or "").strip()[:80]
    history_expected_platforms = normalize_list(payload.get("history_expected_platforms"))
    platforms = list(material_input.target_platforms)
    source = ""
    articles_payload: list[dict[str, Any]] = []
    material_result: dict[str, Any] | None = None
    errors: dict[str, str] = {}
    total = len(platforms)
    progress.update(0, total, "生成任务开始执行")

    for index, platform in enumerate(platforms, start=1):
        progress.update(index - 1, total, f"正在生成 {platform}")
        platform_input = material_for_platform(material_input, platform)
        try:
            platform_source, drafts = generate_drafts(platform_input, config)
            with session_scope(session_factory) as session:
                material = create_material(session, platform_input)
                articles = create_articles(session, material, drafts)
                if history_run_id:
                    run_record = get_or_create_generation_run(
                        session,
                        history_run_id,
                        material_input,
                        history_expected_platforms or platforms,
                    )
                    link_generation_articles(session, run_record, articles)
                material_result = material_result or material_payload(material)
                articles_payload.extend(article_payload(article) for article in articles)
            source = source or platform_source
        except Exception as exc:
            LOGGER.exception("Queued generation failed for platform %s", platform)
            errors[platform] = str(exc)
        progress.update(index, total, f"已完成 {index}/{total} 个平台")

    if not articles_payload and errors:
        raise RuntimeError("全部平台生成失败")

    return {
        "source": source,
        "material": material_result,
        "articles": articles_payload,
        "errors": errors,
        "failed_count": len(errors),
    }


def run_variant_generation_task(
    payload: dict[str, Any],
    config: AppConfig,
    session_factory: sessionmaker[Session],
    progress: TaskProgress,
) -> dict[str, Any]:
    material_input = normalize_material(payload.get("material") or payload)
    platform = str(payload.get("platform") or "").strip() or (
        material_input.target_platforms[0] if material_input.target_platforms else ""
    )
    if not platform:
        raise ValueError("缺少变体生成平台")
    try:
        count = max(1, min(int(payload.get("count") or 3), 10))
    except (TypeError, ValueError):
        count = 3
    history_run_id = str(payload.get("history_run_id") or "").strip()[:80]

    progress.update(0, count, "内容变体任务开始执行")
    source, drafts = generate_variants(material_input, config, platform, count)
    progress.update(max(1, count - 1), count, "正在保存变体结果")
    draft_map = {f"{platform}_{index}": draft for index, draft in enumerate(drafts, start=1)}
    with session_scope(session_factory) as session:
        material = create_material(session, material_for_platform(material_input, platform))
        articles = create_articles(session, material, draft_map, status="variant")
        if history_run_id:
            run_record = get_or_create_generation_run(session, history_run_id, material_input, [platform])
            link_generation_articles(session, run_record, articles)
        result = {
            "source": source,
            "material": material_payload(material),
            "articles": [article_payload(article) for article in articles],
            "errors": {},
            "failed_count": 0,
        }
    progress.update(count, count, f"已生成 {len(result['articles'])} 个内容变体")
    return result


def run_batch_generation_task(
    payload: dict[str, Any],
    config: AppConfig,
    session_factory: sessionmaker[Session],
    progress: TaskProgress,
) -> dict[str, Any]:
    job_id = int(payload.get("batch_job_id") or 0)
    if not job_id:
        raise ValueError("缺少批量任务 ID")
    process_batch_job(job_id, config, session_factory, progress.update)
    return {"batch_job_id": job_id}
