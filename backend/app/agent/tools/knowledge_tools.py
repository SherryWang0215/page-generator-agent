from __future__ import annotations

import logging
from typing import Any

from elasticsearch import Elasticsearch

from ...adapters.knowledge.adapter import KnowledgeAdapter, KnowledgeChunk
from ...config import settings

logger = logging.getLogger(__name__)

_adapter: KnowledgeAdapter | None = None


def _get_adapter() -> KnowledgeAdapter:
    global _adapter
    if _adapter is None:
        try:
            es = Elasticsearch(hosts=[settings.es_host])
            es.info()
            _adapter = KnowledgeAdapter(es_client=es)
        except Exception as exc:
            logger.warning("ES unavailable, RAG will be disabled | reason=%s", exc)
            _adapter = KnowledgeAdapter(es_client=None)
            _adapter._enabled = False
    return _adapter


def query_rag_tool(params: dict[str, Any]) -> dict[str, Any]:
    """Agent tool: retrieve relevant knowledge chunks for the given query.

    Input params:
        query: the search query (usually the user's prompt)
        top_k: optional, number of chunks to retrieve (default from config)

    Output:
        {"chunks": [...], "context_text": "..."}
    """
    query = str(params.get("query") or params.get("prompt") or "")
    top_k = int(params.get("top_k") or settings.rag_top_k)

    if not query.strip():
        logger.warning("query_rag called with empty query")
        return {"chunks": [], "context_text": ""}

    adapter = _get_adapter()
    chunks = adapter.query_rag(query, top_k=top_k)

    context_text = _format_context(chunks)
    logger.info(
        "query_rag completed | query_len=%d | chunks=%d | context_len=%d",
        len(query),
        len(chunks),
        len(context_text),
    )
    return {
        "chunks": [
            {
                "doc_id": c.doc_id,
                "title": c.title,
                "content": c.content,
                "score": c.score,
            }
            for c in chunks
        ],
        "context_text": context_text,
    }


def _format_context(chunks: list[KnowledgeChunk]) -> str:
    if not chunks:
        return ""
    lines: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[参考知识 {i}] 来源: {chunk.title}")
        lines.append(chunk.content)
        lines.append("")
    return "\n".join(lines).strip()
