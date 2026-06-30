from __future__ import annotations

import json
import logging
import queue
from dataclasses import dataclass
from datetime import datetime
from threading import Thread
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from .models import TaskJob


LOGGER = logging.getLogger(__name__)
TaskHandler = Callable[["TaskProgress"], dict[str, Any] | None]


@dataclass(frozen=True)
class QueuedTask:
    task_id: str
    handler: TaskHandler


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
        self._queue: queue.Queue[QueuedTask] = queue.Queue()
        self._worker = Thread(target=self._run, name="content-pipeline-task-queue", daemon=True)
        self._worker.start()

    def enqueue(self, task_type: str, handler: TaskHandler, total: int = 0, message: str = "") -> TaskJob:
        task = TaskJob(
            id=str(uuid4()),
            task_type=task_type,
            status="pending",
            progress_total=max(0, int(total or 0)),
            progress_message=message or "任务已进入队列",
        )
        with self.session_factory() as session:
            session.add(task)
            session.commit()
            session.refresh(task)
            task_id = task.id
        self._queue.put(QueuedTask(task_id=task_id, handler=handler))
        with self.session_factory() as session:
            return session.get(TaskJob, task_id)

    def _run(self) -> None:
        while True:
            queued = self._queue.get()
            try:
                self._mark_running(queued.task_id)
                result = queued.handler(TaskProgress(self.session_factory, queued.task_id)) or {}
                self._mark_finished(queued.task_id, result)
            except Exception as exc:
                LOGGER.exception("Queued task failed: %s", queued.task_id)
                self._mark_failed(queued.task_id, exc)
            finally:
                self._queue.task_done()

    def _mark_running(self, task_id: str) -> None:
        with self.session_factory() as session:
            task = session.get(TaskJob, task_id)
            if not task:
                return
            task.status = "running"
            task.started_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            if not task.progress_message:
                task.progress_message = "任务执行中"
            session.commit()

    def _mark_finished(self, task_id: str, result: dict[str, Any]) -> None:
        with self.session_factory() as session:
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

    def _mark_failed(self, task_id: str, exc: Exception) -> None:
        with self.session_factory() as session:
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
