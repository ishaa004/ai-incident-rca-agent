from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from agents import Runner

from app.agents.definitions import (
    knowledge_agent,
    log_agent,
    metrics_agent,
    synthesis_agent,
    trace_agent,
    verification_agent,
)
from app.cache import set_investigation_state


@dataclass
class SpecialistResult:
    name: str
    findings: str
    error: str | None = None


@dataclass
class InvestigationResult:
    incident_id: str
    specialist_findings: list[SpecialistResult] = field(default_factory=list)
    draft_report: str = ""
    verified_report: str = ""


async def _run_specialist(agent, name: str, prompt: str) -> SpecialistResult:
    try:
        result = await Runner.run(agent, prompt)
        return SpecialistResult(name=name, findings=result.final_output)
    except Exception as exc:  # noqa: BLE001 - surface but don't kill the whole investigation
        return SpecialistResult(name=name, findings="", error=str(exc))


async def investigate(incident_id: str, summary: str) -> InvestigationResult:
    """Runs the full multi-agent investigation workflow:
    1. Fan out to log/metrics/trace/knowledge specialists in parallel
    2. Synthesize their findings into a draft RCA
    3. Verify the draft against the raw evidence, catching unsupported claims
    """
    set_investigation_state(incident_id, {"status": "gathering_evidence"})

    specialist_prompt = (
        f"Incident ID: {incident_id}\n"
        f"Reported symptom summary: {summary}\n\n"
        "Investigate this incident within your area of expertise and report your findings."
    )

    specialists = [
        (log_agent, "LogInvestigator"),
        (metrics_agent, "MetricsInvestigator"),
        (trace_agent, "TraceInvestigator"),
        (knowledge_agent, "KnowledgeInvestigator"),
    ]

    results = await asyncio.gather(
        *[_run_specialist(agent, name, specialist_prompt) for agent, name in specialists]
    )

    set_investigation_state(incident_id, {"status": "synthesizing"})

    findings_blob = "\n\n".join(
        f"### {r.name} findings:\n{r.findings if not r.error else f'[ERROR: {r.error}]'}" for r in results
    )
    synthesis_prompt = (
        f"Incident ID: {incident_id}\n"
        f"Reported symptom summary: {summary}\n\n"
        f"Specialist findings:\n{findings_blob}\n\n"
        "Produce the RCA report as described in your instructions, as a single JSON object."
    )
    draft = await Runner.run(synthesis_agent, synthesis_prompt)
    draft_report = draft.final_output

    set_investigation_state(incident_id, {"status": "verifying"})

    verification_prompt = (
        f"Draft RCA report:\n{draft_report}\n\n"
        f"Raw specialist evidence (for cross-checking citations):\n{findings_blob}\n\n"
        "Verify every claim as instructed and return the final, corrected JSON report — same "
        "structure as the draft, but with any UNSUPPORTED claims removed and any CONTRADICTED "
        "claims corrected. Add a `verification_notes` field summarizing what was checked."
    )
    verified = await Runner.run(verification_agent, verification_prompt)
    verified_report = verified.final_output

    set_investigation_state(incident_id, {"status": "complete"})

    return InvestigationResult(
        incident_id=incident_id,
        specialist_findings=list(results),
        draft_report=draft_report,
        verified_report=verified_report,
    )


def try_parse_json(text: str) -> dict | None:
    """The synthesis/verification agents are prompted to return JSON, but LLMs
    sometimes wrap it in prose or code fences — this strips common wrappers
    before giving up and returning None (caller falls back to raw text)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None
