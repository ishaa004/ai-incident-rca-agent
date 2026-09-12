"""Consumes the `incident.events` Kafka topic and writes log/metric/trace/
deployment events into their respective Postgres tables, so the agent tools
in app/agents/tools.py can query them during an investigation.

This is optional for local development/demo — scripts/seed_data.py loads the
same shape of data directly from data/sample_incidents/ without needing a
broker running. Run this module directly against a real cluster to ingest
live production telemetry:

    python -m app.ingestion.kafka_consumer

Expected message value: JSON matching one of the models in event_schemas.py,
discriminated by the `type` field (log | metric | trace | deployment).
"""
from __future__ import annotations

import json
import logging

from confluent_kafka import Consumer

from app.config import settings
from app.db import DeploymentEvent, LogEvent, MetricPoint, TraceSpan, get_session
from app.ingestion.event_schemas import DeploymentEventIn, LogEventIn, MetricEventIn, TraceEventIn

logger = logging.getLogger("rca_agent.kafka_consumer")

HANDLERS = {
    "log": (LogEventIn, LogEvent, lambda m: dict(
        incident_id=m.incident_id, service=m.service, level=m.level,
        message=m.message, timestamp=m.timestamp, raw=m.raw,
    )),
    "metric": (MetricEventIn, MetricPoint, lambda m: dict(
        incident_id=m.incident_id, service=m.service, metric_name=m.metric_name,
        value=m.value, unit=m.unit, timestamp=m.timestamp,
    )),
    "trace": (TraceEventIn, TraceSpan, lambda m: dict(
        incident_id=m.incident_id, trace_id=m.trace_id, span_id=m.span_id,
        parent_span_id=m.parent_span_id, service=m.service, operation=m.operation,
        duration_ms=m.duration_ms, status=m.status, timestamp=m.timestamp,
    )),
    "deployment": (DeploymentEventIn, DeploymentEvent, lambda m: dict(
        incident_id=m.incident_id, service=m.service, version=m.version,
        description=m.description, timestamp=m.timestamp,
    )),
}


def handle_message(raw_value: bytes) -> None:
    payload = json.loads(raw_value)
    event_type = payload.get("type")
    handler = HANDLERS.get(event_type)
    if not handler:
        logger.warning("Unknown event type: %s", event_type)
        return

    model_cls, table_cls, to_kwargs = handler
    model = model_cls(**payload)

    session = get_session()
    try:
        session.add(table_cls(**to_kwargs(model)))
        session.commit()
    finally:
        session.close()


def run_consumer() -> None:
    consumer = Consumer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": settings.kafka_consumer_group,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([settings.kafka_topic_events])
    logger.info("Listening on topic %s ...", settings.kafka_topic_events)

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("Kafka error: %s", msg.error())
                continue
            try:
                handle_message(msg.value())
            except Exception:
                logger.exception("Failed to process message")
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


if __name__ == "__main__":
    logging.basicConfig(level=settings.log_level)
    run_consumer()
