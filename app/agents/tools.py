"""Function tools exposed to the specialist agents via the OpenAI Agents SDK.

Every tool returns evidence in a uniform shape: a list of dicts each carrying
a `citation` field, so the orchestrator/verification agents can trace every
claim in the final RCA back to a specific log line, metric window, trace
span, or runbook section.
"""
from __future__ import annotations

from datetime import datetime

from agents import function_tool
from sqlalchemy import select

from app.cache import cache_tool_result, get_cached_tool_result
from app.db import DeploymentEvent, LogEvent, MetricPoint, TraceSpan, get_session
from app.rag.retriever import retrieve


def _cache_key(name: str, **kwargs) -> str:
    parts = "|".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return f"tool:{name}:{parts}"


@function_tool
def search_logs(incident_id: str, keyword: str = "", level: str = "", limit: int = 20) -> list[dict]:
    """Search log events for an incident, optionally filtered by keyword substring
    and/or log level (INFO/WARN/ERROR). Returns the most recent matching lines
    with a citation pointing at the exact log timestamp and service."""
    cache_key = _cache_key("search_logs", incident_id=incident_id, keyword=keyword, level=level, limit=limit)
    if cached := get_cached_tool_result(cache_key):
        return cached

    session = get_session()
    try:
        stmt = select(LogEvent).where(LogEvent.incident_id == incident_id)
        if keyword:
            stmt = stmt.where(LogEvent.message.ilike(f"%{keyword}%"))
        if level:
            stmt = stmt.where(LogEvent.level == level.upper())
        stmt = stmt.order_by(LogEvent.timestamp.desc()).limit(limit)
        rows = session.execute(stmt).scalars().all()

        result = [
            {
                "service": r.service,
                "level": r.level,
                "message": r.message,
                "timestamp": r.timestamp.isoformat(),
                "citation": f"log:{r.service}@{r.timestamp.isoformat()}",
            }
            for r in rows
        ]
        cache_tool_result(cache_key, result)
        return result
    finally:
        session.close()


@function_tool
def search_metrics(incident_id: str, metric_name: str = "", service: str = "") -> list[dict]:
    """Fetch metric time-series points for an incident, optionally filtered by
    metric name (e.g. 'p99_latency_ms', 'error_rate') and/or service. Returns
    points ordered by time with a citation pointing at the metric+timestamp."""
    cache_key = _cache_key("search_metrics", incident_id=incident_id, metric_name=metric_name, service=service)
    if cached := get_cached_tool_result(cache_key):
        return cached

    session = get_session()
    try:
        stmt = select(MetricPoint).where(MetricPoint.incident_id == incident_id)
        if metric_name:
            stmt = stmt.where(MetricPoint.metric_name == metric_name)
        if service:
            stmt = stmt.where(MetricPoint.service == service)
        stmt = stmt.order_by(MetricPoint.timestamp.asc())
        rows = session.execute(stmt).scalars().all()

        result = [
            {
                "service": r.service,
                "metric_name": r.metric_name,
                "value": r.value,
                "unit": r.unit,
                "timestamp": r.timestamp.isoformat(),
                "citation": f"metric:{r.service}:{r.metric_name}@{r.timestamp.isoformat()}",
            }
            for r in rows
        ]
        cache_tool_result(cache_key, result)
        return result
    finally:
        session.close()


@function_tool
def search_traces(incident_id: str, service: str = "", min_duration_ms: float = 0, status: str = "") -> list[dict]:
    """Fetch distributed trace spans for an incident, optionally filtered by
    service, a minimum duration threshold (to surface slow spans), and/or
    status (ok/error). Returns spans with a citation pointing at trace+span id."""
    cache_key = _cache_key(
        "search_traces", incident_id=incident_id, service=service, min_duration_ms=min_duration_ms, status=status
    )
    if cached := get_cached_tool_result(cache_key):
        return cached

    session = get_session()
    try:
        stmt = select(TraceSpan).where(TraceSpan.incident_id == incident_id)
        if service:
            stmt = stmt.where(TraceSpan.service == service)
        if min_duration_ms:
            stmt = stmt.where(TraceSpan.duration_ms >= min_duration_ms)
        if status:
            stmt = stmt.where(TraceSpan.status == status)
        stmt = stmt.order_by(TraceSpan.duration_ms.desc())
        rows = session.execute(stmt).scalars().all()

        result = [
            {
                "trace_id": r.trace_id,
                "span_id": r.span_id,
                "service": r.service,
                "operation": r.operation,
                "duration_ms": r.duration_ms,
                "status": r.status,
                "timestamp": r.timestamp.isoformat(),
                "citation": f"trace:{r.trace_id}/{r.span_id}",
            }
            for r in rows
        ]
        cache_tool_result(cache_key, result)
        return result
    finally:
        session.close()


@function_tool
def search_deployments(incident_id: str, service: str = "") -> list[dict]:
    """Fetch deployment events around an incident, optionally filtered by
    service. Useful for correlating a symptom onset with a recent release."""
    session = get_session()
    try:
        stmt = select(DeploymentEvent).where(DeploymentEvent.incident_id == incident_id)
        if service:
            stmt = stmt.where(DeploymentEvent.service == service)
        stmt = stmt.order_by(DeploymentEvent.timestamp.desc())
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "service": r.service,
                "version": r.version,
                "description": r.description,
                "timestamp": r.timestamp.isoformat(),
                "citation": f"deploy:{r.service}:{r.version}@{r.timestamp.isoformat()}",
            }
            for r in rows
        ]
    finally:
        session.close()


@function_tool
def search_knowledge_base(query: str, source_types: list[str] | None = None, top_k: int = 5) -> list[dict]:
    """Semantic search over runbooks, architecture docs, and historical
    incident writeups. Use this to check whether the current symptoms match
    a documented known-failure-mode or a past incident. Returns chunks with
    a `citation` pointing at the exact document + section."""
    chunks = retrieve(query, top_k=top_k, source_types=source_types)
    return [
        {
            "source_type": c.source_type,
            "title": c.title,
            "section": c.section,
            "content": c.content,
            "citation": c.citation(),
            "similarity_score": round(1 - c.score, 4),
        }
        for c in chunks
    ]
