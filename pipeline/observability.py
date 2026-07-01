from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .models import LlmCallMetric, ObservabilityLog


MODEL_PRICE_PER_1M_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
}


def estimate_llm_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    input_price, output_price = MODEL_PRICE_PER_1M_TOKENS.get(
        model,
        (Decimal("0.15"), Decimal("0.60")),
    )
    return (
        (Decimal(prompt_tokens or 0) / Decimal(1_000_000) * input_price)
        + (Decimal(completion_tokens or 0) / Decimal(1_000_000) * output_price)
    ).quantize(Decimal("0.000001"))


def record_log(
    session_factory: sessionmaker[Session],
    *,
    event_type: str,
    level: str = "info",
    message: str = "",
    path: str = "",
    method: str = "",
    status_code: int = 0,
    duration_ms: int = 0,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        with session_factory() as session:
            session.add(
                ObservabilityLog(
                    event_type=event_type,
                    level=level,
                    message=message,
                    path=path,
                    method=method,
                    status_code=int(status_code or 0),
                    duration_ms=int(duration_ms or 0),
                    details_json=json.dumps(details or {}, ensure_ascii=False),
                )
            )
            session.commit()
    except Exception:
        return


def record_llm_call(session_factory: sessionmaker[Session], metric: dict[str, Any]) -> None:
    try:
        prompt_tokens = int(metric.get("prompt_tokens") or 0)
        completion_tokens = int(metric.get("completion_tokens") or 0)
        model = str(metric.get("model") or "")
        estimated_cost = estimate_llm_cost_usd(model, prompt_tokens, completion_tokens)
        with session_factory() as session:
            session.add(
                LlmCallMetric(
                    operation=str(metric.get("operation") or ""),
                    platform=str(metric.get("platform") or ""),
                    model=model,
                    success=1 if metric.get("success", True) else 0,
                    latency_ms=int(metric.get("latency_ms") or 0),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=int(metric.get("total_tokens") or prompt_tokens + completion_tokens),
                    estimated_cost_usd=str(estimated_cost),
                    error_message=str(metric.get("error_message") or "")[:2000],
                )
            )
            session.commit()
    except Exception:
        return


def log_payload(item: ObservabilityLog) -> dict[str, Any]:
    try:
        details = json.loads(item.details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    return {
        "id": item.id,
        "event_type": item.event_type,
        "level": item.level,
        "message": item.message,
        "path": item.path,
        "method": item.method,
        "status_code": item.status_code,
        "duration_ms": item.duration_ms,
        "details": details,
        "created_at": item.created_at.isoformat(),
    }


def llm_metric_payload(item: LlmCallMetric) -> dict[str, Any]:
    return {
        "id": item.id,
        "operation": item.operation,
        "platform": item.platform,
        "model": item.model,
        "success": bool(item.success),
        "latency_ms": item.latency_ms,
        "prompt_tokens": item.prompt_tokens,
        "completion_tokens": item.completion_tokens,
        "total_tokens": item.total_tokens,
        "estimated_cost_usd": item.estimated_cost_usd,
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat(),
    }


def observability_summary(session: Session, hours: int = 24, limit: int = 50) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(hours=max(1, min(int(hours or 24), 24 * 30)))

    request_count = session.scalar(
        select(func.count()).select_from(ObservabilityLog).where(ObservabilityLog.created_at >= since)
    ) or 0
    error_count = session.scalar(
        select(func.count())
        .select_from(ObservabilityLog)
        .where(ObservabilityLog.created_at >= since, ObservabilityLog.status_code >= 500)
    ) or 0
    avg_request_latency = session.scalar(
        select(func.avg(ObservabilityLog.duration_ms)).where(ObservabilityLog.created_at >= since)
    ) or 0

    llm_count = session.scalar(
        select(func.count()).select_from(LlmCallMetric).where(LlmCallMetric.created_at >= since)
    ) or 0
    llm_success = session.scalar(
        select(func.count())
        .select_from(LlmCallMetric)
        .where(LlmCallMetric.created_at >= since, LlmCallMetric.success == 1)
    ) or 0
    avg_llm_latency = session.scalar(
        select(func.avg(LlmCallMetric.latency_ms)).where(LlmCallMetric.created_at >= since)
    ) or 0
    total_tokens = session.scalar(
        select(func.sum(LlmCallMetric.total_tokens)).where(LlmCallMetric.created_at >= since)
    ) or 0
    cost_values = list(
        session.scalars(select(LlmCallMetric.estimated_cost_usd).where(LlmCallMetric.created_at >= since)).all()
    )

    llm_metrics = list(
        session.scalars(
            select(LlmCallMetric).where(LlmCallMetric.created_at >= since).order_by(LlmCallMetric.created_at.desc()).limit(limit)
        ).all()
    )
    recent_logs = list(
        session.scalars(
            select(ObservabilityLog)
            .where(ObservabilityLog.created_at >= since)
            .order_by(ObservabilityLog.created_at.desc())
            .limit(limit)
        ).all()
    )
    total_cost = sum((Decimal(value or "0") for value in cost_values), Decimal("0"))

    return {
        "window_hours": hours,
        "requests": {
            "count": request_count,
            "error_count": error_count,
            "avg_latency_ms": round(float(avg_request_latency), 2),
        },
        "llm": {
            "count": llm_count,
            "success_count": llm_success,
            "error_count": max(0, llm_count - llm_success),
            "avg_latency_ms": round(float(avg_llm_latency), 2),
            "total_tokens": int(total_tokens or 0),
            "estimated_cost_usd": str(total_cost.quantize(Decimal("0.000001"))),
        },
        "recent_logs": [log_payload(item) for item in recent_logs],
        "recent_llm_calls": [llm_metric_payload(item) for item in llm_metrics],
    }
