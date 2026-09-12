"""End-to-end eval pipeline.

For every incident in the eval set (data/sample_incidents/*/ground_truth.json):
1. Run the full investigation (multi-agent workflow, same code path as the API).
2. Score:
   - Retrieval Recall@5: did the knowledge-base retrieval surface the
     ground-truth-relevant runbook/architecture/historical-incident sections?
   - Citation correctness: are the citations in the final report actually
     real citations returned by a tool call (not hallucinated)?
   - RCA accuracy: LLM-judged similarity between the produced root cause and
     the ground-truth root cause.

Usage:
    python -m app.eval.run_eval
"""
from __future__ import annotations

import asyncio
import statistics

from app.agents.orchestrator import investigate, try_parse_json
from app.eval.dataset import load_eval_incidents
from app.eval.metrics import citation_correctness, llm_judge_rca_accuracy, recall_at_k, CITATION_RE


async def run_one(incident) -> dict:
    result = await investigate(incident.incident_id, incident.summary)
    report = try_parse_json(result.verified_report) or {}
    root_cause = report.get("root_cause", result.verified_report) if isinstance(report, dict) else result.verified_report

    # Collect every citation string that was actually returned by a tool call
    # across the specialist findings, so we can check the final report isn't
    # citing evidence that was never retrieved.
    valid_citations = set()
    for finding in result.specialist_findings:
        valid_citations.update(m.group(0) for m in CITATION_RE.finditer(finding.findings))

    recall = recall_at_k(incident, k=5)
    citation_score = citation_correctness(result.verified_report, valid_citations)
    judge = llm_judge_rca_accuracy(incident, root_cause)

    return {
        "incident_id": incident.incident_id,
        "recall_at_5": recall,
        "citation_correctness": citation_score,
        "rca_accuracy": judge.score,
        "judge_reasoning": judge.reasoning,
    }


async def main() -> None:
    incidents = load_eval_incidents()
    if not incidents:
        print("No eval incidents found. Run scripts/seed_data.py and ensure "
              "data/sample_incidents/*/ground_truth.json exist.")
        return

    print(f"Running eval over {len(incidents)} incident(s)...\n")
    results = []
    for incident in incidents:
        print(f"  -> investigating {incident.incident_id} ...")
        results.append(await run_one(incident))

    print("\n=== Per-incident results ===")
    for r in results:
        print(f"{r['incident_id']}: recall@5={r['recall_at_5']:.2f} "
              f"citation_correctness={r['citation_correctness']:.2f} "
              f"rca_accuracy={r['rca_accuracy']:.2f}  ({r['judge_reasoning']})")

    def _mean(key: str) -> float:
        vals = [r[key] for r in results if r[key] == r[key]]  # filter NaN
        return statistics.mean(vals) if vals else float("nan")

    print("\n=== Aggregate ===")
    print(f"Mean Recall@5:            {_mean('recall_at_5'):.3f}")
    print(f"Mean Citation Correctness: {_mean('citation_correctness'):.3f}")
    print(f"Mean RCA Accuracy:         {_mean('rca_accuracy'):.3f}")


if __name__ == "__main__":
    asyncio.run(main())
