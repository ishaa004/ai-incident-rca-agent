from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from app.config import settings
from app.eval.dataset import EvalIncident
from app.rag.retriever import retrieve

_client = OpenAI(api_key=settings.openai_api_key)

CITATION_RE = re.compile(r"\b(log|metric|trace|deploy|runbook|architecture_doc|historical_incident):[^\s,;\]\)]+")


def recall_at_k(incident: EvalIncident, k: int = 5) -> float:
    """Fraction of the ground-truth relevant knowledge-base sections that
    appear in the top-k retrieved chunks for this incident's summary query."""
    if not incident.relevant_knowledge_sections:
        return float("nan")

    retrieved = retrieve(incident.summary, top_k=k)
    retrieved_citations = {c.citation() for c in retrieved}

    hits = sum(1 for expected in incident.relevant_knowledge_sections if expected in retrieved_citations)
    return hits / len(incident.relevant_knowledge_sections)


def citation_correctness(report_text: str, valid_citations: set[str]) -> float:
    """Fraction of citation-like strings found in the report that actually
    correspond to a citation string returned by a tool call during the
    investigation (i.e. not hallucinated)."""
    found_full = set(m.group(0) for m in CITATION_RE.finditer(report_text))
    if not found_full:
        return float("nan")
    correct = sum(1 for c in found_full if c in valid_citations)
    return correct / len(found_full)


@dataclass
class JudgeResult:
    score: float  # 0-1
    reasoning: str


def llm_judge_rca_accuracy(incident: EvalIncident, produced_root_cause: str) -> JudgeResult:
    """Uses an LLM-as-judge to score how well the produced root cause matches
    the ground-truth root cause, since exact string match is too strict for
    natural-language RCA text."""
    prompt = f"""You are grading a root-cause-analysis output against a known ground truth.

Ground truth root cause:
{incident.expected_root_cause}

Produced root cause:
{produced_root_cause}

Score how well the produced root cause captures the SAME underlying cause as
the ground truth (not just similar symptoms). Respond with ONLY a JSON object:
{{"score": <float 0.0-1.0>, "reasoning": "<one sentence>"}}

Scoring guide: 1.0 = same root cause, correctly identified. 0.5 = partially
correct or identifies a contributing factor but misses the primary cause.
0.0 = wrong or unrelated cause."""

    resp = _client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    try:
        data = json.loads(text)
        return JudgeResult(score=float(data["score"]), reasoning=data.get("reasoning", ""))
    except (json.JSONDecodeError, KeyError, ValueError):
        return JudgeResult(score=float("nan"), reasoning=f"Failed to parse judge output: {text}")
