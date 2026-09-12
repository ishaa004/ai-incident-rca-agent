# AI Production Incident RCA Agent

An AI-powered incident investigation agent that analyzes application logs, metrics, traces,
and deployment events to generate evidence-backed root-cause analyses (RCAs) and remediation
recommendations — with source citations pulled from runbooks, architecture docs, and past
incidents via RAG.

## Architecture

```
                         ┌─────────────────────┐
   logs / metrics /      │   Kafka (events)     │
   traces / deploys ────▶│  incident.events     │
                         └──────────┬───────────┘
                                    │ consumer
                                    ▼
                         ┌─────────────────────┐
                         │  Postgres + pgvector │◀──── ingest runbooks/
                         │  (evidence store +   │      architecture docs/
                         │   embeddings)        │      historical incidents
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Redis              │  investigation state,
                         │  (state/cache)        │  dedupe, rate limiting
                         └──────────┬───────────┘
                                    │
                                    ▼
     ┌──────────────────────────────────────────────────────┐
     │                Orchestrator Agent                     │
     │  fans out to specialist agents in parallel, then       │
     │  synthesizes + verifies                                │
     └───┬────────────┬────────────┬────────────┬────────────┘
         ▼             ▼            ▼            ▼
     Log Agent   Metrics Agent  Trace Agent   RAG Retriever
         │             │            │            │
         └─────────────┴────────────┴────────────┘
                        ▼
              Verification Agent
              (checks each claim in the draft RCA is
               backed by cited evidence, flags gaps)
                        ▼
              Final RCA report (JSON + Markdown)
              with inline citations to logs/metrics/
              traces/runbook sections
```

## Stack

- **FastAPI** — HTTP API (`/incidents/investigate`, `/incidents/{id}`, `/eval/run`)
- **OpenAI Agents SDK** — orchestrator + specialist agents, handoffs, tool calls
- **Postgres + pgvector** — evidence store (runbooks, arch docs, historical incidents) with
  semantic search
- **Redis** — investigation run state, caching of tool results
- **Kafka** — ingestion of log/metric/trace/deployment events (optional for local dev; a
  file-based loader is provided for sample data so you don't need Kafka running to try it out)
- **Docker Compose** — one command to bring up Postgres, Redis, Kafka, and the API

## Repo layout

```
app/
  main.py                 FastAPI app + routes
  config.py                settings (env vars)
  db.py                    SQLAlchemy models + session (pgvector columns)
  cache.py                 Redis client + investigation state helpers
  agents/
    tools.py               function tools shared by agents (search_logs, search_metrics, ...)
    definitions.py         Agent() definitions: log, metrics, trace, verification, orchestrator
    orchestrator.py         runs the parallel investigation + synthesis + verification
  rag/
    ingest.py               chunk + embed runbooks/docs/incidents into pgvector
    retriever.py             semantic search with citations
  ingestion/
    kafka_consumer.py       consumes incident.events topic into Postgres
    event_schemas.py        pydantic event models
  eval/
    dataset.py               loads/generates simulated incidents for eval
    metrics.py                Recall@5, citation correctness, RCA accuracy (LLM-judged)
    run_eval.py               CLI: runs eval pipeline end to end
data/
  runbooks/                 sample runbooks (markdown)
  architecture_docs/        sample architecture docs
  historical_incidents/     sample past-incident writeups
  sample_incidents/         synthetic logs/metrics/traces/deploys for a demo incident
scripts/
  seed_data.py               ingest data/ into Postgres
  generate_synthetic_incidents.py   generate more eval incidents
tests/
  test_retriever.py
```

## Quickstart

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
2. `docker compose up -d postgres redis` (Kafka is optional for the demo path)
3. `pip install -r requirements.txt`
4. `python scripts/seed_data.py` — embeds the sample runbooks/docs/incidents into Postgres
5. `uvicorn app.main:app --reload`
6. Trigger an investigation against the bundled sample incident:

   ```bash
   curl -X POST localhost:8000/incidents/investigate \
     -H "Content-Type: application/json" \
     -d '{"incident_id": "incident_001", "summary": "Checkout service p99 latency spike and 5xx errors after deploy"}'
   ```

   You'll get back a JSON RCA with a `root_cause`, `timeline`, `evidence` list, and
   `citations` pointing at specific log lines, metric windows, and runbook sections.

7. Run the eval pipeline: `python -m app.eval.run_eval` — scores Recall@5 on retrieval,
   citation correctness, and RCA accuracy (LLM-as-judge against ground-truth root causes)
   across the simulated incident set.

## Design notes / why this shape

- **Parallel specialist agents** (log / metrics / trace) each get a narrow toolset and a
  narrow prompt, so each investigation thread stays focused and cheap, and they run
  concurrently instead of one agent doing a serial 20-tool-call slog.
- **Verification agent** is a separate pass, not the same agent grading its own work — it
  re-checks every claim in the draft RCA against the evidence blocks that were actually
  retrieved, and strips or flags unsupported claims before the report is returned.
- **RAG is retrieval, not memorization** — runbooks/architecture docs/historical incidents
  are chunked, embedded, and cited by section, so the RCA can point to *why* (a specific
  known-failure-mode section) rather than just re-describing the symptoms.
- **Kafka is optional for local dev** — the same evidence rows Kafka would populate are
  loaded from `data/sample_incidents/` via `scripts/seed_data.py`, so you can develop and
  demo the agent logic without standing up a broker.
