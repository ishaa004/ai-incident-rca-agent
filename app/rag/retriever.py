from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI
from sqlalchemy import select

from app.config import settings
from app.db import KnowledgeChunk, get_session

_client = OpenAI(api_key=settings.openai_api_key)


@dataclass
class RetrievedChunk:
    source_type: str
    source_path: str
    title: str
    section: str
    content: str
    score: float  # cosine distance, lower = more similar

    def citation(self) -> str:
        return f"{self.source_type}:{self.title} \u203a {self.section}"


def embed_query(query: str) -> list[float]:
    resp = _client.embeddings.create(model=settings.openai_embedding_model, input=[query])
    return resp.data[0].embedding


def retrieve(query: str, top_k: int | None = None, source_types: list[str] | None = None) -> list[RetrievedChunk]:
    """Semantic search over the knowledge base. Returns chunks ordered by
    similarity, each carrying enough metadata to cite (source + section)."""
    top_k = top_k or settings.retrieval_top_k
    query_embedding = embed_query(query)

    session = get_session()
    try:
        stmt = select(
            KnowledgeChunk,
            KnowledgeChunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        if source_types:
            stmt = stmt.where(KnowledgeChunk.source_type.in_(source_types))
        stmt = stmt.order_by("distance").limit(top_k)

        rows = session.execute(stmt).all()
        return [
            RetrievedChunk(
                source_type=chunk.source_type,
                source_path=chunk.source_path,
                title=chunk.title,
                section=chunk.section,
                content=chunk.content,
                score=float(distance),
            )
            for chunk, distance in rows
        ]
    finally:
        session.close()
