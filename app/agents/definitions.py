from agents import Agent

from app.agents.tools import (
    search_deployments,
    search_knowledge_base,
    search_logs,
    search_metrics,
    search_traces,
)
from app.config import settings

MODEL = settings.openai_model

# ---------------------------------------------------------------------------
# Specialist investigation agents. Each has a narrow toolset and a narrow
# prompt so it stays focused on its evidence domain; the orchestrator runs
# these concurrently rather than having one agent serially page through
# every tool.
# ---------------------------------------------------------------------------

log_agent = Agent(
    name="LogInvestigator",
    model=MODEL,
    instructions=(
        "You investigate application logs for a production incident. Use search_logs to find "
        "ERROR/WARN entries, stack traces, and anomalous messages around the incident window. "
        "Cross-check against search_deployments to see if a recent release correlates with the "
        "first error. Return a concise list of the most suspicious log findings, each with its "
        "exact `citation` string copied verbatim from the tool result — never invent a citation "
        "and never paraphrase away the citation. If nothing suspicious is found, say so plainly."
    ),
    tools=[search_logs, search_deployments],
)

metrics_agent = Agent(
    name="MetricsInvestigator",
    model=MODEL,
    instructions=(
        "You investigate system metrics for a production incident. Use search_metrics to pull "
        "time series for latency, error rate, saturation (CPU/memory/connection pool), and "
        "throughput. Identify the point where the metric deviates from baseline and describe the "
        "shape of the deviation (sudden step vs gradual climb). Cite every claim with the exact "
        "`citation` string from the tool result."
    ),
    tools=[search_metrics, search_deployments],
)

trace_agent = Agent(
    name="TraceInvestigator",
    model=MODEL,
    instructions=(
        "You investigate distributed traces for a production incident. Use search_traces to find "
        "the slowest and/or error-status spans, and identify which downstream service or "
        "operation is the bottleneck or failure point in the request path. Cite every claim with "
        "the exact `citation` string from the tool result."
    ),
    tools=[search_traces],
)

knowledge_agent = Agent(
    name="KnowledgeInvestigator",
    model=MODEL,
    instructions=(
        "You check whether the incident's symptoms match a documented known-failure-mode in "
        "runbooks, a described component in architecture docs, or a similar past incident. Use "
        "search_knowledge_base with a query built from the symptom description. Cite every claim "
        "with the exact `citation` string from the tool result. If nothing relevant is found, say so."
    ),
    tools=[search_knowledge_base],
)

verification_agent = Agent(
    name="VerificationAgent",
    model=MODEL,
    instructions=(
        "You are given a draft RCA report plus the raw evidence blocks (with citations) gathered "
        "by the specialist agents. Check every factual claim in the draft against the evidence: "
        "\n1. Does a citation exist in the evidence for each claim?\n"
        "2. Does the cited evidence actually support the claim (not just superficially related)?\n"
        "3. Is the proposed root cause the *best-supported* explanation, or is there stronger "
        "evidence elsewhere pointing at a different cause?\n"
        "Return a verified report: for each claim mark it VERIFIED, UNSUPPORTED (remove or flag "
        "it), or CONTRADICTED (evidence points the other way — explain). Do not add new claims "
        "that aren't grounded in the provided evidence."
    ),
    tools=[],
)

# ---------------------------------------------------------------------------
# Orchestrator: fans out to the four specialists (run concurrently by the
# calling code, see orchestrator.py), then synthesizes their findings into a
# single draft RCA, before handing that draft to the verification agent.
# ---------------------------------------------------------------------------

synthesis_agent = Agent(
    name="RCASynthesizer",
    model=MODEL,
    instructions=(
        "You are given findings from four specialist investigators (logs, metrics, traces, "
        "knowledge base) for one production incident. Synthesize them into a single root-cause "
        "analysis with this structure:\n"
        "- `summary`: one paragraph, what happened\n"
        "- `root_cause`: the single most-supported root cause, one or two sentences\n"
        "- `contributing_factors`: list of secondary factors, if any\n"
        "- `timeline`: ordered list of {time, event} entries built from the evidence\n"
        "- `evidence`: list of {claim, citation} pairs — every claim must carry a citation string "
        "copied exactly from one of the specialist findings\n"
        "- `remediation`: list of concrete, actionable next steps\n"
        "- `confidence`: high|medium|low, based on how directly the evidence supports the root cause\n"
        "Never state a claim without a citation. If the specialists disagree or evidence is "
        "inconclusive, say so and lower the confidence rather than guessing."
    ),
    tools=[],
)
