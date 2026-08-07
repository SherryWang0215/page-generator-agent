from __future__ import annotations

import logging

from ...services.llm_client import LLMGenerationError
from ...services.page_generator import build_page_with_llm
from ...schemas.page_dsl import PageDSL, PageMeta
from ..context import build_context_package
from ..tool_harness import invoke_tool, tool_result_payload
from ..state import PageGenerationState


logger = logging.getLogger(__name__)


def execute_node(state: PageGenerationState) -> PageGenerationState:
    state.context_package = build_context_package(state)
    state.tool_results["context_package"] = {
        "success": True,
        "result_type": "context_package",
        "context_hash": state.context_package.runtime_context.get("context_hash"),
        "source_count": len(state.context_package.context_sources),
        "rag_chunk_count": state.context_package.knowledge_context.get("rag_chunk_count", 0),
        "rag_raw_chunk_count": state.context_package.knowledge_context.get("rag_raw_chunk_count", 0),
        "rag_quality_score": state.context_package.knowledge_context.get("rag_quality_score", 0),
        "query_rewrite_strategy": state.context_package.knowledge_context.get("query_rewrite_strategy"),
        "rewritten_query": state.context_package.knowledge_context.get("rewritten_query"),
    }
    if state.context_package.knowledge_context.get("rag_chunk_count", 0):
        state.tool_results["query_rag"] = {
            "success": True,
            "result_type": "knowledge_context",
            "chunk_count": state.context_package.knowledge_context["rag_chunk_count"],
            "raw_chunk_count": state.context_package.knowledge_context.get("rag_raw_chunk_count", 0),
            "quality_score": state.context_package.knowledge_context.get("rag_quality_score", 0),
            "retrieved_doc_ids": state.context_package.knowledge_context.get("retrieved_doc_ids", []),
            "citations": state.context_package.knowledge_context.get("citations", []),
            "original_query": state.context_package.knowledge_context.get("original_query"),
            "rewritten_query": state.context_package.knowledge_context.get("rewritten_query"),
        }

    if state.base_page_dsl is not None:
        state.page_dsl = build_page_revision_from_tasks(state)
        state.generation_source = "revision"
        state.tool_results["page_revision"] = {
            "success": True,
            "source": state.generation_source,
            "mode": "partial_task_plan_tools",
        }
        logger.info("Execute node finished revision | tasks=%s", len(state.task_plan))
        return state

    rag_context = state.context_package.knowledge_context.get("rag_context", "")

    try:
        state.page_dsl = build_page_with_llm(
            state.request,
            rag_context,
            task_plan=state.task_plan,
        )
        state.generation_source = "llm_normalized"
        state.tool_results["page_generation"] = {
            "success": True,
            "source": state.generation_source,
            "rag_used": bool(rag_context),
            "task_plan_used": True,
            "context_hash": state.context_package.runtime_context.get("context_hash"),
        }
        for task in state.task_plan:
            task.status = "success"
        logger.info(
            "Execute node finished | source=%s | rag_used=%s",
            state.generation_source,
            bool(rag_context),
        )
        return state
    except LLMGenerationError as exc:
        state.error_info.append(f"llm_generation_failed: {exc}")
        logger.warning("Execute node LLM failed, fallback to task tools | reason=%s", exc)

    state.page_dsl = build_page_from_tasks(state)
    state.generation_source = "fallback"
    state.tool_results["page_generation"] = {
        "success": True,
        "source": state.generation_source,
        "mode": "task_plan_tools",
        "task_plan_used": True,
        "context_hash": state.context_package.runtime_context.get("context_hash"),
    }

    logger.info("Execute node finished | source=%s", state.generation_source)
    return state


def build_page_from_tasks(state: PageGenerationState) -> PageDSL:
    layout = None
    sections = []

    for task in state.task_plan:
        try:
            if task.action == "select_layout":
                invocation = invoke_tool("select_layout", task.params)
                state.tool_results[task.task_id] = tool_result_payload(invocation, "layout")
                layout = require_tool_result(invocation)
            elif task.params.get("component_type") == "hero_banner":
                invocation = invoke_tool("generate_hero", task.params)
                state.tool_results[task.task_id] = tool_result_payload(invocation, "section")
                section = require_tool_result(invocation)
                sections.append(section)
            elif task.params.get("component_type") == "feature_cards":
                invocation = invoke_tool("generate_features", task.params)
                state.tool_results[task.task_id] = tool_result_payload(invocation, "section")
                section = require_tool_result(invocation)
                sections.append(section)
            elif task.params.get("component_type") == "cta_button":
                invocation = invoke_tool("generate_cta", task.params)
                state.tool_results[task.task_id] = tool_result_payload(invocation, "section")
                section = require_tool_result(invocation)
                sections.append(section)
            else:
                task.status = "skipped"
                state.tool_results[task.task_id] = {
                    "success": False,
                    "result_type": "skipped",
                    "reason": f"unsupported task: {task.action}",
                }
                continue

            task.status = "success"
        except Exception as exc:
            task.status = "failed"
            state.tool_results.setdefault(
                task.task_id,
                {"success": False, "result_type": "error", "reason": str(exc)},
            )
            raise

    if layout is None:
        invocation = invoke_tool("select_layout", {"page_type": state.request.page_type})
        state.tool_results["task_select_layout_default"] = tool_result_payload(invocation, "layout")
        layout = require_tool_result(invocation)

    parsed_intent = state.parsed_intent
    page_meta = PageMeta(
        name=f"{parsed_intent.get('subject', '产品方案')}页面方案",
        page_type=state.request.page_type,
        theme=state.request.brand_style,
        audience=str(parsed_intent.get("audience") or "目标用户"),
        goal=str(parsed_intent.get("goal") or "页面转化"),
    )

    return PageDSL(
        page_meta=page_meta,
        layout=layout,
        sections=sorted(sections, key=lambda section: section.order),
    )


def build_page_revision_from_tasks(state: PageGenerationState) -> PageDSL:
    if state.base_page_dsl is None:
        raise ValueError("base_page_dsl is required for revision")

    sections = list(state.base_page_dsl.sections)

    for task in state.task_plan:
        try:
            component_type = task.params.get("component_type")
            target_section_id = task.params.get("target_section_id")

            if component_type == "hero_banner":
                base_section = find_section(sections, "hero_banner", target_section_id)
                invocation = invoke_tool("rewrite_hero", task.params, base_section=base_section)
                state.tool_results[task.task_id] = tool_result_payload(invocation, "section")
                section = require_tool_result(invocation)
                sections = replace_or_append_section(sections, section)
            elif component_type == "feature_cards":
                base_section = find_section(sections, "feature_cards", target_section_id)
                invocation = invoke_tool("rewrite_features", task.params, base_section=base_section)
                state.tool_results[task.task_id] = tool_result_payload(invocation, "section")
                section = require_tool_result(invocation)
                sections = replace_or_append_section(sections, section)
            elif component_type == "cta_button":
                base_section = find_section(sections, "cta_button", target_section_id)
                invocation = invoke_tool("rewrite_cta", task.params, base_section=base_section)
                state.tool_results[task.task_id] = tool_result_payload(invocation, "section")
                section = require_tool_result(invocation)
                sections = replace_or_append_section(sections, section)
            elif component_type == "testimonials":
                invocation = invoke_tool(
                    "generate_testimonials",
                    task.params,
                    order=next_section_order(sections),
                )
                state.tool_results[task.task_id] = tool_result_payload(invocation, "section")
                section = require_tool_result(invocation)
                sections = replace_or_append_section(sections, section)
            else:
                task.status = "skipped"
                state.tool_results[task.task_id] = {
                    "success": False,
                    "result_type": "skipped",
                    "reason": f"unsupported revision component: {component_type}",
                }
                continue

            task.status = "success"
        except Exception as exc:
            task.status = "failed"
            state.tool_results.setdefault(
                task.task_id,
                {"success": False, "result_type": "error", "reason": str(exc)},
            )
            raise

    return PageDSL(
        page_meta=state.base_page_dsl.page_meta,
        layout=state.base_page_dsl.layout,
        sections=sorted(sections, key=lambda section: section.order),
    )


def find_section(sections, component_type: str, section_id: str | None = None):
    for section in sections:
        if section_id and section.section_id == section_id:
            return section
        if not section_id and section.component_type == component_type:
            return section
    for section in sections:
        if section.component_type == component_type:
            return section
    return None


def replace_or_append_section(sections, new_section):
    next_sections = []
    replaced = False
    for section in sections:
        if section.section_id == new_section.section_id or section.component_type == new_section.component_type:
            if not replaced:
                next_sections.append(new_section)
                replaced = True
            continue
        next_sections.append(section)

    if not replaced:
        next_sections.append(new_section)

    return next_sections


def next_section_order(sections) -> int:
    if not sections:
        return 1
    return max(section.order for section in sections) + 1


def require_tool_result(invocation):
    if not invocation.success:
        raise RuntimeError(invocation.error or f"tool '{invocation.tool_name}' failed")
    return invocation.result
