"""Procedurally generates additional simulated incidents (logs/metrics/
traces/deployments + ground_truth.json) so the eval set can scale to 100+
incidents without hand-writing each one, as called for in the project scope.

Each incident is drawn from one of a few failure-mode templates (DB pool
exhaustion, downstream timeout cascade, bad deploy/config error) with
randomized service names, timestamps, and magnitudes, so retrieval and RCA
accuracy are tested against varied but realistic surface forms of a small
set of known root causes.

Usage:
    python scripts/generate_synthetic_incidents.py --count 100
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT_DIR = Path("data/sample_incidents")

SERVICES = ["checkout-service", "orders-service", "cart-service", "billing-service", "shipping-service"]
DOWNSTREAM = ["payment-gateway", "inventory-service", "tax-service", "fraud-check-service"]

TEMPLATES = ["db_pool_exhaustion", "downstream_timeout_cascade", "bad_deploy_config_error"]


def gen_db_pool_exhaustion(idx: int, service: str, base: datetime) -> tuple[list, list, list, list, dict]:
    version = f"v{random.randint(1,4)}.{random.randint(0,20)}.{random.randint(0,9)}"
    deployments = [{"service": service, "version": version,
                    "description": "Add background task without proper session cleanup.",
                    "timestamp": base.isoformat()}]
    metrics, logs, traces = [], [], []
    for i in range(15):
        t = base + timedelta(minutes=i)
        pool = min(4 + max(0, i - 1) * 2, 20)
        metrics.append({"service": service, "metric_name": "db_pool_in_use", "value": pool,
                         "unit": "connections", "timestamp": t.isoformat()})
        metrics.append({"service": service, "metric_name": "p99_latency_ms",
                         "value": 120 if i < 2 else 120 + (i - 1) * 200, "unit": "ms", "timestamp": t.isoformat()})
        if i >= 3:
            logs.append({"service": service, "level": "ERROR",
                         "message": f"TimeoutError: QueuePool limit of size 20 overflow 0 reached (attempt {i})",
                         "timestamp": t.isoformat(), "raw": {}})
    summary = f"{service} p99 latency spike and 5xx errors after deploy"
    root_cause = (f"The {version} deploy on {service} introduced a code path that leaks DB sessions, "
                  f"exhausting the connection pool and causing request timeouts and 5xx errors.")
    return logs, metrics, traces, deployments, {"summary": summary, "expected_root_cause": root_cause}


def gen_downstream_timeout(idx: int, service: str, base: datetime) -> tuple[list, list, list, list, dict]:
    downstream = random.choice(DOWNSTREAM)
    metrics, logs, traces = [], [], []
    for i in range(15):
        t = base + timedelta(minutes=i)
        latency = 150 if i < 2 else 150 + (i - 1) * 1800
        metrics.append({"service": downstream, "metric_name": "p99_latency_ms", "value": latency,
                         "unit": "ms", "timestamp": t.isoformat()})
        metrics.append({"service": service, "metric_name": "p99_latency_ms", "value": latency + 50,
                         "unit": "ms", "timestamp": t.isoformat()})
        if i >= 3:
            traces.append({"trace_id": f"trace-{idx}-{i}", "span_id": f"s-{idx}-{i}", "parent_span_id": "",
                            "service": downstream, "operation": "handle_request", "duration_ms": latency,
                            "status": "ok", "timestamp": t.isoformat()})
    summary = f"{service} latency spike, no recent deploy, errors correlate with {downstream} slowness"
    root_cause = (f"{downstream} became slow (elevated latency, not errors), and {service}'s call to it "
                  f"had too generous a timeout, so requests piled up and saturated {service} itself.")
    return logs, metrics, traces, [], {"summary": summary, "expected_root_cause": root_cause}


def gen_bad_deploy(idx: int, service: str, base: datetime) -> tuple[list, list, list, list, dict]:
    version = f"v{random.randint(1,4)}.{random.randint(0,20)}.{random.randint(0,9)}"
    deployments = [{"service": service, "version": version,
                    "description": "Config change: default feature flag value updated.",
                    "timestamp": base.isoformat()}]
    metrics, logs, traces = [], [], []
    for i in range(10):
        t = base + timedelta(minutes=i)
        err = 2.0 if i == 0 else 95.0
        metrics.append({"service": service, "metric_name": "error_rate_pct", "value": err,
                         "unit": "pct", "timestamp": t.isoformat()})
        if i >= 1:
            logs.append({"service": service, "level": "ERROR",
                         "message": "KeyError: 'FEATURE_FLAG_NEW_PRICING_ENGINE' missing from config",
                         "timestamp": t.isoformat(), "raw": {}})
    summary = f"{service} error rate jumped to near 100% immediately after deploy"
    root_cause = (f"The {version} deploy on {service} shipped a config change referencing a feature flag "
                  f"that wasn't defined in the runtime environment, causing immediate near-total failure.")
    return logs, metrics, traces, deployments, {"summary": summary, "expected_root_cause": root_cause}


GENERATORS = {
    "db_pool_exhaustion": gen_db_pool_exhaustion,
    "downstream_timeout_cascade": gen_downstream_timeout,
    "bad_deploy_config_error": gen_bad_deploy,
}


def main(count: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1)

    for i in range(count):
        template = random.choice(TEMPLATES)
        service = random.choice(SERVICES)
        base = start + timedelta(days=i, hours=random.randint(0, 23), minutes=random.randint(0, 59))
        incident_id = f"synthetic_{template}_{i:04d}"

        logs, metrics, traces, deployments, meta = GENERATORS[template](i, service, base)

        incident_dir = OUT_DIR / incident_id
        incident_dir.mkdir(parents=True, exist_ok=True)

        with open(incident_dir / "logs.jsonl", "w") as f:
            for l in logs:
                f.write(json.dumps(l) + "\n")
        with open(incident_dir / "metrics.json", "w") as f:
            json.dump(metrics, f)
        with open(incident_dir / "traces.json", "w") as f:
            json.dump(traces, f)
        with open(incident_dir / "deployments.json", "w") as f:
            json.dump(deployments, f)
        with open(incident_dir / "ground_truth.json", "w") as f:
            json.dump({
                "incident_id": incident_id,
                "summary": meta["summary"],
                "expected_root_cause": meta["expected_root_cause"],
                "relevant_knowledge_sections": [],  # fill in manually for a curated subset if desired
                "expected_evidence_signals": [],
            }, f, indent=2)

    print(f"Generated {count} synthetic incidents under {OUT_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    main(args.count)
