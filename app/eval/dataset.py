"""Loads the set of simulated incidents used for evaluation. Each incident
directory under data/sample_incidents/<id>/ must contain a ground_truth.json
with the expected root cause, the knowledge-base sections a good retrieval
pass should surface, and the key evidence signals a good RCA should mention.

To scale this to "100+ simulated production incidents" as in the project
description, run scripts/generate_synthetic_incidents.py, which procedurally
generates additional incident directories in this same shape (varying the
failure mode: pool exhaustion, downstream timeout, bad deploy, etc.) so the
eval set grows without hand-writing each one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SAMPLE_INCIDENTS_DIR = Path("data/sample_incidents")


@dataclass
class EvalIncident:
    incident_id: str
    summary: str
    expected_root_cause: str
    relevant_knowledge_sections: list[str]
    expected_evidence_signals: list[str]


def load_eval_incidents() -> list[EvalIncident]:
    incidents = []
    if not SAMPLE_INCIDENTS_DIR.exists():
        return incidents

    for incident_dir in sorted(p for p in SAMPLE_INCIDENTS_DIR.iterdir() if p.is_dir()):
        gt_path = incident_dir / "ground_truth.json"
        if not gt_path.exists():
            continue
        gt = json.loads(gt_path.read_text())
        incidents.append(EvalIncident(
            incident_id=gt["incident_id"],
            summary=gt["summary"],
            expected_root_cause=gt["expected_root_cause"],
            relevant_knowledge_sections=gt.get("relevant_knowledge_sections", []),
            expected_evidence_signals=gt.get("expected_evidence_signals", []),
        ))
    return incidents
