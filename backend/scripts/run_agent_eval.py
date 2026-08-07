from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent.runner import run_page_generation_agent
from app.schemas.page_dsl import GenerationRequestDraft, PageDSL


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    duration_ms: float
    generation_source: str | None
    structure_complete: bool
    component_hit_rate: float
    renderable: bool
    task_plan_used: bool
    query_rewrite_used: bool
    rag_chunk_count: int
    retrieved_doc_count: int
    citation_count: int
    rag_quality_score: float
    rewritten_query: str | None
    query_rewrite_hit_rate: float
    tool_invocation_count: int
    tool_success_rate: float
    tool_duration_ms: float
    error: str | None = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline evals for the page generation agent.")
    parser.add_argument(
        "--cases",
        default=str(PROJECT_DIR / "data/evals/page_generation_cases.jsonl"),
        help="Path to JSONL eval cases.",
    )
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    results = [run_case(case) for case in cases]
    print_report(results)

    if any(not result.passed for result in results):
        raise SystemExit(1)


def load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)

    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def run_case(case: dict[str, Any]) -> EvalResult:
    started_at = perf_counter()
    try:
        request = GenerationRequestDraft(
            prompt=case["prompt"],
            page_type=case["page_type"],
            brand_style=case["brand_style"],
        )
        agent_result = run_page_generation_agent(request)
        page_dsl = agent_result.page_dsl
        execute_metadata = extract_trace_metadata(agent_result.agent_trace, "execute")
        duration_ms = _elapsed_ms(started_at)
        expected_components = case.get("expected_components", [])
        expected_query_terms = case.get("expected_query_terms", [])
        structure_complete = is_structure_complete(page_dsl)
        component_hit_rate = calculate_component_hit_rate(page_dsl, expected_components)
        query_rewrite_hit_rate = calculate_query_rewrite_hit_rate(
            execute_metadata.get("rewritten_query"),
            expected_query_terms,
        )
        renderable = is_renderable(page_dsl)
        passed = structure_complete and renderable and component_hit_rate >= 1.0
        return EvalResult(
            case_id=case["case_id"],
            passed=passed,
            duration_ms=duration_ms,
            generation_source=agent_result.generation_source,
            structure_complete=structure_complete,
            component_hit_rate=component_hit_rate,
            renderable=renderable,
            task_plan_used=bool(execute_metadata.get("task_plan_used")),
            query_rewrite_used=bool(execute_metadata.get("rewritten_query")),
            rag_chunk_count=int(execute_metadata.get("rag_chunk_count") or 0),
            retrieved_doc_count=len(execute_metadata.get("retrieved_doc_ids") or []),
            citation_count=len(execute_metadata.get("citations") or []),
            rag_quality_score=float(execute_metadata.get("rag_quality_score") or 0),
            rewritten_query=execute_metadata.get("rewritten_query"),
            query_rewrite_hit_rate=query_rewrite_hit_rate,
            tool_invocation_count=int(execute_metadata.get("tool_invocation_count") or 0),
            tool_success_rate=float(execute_metadata.get("tool_success_rate") or 0),
            tool_duration_ms=float(execute_metadata.get("tool_duration_ms") or 0),
        )
    except Exception as exc:
        return EvalResult(
            case_id=case.get("case_id", "unknown"),
            passed=False,
            duration_ms=_elapsed_ms(started_at),
            generation_source=None,
            structure_complete=False,
            component_hit_rate=0,
            renderable=False,
            task_plan_used=False,
            query_rewrite_used=False,
            rag_chunk_count=0,
            retrieved_doc_count=0,
            citation_count=0,
            rag_quality_score=0,
            rewritten_query=None,
            query_rewrite_hit_rate=0,
            tool_invocation_count=0,
            tool_success_rate=0,
            tool_duration_ms=0,
            error=str(exc),
        )


def is_structure_complete(page_dsl: PageDSL) -> bool:
    return bool(
        page_dsl.page_meta.name
        and page_dsl.page_meta.page_type
        and page_dsl.page_meta.theme
        and page_dsl.layout.template_id
        and len(page_dsl.sections) >= 3
    )


def calculate_component_hit_rate(page_dsl: PageDSL, expected_components: list[str]) -> float:
    if not expected_components:
        return 1.0

    actual_components = {section.component_type for section in page_dsl.sections}
    hits = sum(1 for component in expected_components if component in actual_components)
    return round(hits / len(expected_components), 4)


def calculate_query_rewrite_hit_rate(rewritten_query: str | None, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 1.0
    query = (rewritten_query or "").lower()
    hits = sum(1 for term in expected_terms if str(term).lower() in query)
    return round(hits / len(expected_terms), 4)


def is_renderable(page_dsl: PageDSL) -> bool:
    section_ids = [section.section_id for section in page_dsl.sections]
    return len(section_ids) == len(set(section_ids)) and all(section.order > 0 for section in page_dsl.sections)


def extract_trace_metadata(agent_trace: list[Any], node_name: str) -> dict[str, Any]:
    for step in agent_trace:
        if step.node == node_name:
            return step.metadata
    return {}


def print_report(results: list[EvalResult]) -> None:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    fallback_count = sum(1 for result in results if result.generation_source == "fallback")
    avg_duration = round(sum(result.duration_ms for result in results) / total, 2) if total else 0
    structure_rate = _rate(result.structure_complete for result in results)
    renderable_rate = _rate(result.renderable for result in results)
    avg_component_hit_rate = (
        round(sum(result.component_hit_rate for result in results) / total, 4) if total else 0
    )
    task_plan_used_rate = _rate(result.task_plan_used for result in results)
    query_rewrite_used_rate = _rate(result.query_rewrite_used for result in results)
    rag_used_rate = _rate(result.rag_chunk_count > 0 for result in results)
    avg_rag_chunk_count = (
        round(sum(result.rag_chunk_count for result in results) / total, 2) if total else 0
    )
    avg_citation_count = (
        round(sum(result.citation_count for result in results) / total, 2) if total else 0
    )
    avg_rag_quality_score = (
        round(sum(result.rag_quality_score for result in results) / total, 4) if total else 0
    )
    avg_query_rewrite_hit_rate = (
        round(sum(result.query_rewrite_hit_rate for result in results) / total, 4) if total else 0
    )
    avg_tool_invocation_count = (
        round(sum(result.tool_invocation_count for result in results) / total, 2) if total else 0
    )
    avg_tool_success_rate = (
        round(sum(result.tool_success_rate for result in results) / total, 4) if total else 0
    )
    avg_tool_duration_ms = (
        round(sum(result.tool_duration_ms for result in results) / total, 2) if total else 0
    )

    print(json.dumps(
        {
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total, 4) if total else 0,
            "structure_complete_rate": structure_rate,
            "renderable_rate": renderable_rate,
            "avg_component_hit_rate": avg_component_hit_rate,
            "fallback_rate": round(fallback_count / total, 4) if total else 0,
            "task_plan_used_rate": task_plan_used_rate,
            "query_rewrite_used_rate": query_rewrite_used_rate,
            "rag_used_rate": rag_used_rate,
            "avg_rag_chunk_count": avg_rag_chunk_count,
            "avg_citation_count": avg_citation_count,
            "avg_rag_quality_score": avg_rag_quality_score,
            "avg_query_rewrite_hit_rate": avg_query_rewrite_hit_rate,
            "avg_tool_invocation_count": avg_tool_invocation_count,
            "avg_tool_success_rate": avg_tool_success_rate,
            "avg_tool_duration_ms": avg_tool_duration_ms,
            "avg_duration_ms": avg_duration,
            "cases": [result.__dict__ for result in results],
        },
        ensure_ascii=False,
        indent=2,
    ))


def _rate(values) -> float:
    values = list(values)
    return round(sum(1 for value in values if value) / len(values), 4) if values else 0


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


if __name__ == "__main__":
    main()
