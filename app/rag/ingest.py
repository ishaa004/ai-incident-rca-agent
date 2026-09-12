"""Chunk and embed the knowledge base (runbooks, architecture docs, historical
incident writeups) into the `knowledge_chunks` pgvector table.

Chunking strategy: split on markdown `## ` headings so each chunk maps to one
citable "section" (e.g. "Runbook: checkout-service.md ### Known failure mode:
DB connection pool exhaustion"). This keeps citations meaningful instead of
pointing at an arbitrary token window.
"""
from __future__ import annotations

import re
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.db import KnowledgeChunk, get_session, init_db

_client = OpenAI(api_key=settings.openai_api_key)

SOURCE_DIRS = {
    "runbook": "data/runbooks",
    "architecture_doc": "data/architecture_docs",
    "historical_incident": "data/historical_incidents",
}

HEADING_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """Return [(section_title, section_body), ...]. Content before the first
    heading is kept under an "Overview" section."""
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("Overview", text.strip())]

    sections = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append(("Overview", preamble))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))
    return sections


def embed_texts(texts: list[str]) -> list[list[float]]:
    resp = _client.embeddings.create(model=settings.openai_embedding_model, input=texts)
    return [d.embedding for d in resp.data]


def ingest_source_type(source_type: str, dir_path: str) -> int:
    session = get_session()
    count = 0
    path = Path(dir_path)
    if not path.exists():
        return 0

    for file in sorted(path.glob("*.md")):
        text = file.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text.strip() else file.stem
        sections = split_into_sections(text)
        if not sections:
            continue

        bodies = [body for _, body in sections]
        embeddings = embed_texts(bodies)

        for idx, ((section_title, body), emb) in enumerate(zip(sections, embeddings)):
            chunk = KnowledgeChunk(
                source_type=source_type,
                source_path=str(file),
                title=title,
                section=section_title,
                chunk_index=idx,
                content=body,
                embedding=emb,
            )
            session.add(chunk)
            count += 1

    session.commit()
    session.close()
    return count


def ingest_all() -> dict:
    init_db()
    results = {}
    for source_type, dir_path in SOURCE_DIRS.items():
        results[source_type] = ingest_source_type(source_type, dir_path)
    return results


if __name__ == "__main__":
    print(ingest_all())
