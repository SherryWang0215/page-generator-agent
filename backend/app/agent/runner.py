from __future__ import annotations

import logging
from collections.abc import Callable
from time import perf_counter

from langgraph.graph import END, START, StateGraph

from .nodes.answer import answer_node
from .nodes.execute import execute_node
from .nodes.input_guard import input_guard_node
from .nodes.plan import plan_node
from .nodes.reflect import reflect_node
from .state import AgentTraceStep, PageGenerationAgentResult, PageGenerationState
from ..schemas.page_dsl import GenerationRequestDraft
from ..services.audit_service import audit_event
from ..services.langsmith_tracer import trace_agent_run


logger = logging.getLogger(__name__)

Node = Callable[[PageGenerationState], PageGenerationState]


def run_page_generation_agent(
    request: GenerationRequestDraft, request_id: str | None = None
) -> PageGenerationAgentResult:
    state = PageGenerationState(request=request, request_id=request_id)
    graph_result = build_page_generation_graph().invoke(state)
    state = normalize_graph_result(graph_result)

    if state.page_dsl is None or state.generation_source is None:
        raise RuntimeError("page generation agent finished without page output")

    trace_agent_run(
        name="page_generation_agent",
        inputs=request.model_dump(),
        outputs={
            "generation_source": state.generation_source,
            "section_count": len(state.page_dsl.sections),
        },
        metadata={
            "request_id": request_id,
            "trace_steps": [step.model_dump() for step in state.trace],
        },
    )
    audit_event(
        "agent_generation_completed",
        {
            "generation_source": state.generation_source,
            "section_count": len(state.page_dsl.sections),
            "trace_node_count": len(state.trace),
        },
    )

    return PageGenerationAgentResult(
        page_dsl=state.page_dsl,
        generation_source=state.generation_source,
        agent_trace=state.trace,
    )


def run_page_revision_agent(
    base_page_dsl, instruction: str, request_id: str | None = None
) -> PageGenerationAgentResult:
    # Revision instructions can be very short (e.g. "商务一点"),
    # but GenerationRequestDraft.prompt requires >= 8 chars.
    # Pad with context so the prompt is always valid.
    if len(instruction) < 8:
        prompt = f"修改页面：{instruction}"
        while len(prompt) < 8:
            prompt += "。"
    else:
        prompt = instruction
    request = GenerationRequestDraft(
        prompt=prompt,
        page_type=base_page_dsl.page_meta.page_type,
        brand_style=base_page_dsl.page_meta.theme,
    )
    state = PageGenerationState(
        request=request,
        base_page_dsl=base_page_dsl,
        revision_instruction=instruction,
        request_id=request_id,
    )
    graph_result = build_page_generation_graph().invoke(state)
    state = normalize_graph_result(graph_result)

    if state.page_dsl is None or state.generation_source is None:
        raise RuntimeError("page revision agent finished without page output")

    trace_agent_run(
        name="page_revision_agent",
        inputs={"instruction": instruction, "base_page_type": base_page_dsl.page_meta.page_type},
        outputs={
            "generation_source": state.generation_source,
            "section_count": len(state.page_dsl.sections),
        },
        metadata={
            "request_id": request_id,
            "trace_steps": [step.model_dump() for step in state.trace],
        },
    )
    audit_event(
        "agent_revision_completed",
        {
            "generation_source": state.generation_source,
            "section_count": len(state.page_dsl.sections),
            "trace_node_count": len(state.trace),
        },
    )

    return PageGenerationAgentResult(
        page_dsl=state.page_dsl,
        generation_source=state.generation_source,
        agent_trace=state.trace,
    )


def build_page_generation_graph():
    graph = StateGraph(PageGenerationState)
    graph.add_node("input_guard", lambda state: run_node("input_guard", input_guard_node, normalize_graph_result(state)))
    graph.add_node("plan", lambda state: run_node("plan", plan_node, normalize_graph_result(state)))
    graph.add_node("execute", lambda state: run_node("execute", execute_node, normalize_graph_result(state)))
    graph.add_node("reflect", lambda state: run_node("reflect", reflect_node, normalize_graph_result(state)))
    graph.add_node("answer", lambda state: run_node("answer", answer_node, normalize_graph_result(state)))
    graph.add_edge(START, "input_guard")
    graph.add_edge("input_guard", "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "reflect")
    graph.add_edge("reflect", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


def normalize_graph_result(graph_result: object) -> PageGenerationState:
    if isinstance(graph_result, PageGenerationState):
        return graph_result
    if isinstance(graph_result, dict):
        return PageGenerationState.model_validate(graph_result)
    raise TypeError(f"unexpected graph state type: {type(graph_result)!r}")


def run_node(node_name: str, node: Node, state: PageGenerationState) -> PageGenerationState:
    started_at = perf_counter()
    logger.info("Agent node started | node=%s", node_name)
    try:
        next_state = node(state)
    except Exception as exc:
        duration_ms = elapsed_ms(started_at)
        state.trace.append(
            AgentTraceStep(
                node=node_name,
                status="failed",
                duration_ms=duration_ms,
                message=str(exc),
            )
        )
        trace_agent_run(
            name=f"agent_node_{node_name}",
            inputs={"node": node_name},
            outputs={"status": "failed", "duration_ms": duration_ms},
            metadata={"request_id": state.request_id},
            error=str(exc),
        )
        audit_event(
            "agent_node_failed",
            {
                "node": node_name,
                "duration_ms": duration_ms,
                "error": str(exc),
            },
        )
        logger.exception("Agent node failed | node=%s | duration_ms=%.2f", node_name, duration_ms)
        raise

    duration_ms = elapsed_ms(started_at)
    next_state.trace.append(
        trace_step := AgentTraceStep(
            node=node_name,
            status="success",
            duration_ms=duration_ms,
            message=f"{node_name} completed",
            metadata=build_trace_metadata(node_name, next_state),
        )
    )
    trace_agent_run(
        name=f"agent_node_{node_name}",
        inputs={"node": node_name},
        outputs={"status": "success", "duration_ms": duration_ms},
        metadata={**trace_step.metadata, "request_id": state.request_id},
    )
    logger.info("Agent node finished | node=%s | duration_ms=%.2f", node_name, duration_ms)
    return next_state


def elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def build_trace_metadata(node_name: str, state: PageGenerationState) -> dict[str, object]:
    if node_name == "input_guard":
        return {
            "passed": not state.safety_issues,
            "issue_count": len(state.safety_issues),
            "issue_codes": [str(issue.get("code")) for issue in state.safety_issues],
        }
    if node_name == "plan":
        return {
            "task_count": len(state.task_plan),
            "subject": state.parsed_intent.get("subject"),
        }
    if node_name == "execute":
        context_package = state.context_package
        tool_metrics = build_tool_metrics(state.tool_results)
        return {
            "generation_source": state.generation_source,
            "task_status": {task.task_id: task.status for task in state.task_plan},
            "context_hash": context_package.runtime_context.get("context_hash") if context_package else None,
            "rag_chunk_count": (
                context_package.knowledge_context.get("rag_chunk_count") if context_package else 0
            ),
            "rag_raw_chunk_count": (
                context_package.knowledge_context.get("rag_raw_chunk_count") if context_package else 0
            ),
            "rag_quality_score": (
                context_package.knowledge_context.get("rag_quality_score") if context_package else 0
            ),
            "citations": (
                context_package.knowledge_context.get("citations", []) if context_package else []
            ),
            "retrieved_doc_ids": (
                context_package.knowledge_context.get("retrieved_doc_ids", []) if context_package else []
            ),
            "query_rewrite_strategy": (
                context_package.knowledge_context.get("query_rewrite_strategy") if context_package else None
            ),
            "rewritten_query": (
                context_package.knowledge_context.get("rewritten_query") if context_package else None
            ),
            "task_plan_used": state.tool_results.get("page_generation", {}).get("task_plan_used", False),
            "tool_invocation_count": tool_metrics["tool_invocation_count"],
            "tool_success_rate": tool_metrics["tool_success_rate"],
            "tool_duration_ms": tool_metrics["tool_duration_ms"],
            "tool_names": tool_metrics["tool_names"],
        }
    if node_name == "reflect":
        return {
            "passed": state.reflection_result.passed if state.reflection_result else False,
            "issues": state.reflection_result.issues if state.reflection_result else [],
        }
    if node_name == "answer" and state.page_dsl:
        return {
            "generation_source": state.generation_source,
            "section_count": len(state.page_dsl.sections),
        }
    return {}


def build_tool_metrics(tool_results: dict[str, object]) -> dict[str, object]:
    tool_events = [
        result
        for result in tool_results.values()
        if isinstance(result, dict) and result.get("tool_name")
    ]
    if not tool_events:
        return {
            "tool_invocation_count": 0,
            "tool_success_rate": 1.0,
            "tool_duration_ms": 0,
            "tool_names": [],
        }

    success_count = sum(1 for event in tool_events if event.get("success"))
    duration_ms = round(sum(float(event.get("duration_ms") or 0) for event in tool_events), 2)
    tool_names = [str(event.get("tool_name")) for event in tool_events]
    return {
        "tool_invocation_count": len(tool_events),
        "tool_success_rate": round(success_count / len(tool_events), 4),
        "tool_duration_ms": duration_ms,
        "tool_names": tool_names,
    }
