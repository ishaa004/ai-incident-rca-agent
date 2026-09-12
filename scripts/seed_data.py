"""Seeds local Postgres for the demo/eval workflow, without needing Kafka:

1. Ingests data/runbooks, data/architecture_docs, data/historical_incidents
   into the pgvector knowledge_chunks table (via app.rag.ingest).
2. Loads every incident directory under data/sample_incidents/<incident_id>/
   (logs.jsonl, metrics.json, traces.json, deployments.json) into the raw
   evidence tables, so the specialist agents' tools have something to query.

Usage:
    python scripts/seed_data.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.db import DeploymentEvent, LogEvent, MetricPoint, TraceSpan, get_session, init_db
from app.rag.ingest import ingest_all

SAMPLE_INCIDENTS_DIR = Path("data/sample_incidents")


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def seed_incident(incident_dir: Path) -> dict:
    incident_id = incident_dir.name
    session = get_session()
    counts = {"logs": 0, "metrics": 0, "traces": 0, "deployments": 0}

    try:
        logs_path = incident_dir / "logs.jsonl"
        if logs_path.exists():
            for line in logs_path.read_text().splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                session.add(LogEvent(
                    incident_id=incident_id, service=rec["service"], level=rec["level"],
                    message=rec["message"], timestamp=_parse_ts(rec["timestamp"]),
                    raw=rec.get("raw", {}),
                ))
                counts["logs"] += 1

        metrics_path = incident_dir / "metrics.json"
        if metrics_path.exists():
            for rec in json.loads(metrics_path.read_text()):
                session.add(MetricPoint(
                    incident_id=incident_id, service=rec["service"], metric_name=rec["metric_name"],
                    value=rec["value"], unit=rec.get("unit", ""), timestamp=_parse_ts(rec["timestamp"]),
                ))
                counts["metrics"] += 1

        traces_path = incident_dir / "traces.json"
        if traces_path.exists():
            for rec in json.loads(traces_path.read_text()):
                session.add(TraceSpan(
                    incident_id=incident_id, trace_id=rec["trace_id"], span_id=rec["span_id"],
                    parent_span_id=rec.get("parent_span_id", ""), service=rec["service"],
                    operation=rec["operation"], duration_ms=rec["duration_ms"], status=rec["status"],
                    timestamp=_parse_ts(rec["timestamp"]),
                ))
                counts["traces"] += 1

        deploys_path = incident_dir / "deployments.json"
        if deploys_path.exists():
            for rec in json.loads(deploys_path.read_text()):
                session.add(DeploymentEvent(
                    incident_id=incident_id, service=rec["service"], version=rec["version"],
                    description=rec.get("description", ""), timestamp=_parse_ts(rec["timestamp"]),
                ))
                counts["deployments"] += 1

        session.commit()
    finally:
        session.close()

    return counts


def main() -> None:
    print("Initializing DB (pgvector extension + tables)...")
    init_db()

    print("Ingesting knowledge base (runbooks / architecture docs / historical incidents)...")
    kb_counts = ingest_all()
    print(f"  -> {kb_counts}")

    if not SAMPLE_INCIDENTS_DIR.exists():
        print("No data/sample_incidents directory found, skipping evidence seeding.")
        return

    for incident_dir in sorted(p for p in SAMPLE_INCIDENTS_DIR.iterdir() if p.is_dir()):
        print(f"Seeding evidence for {incident_dir.name}...")
        counts = seed_incident(incident_dir)
        print(f"  -> {counts}")

    print("Done.")


if __name__ == "__main__":
    main()
