from __future__ import annotations

import hashlib
import logging
from typing import Any

from ..config import settings
from ..services.audit_service import audit_event
from .state import ContextPackage, ContextSource, PageGenerationState
from .tool_harness import tool_registry
from .tools.knowledge_tools import query_rag_tool


logger = logging.getLogger(__name__)


def build_context_package(state: PageGenerationState) -> ContextPackage:
    """Assemble the runtime context used by the agent execution harness."""
    task_plan = [task.model_dump() for task in state.task_plan]
    rewritten_query = rewrite_rag_query(state, task_plan)
    rag_result = _query_rag(rewritten_query)
    raw_chunks = rag_result.get("chunks", [])
    quality_chunks = _filter_quality_chunks(raw_chunks)
    rag_context = _format_rag_context(quality_chunks)
    citations = _build_citations(quality_chunks)
    quality_score = _calculate_rag_quality_score(raw_chunks, quality_chunks)
    base_page_summary = _summarize_page(state)
    context_sources = _build_context_sources(quality_chunks)

    package = ContextPackage(
        request_context={
            "prompt": state.request.prompt,
            "page_type": state.request.page_type,
            "brand_style": state.request.brand_style,
            "parsed_intent": state.parsed_intent,
        },
        session_context={
            "conversation_id": state.conversation_id,
            "revision_instruction": state.revision_instruction,
        },
        object_context={
            "base_page": base_page_summary,
            "has_base_page": state.base_page_dsl is not None,
        },
        knowledge_context={
            "original_query": state.request.prompt,
            "rewritten_query": rewritten_query,
            "query_rewrite_strategy": "prompt_page_style_intent_task_plan",
            "rag_context": rag_context,
            "rag_chunk_count": len(quality_chunks),
            "rag_raw_chunk_count": len(raw_chunks),
            "rag_quality_score": quality_score,
            "rag_min_score": settings.rag_min_score,
            "citations": citations,
            "retrieved_doc_ids": [
                chunk.get("doc_id")
                for chunk in quality_chunks
                if chunk.get("doc_id")
            ],
        },
        tool_context={
            "task_plan": task_plan,
            "tool_policy": "static_registry",
            "available_tools": tool_registry.describe(),
        },
        runtime_context={
            "context_hash": _context_hash(
                state.request.prompt,
                rewritten_query,
                task_plan,
                rag_context,
                base_page_summary,
            ),
            "context_version": "context_package_v1",
        },
        context_sources=context_sources,
        token_budget={
            "request_context": 500,
            "knowledge_context": 1600,
            "task_plan": 800,
            "object_context": 1200,
        },
    )
    audit_event(
        "rag_context_assembled",
        {
            "context_hash": package.runtime_context["context_hash"],
            "original_query_len": len(state.request.prompt),
            "rewritten_query_len": len(rewritten_query),
            "raw_chunk_count": len(raw_chunks),
            "kept_chunk_count": len(quality_chunks),
            "rag_quality_score": quality_score,
            "retrieved_doc_ids": package.knowledge_context["retrieved_doc_ids"],
        },
    )
    logger.info(
        "Context package assembled | hash=%s | rag_chunks=%s | task_count=%s",
        package.runtime_context["context_hash"],
        package.knowledge_context["rag_chunk_count"],
        len(state.task_plan),
    )
    return package


def rewrite_rag_query(state: PageGenerationState, task_plan: list[dict[str, Any]]) -> str:
    """Build a deterministic retrieval query from task and business context."""
    subject = state.parsed_intent.get("subject")
    audience = state.parsed_intent.get("audience")
    goal = state.parsed_intent.get("goal")
    component_types = [
        task.get("params", {}).get("component_type")
        for task in task_plan
        if task.get("params", {}).get("component_type")
    ]

    parts = [
        state.request.prompt,
        f"页面类型: {state.request.page_type}",
        f"品牌风格: {state.request.brand_style}",
    ]
    if subject:
        parts.append(f"主题: {subject}")
    if audience:
        parts.append(f"目标用户: {audience}")
    if goal:
        parts.append(f"页面目标: {goal}")
    if component_types:
        parts.append("组件规范: " + " ".join(dict.fromkeys(component_types)))
    if state.revision_instruction:
        parts.append(f"修改指令: {state.revision_instruction}")

    return " | ".join(str(part) for part in parts if part)


def _query_rag(prompt: str) -> dict[str, Any]:
    try:
        return query_rag_tool({"query": prompt})
    except Exception as exc:
        logger.warning("RAG query failed during context assembly | reason=%s", exc)
        return {"chunks": [], "context_text": "", "error": str(exc)}


def _filter_quality_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        chunk
        for chunk in chunks
        if float(chunk.get("score") or 0) >= settings.rag_min_score
    ]


def _format_rag_context(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        lines.append(f"[参考知识 {index}] 来源: {chunk.get('title') or chunk.get('doc_id')}")
        lines.append(str(chunk.get("content") or ""))
        lines.append("")
    return "\n".join(lines).strip()


def _build_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": chunk.get("doc_id"),
            "title": chunk.get("title"),
            "score": chunk.get("score"),
            "rank": index,
        }
        for index, chunk in enumerate(chunks, start=1)
    ]


def _calculate_rag_quality_score(raw_chunks: list[dict[str, Any]], quality_chunks: list[dict[str, Any]]) -> float:
    if not raw_chunks:
        return 0.0
    avg_score = sum(float(chunk.get("score") or 0) for chunk in quality_chunks) / len(raw_chunks)
    coverage = len(quality_chunks) / len(raw_chunks)
    return round(min(1.0, avg_score * coverage), 4)


def _build_context_sources(chunks: list[dict[str, Any]]) -> list[ContextSource]:
    sources: list[ContextSource] = []
    for index, chunk in enumerate(chunks, start=1):
        sources.append(
            ContextSource(
                source_type="rag_chunk",
                source_id=str(chunk.get("doc_id") or f"chunk_{index}"),
                title=chunk.get("title"),
                score=chunk.get("score"),
                metadata={"rank": index},
            )
        )
    return sources


def _summarize_page(state: PageGenerationState) -> dict[str, Any] | None:
    if state.base_page_dsl is None:
        return None

    return {
        "page_meta": state.base_page_dsl.page_meta.model_dump(),
        "layout": state.base_page_dsl.layout.model_dump(),
        "sections": [
            {
                "section_id": section.section_id,
                "component_type": section.component_type,
                "order": section.order,
            }
            for section in state.base_page_dsl.sections
        ],
    }


def _context_hash(*parts: Any) -> str:
    raw = repr(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
