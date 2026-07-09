from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from celery import Celery
from sqlalchemy.orm import Session, sessionmaker

from .config import config_from_dict, load_json_config
from .database import create_app_engine, create_session_factory, init_database
from .models import TaskJob


LOGGER = logging.getLogger(__name__)

CELERY_BROKER_URL = os.getenv("CONTENT_CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CONTENT_CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
DEFAULT_QUEUE = os.getenv("CONTENT_CELERY_QUEUE", "content_pipeline")
DEFAULT_PRIORITY = int(os.getenv("CONTENT_CELERY_DEFAULT_PRIORITY", "5"))
DEFAULT_MAX_RETRIES = int(os.getenv("CONTENT_CELERY_TASK_MAX_RETRIES", "3"))

celery_app = Celery(
    "content_pipeline",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_default_queue=DEFAULT_QUEUE,
    task_default_priority=DEFAULT_PRIORITY,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_transport_options={
        "queue_order_strategy": "priority",
        "priority_steps": list(range(10)),
    },
)


class TaskProgress:
    def __init__(self, session_factory: sessionmaker[Session], task_id: str):
        self.session_factory = session_factory
        self.task_id = task_id

    def update(self, current: int, total: int, message: str = "") -> None:
        total = max(0, int(total or 0))
        current = max(0, min(int(current or 0), total or int(current or 0)))
        percent = int((current / total) * 100) if total else 0
        with self.session_factory() as session:
            task = session.get(TaskJob, self.task_id)
            if not task:
                return
            task.progress_current = current
            task.progress_total = total
            task.progress_percent = percent
            if message:
                task.progress_message = message
            task.updated_at = datetime.utcnow()
            session.commit()


class TaskQueue:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        config_payload: dict[str, Any],
        total: int = 0,
        message: str = "",
        priority: int | None = None,
        queue_name: str | None = None,
        max_retries: int | None = None,
    ) -> TaskJob:
        priority_value = normalize_priority(priority)
        queue_value = queue_name or queue_for_task(task_type)
        retries_value = max(0, int(max_retries if max_retries is not None else DEFAULT_MAX_RETRIES))
        task = TaskJob(
            id=str(uuid4()),
            task_type=task_type,
            status="pending",
            queue_name=queue_value,
            priority=priority_value,
            max_retries=retries_value,
            progress_total=max(0, int(total or 0)),
            progress_message=message or "任务已进入队列",
        )
        with self.session_factory() as session:
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id

        async_result = execute_task.apply_async(
            args=[task_id, task_type, payload, config_payload, retries_value],
            queue=queue_value,
            priority=priority_value,
        )
        with self.session_factory() as session:
            task = session.get(TaskJob, task_id)
            if task:
                task.celery_task_id = async_result.id
                task.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(task)
            return task


def normalize_priority(priority: int | None) -> int:
    if priority is None:
        return DEFAULT_PRIORITY
    return max(0, min(9, int(priority)))


def queue_for_task(task_type: str) -> str:
    explicit = {
        "material_generation": os.getenv("CONTENT_CELERY_GENERATION_QUEUE"),
        "variant_generation": os.getenv("CONTENT_CELERY_GENERATION_QUEUE"),
        "batch_generation": os.getenv("CONTENT_CELERY_BATCH_QUEUE"),
    }.get(task_type)
    return explicit or DEFAULT_QUEUE


def worker_session_factory() -> sessionmaker[Session]:
    config = config_from_dict(load_json_config())
    engine = create_app_engine(config)
    init_database(engine)
    return create_session_factory(engine)


@celery_app.task(name="pipeline.task_queue.execute_task", bind=True, acks_late=True)
def execute_task(
    self,
    task_id: str,
    task_type: str,
    payload: dict[str, Any],
    config_payload: dict[str, Any],
    max_retries: int,
):
    from .task_handlers import execute_registered_task

    session_factory = worker_session_factory()
    mark_running(session_factory, task_id, celery_task_id=self.request.id)
    try:
        request_config = config_from_dict(config_payload or load_json_config(), prefer_config=True)
        result = execute_registered_task(task_type, payload or {}, request_config, session_factory, task_id) or {}
        mark_finished(session_factory, task_id, result)
        return result
    except Exception as exc:
        retry_count = int(getattr(self.request, "retries", 0) or 0)
        if retry_count < max_retries:
            next_retry = retry_count + 1
            countdown = min(300, 5 * (2 ** retry_count))
            mark_retrying(session_factory, task_id, exc, next_retry)
            raise self.retry(exc=exc, countdown=countdown, max_retries=max_retries)
        LOGGER.exception("Celery task failed after retries: %s", task_id)
        mark_failed(session_factory, task_id, exc)
        raise


def mark_running(session_factory: sessionmaker[Session], task_id: str, celery_task_id: str = "") -> None:
    with session_factory() as session:
        task = session.get(TaskJob, task_id)
        if not task:
            return
        task.status = "running"
        task.celery_task_id = celery_task_id or task.celery_task_id
        task.started_at = task.started_at or datetime.utcnow()
        task.updated_at = datetime.utcnow()
        if not task.progress_message:
            task.progress_message = "任务执行中"
        session.commit()


def mark_retrying(session_factory: sessionmaker[Session], task_id: str, exc: Exception, retry_count: int) -> None:
    with session_factory() as session:
        task = session.get(TaskJob, task_id)
        if not task:
            return
        task.status = "retrying"
        task.retry_count = retry_count
        task.error_message = str(exc)
        task.progress_message = f"任务失败，准备第 {retry_count} 次重试"
        task.updated_at = datetime.utcnow()
        session.commit()


def mark_finished(session_factory: sessionmaker[Session], task_id: str, result: dict[str, Any]) -> None:
    with session_factory() as session:
        task = session.get(TaskJob, task_id)
        if not task:
            return
        task.status = "success"
        task.progress_current = task.progress_total or task.progress_current
        task.progress_percent = 100
        task.progress_message = task.progress_message or "任务完成"
        task.result_json = json.dumps(result, ensure_ascii=False)
        task.finished_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        session.commit()


def mark_failed(session_factory: sessionmaker[Session], task_id: str, exc: Exception) -> None:
    with session_factory() as session:
        task = session.get(TaskJob, task_id)
        if not task:
            return
        task.status = "failed"
        task.error_message = str(exc)
        task.progress_message = "任务执行失败"
        task.finished_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        session.commit()


def task_job_payload(task: TaskJob) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if task.result_json:
        try:
            result = json.loads(task.result_json)
        except json.JSONDecodeError:
            result = {}
    return {
        "id": task.id,
        "type": task.task_type,
        "status": task.status,
        "celery_task_id": task.celery_task_id,
        "queue_name": task.queue_name,
        "priority": task.priority,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "progress": {
            "current": task.progress_current,
            "total": task.progress_total,
            "percent": task.progress_percent,
            "message": task.progress_message,
        },
        "result": result,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }
