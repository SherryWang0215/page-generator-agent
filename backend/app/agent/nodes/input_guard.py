from __future__ import annotations

import logging

from ...services.audit_service import audit_event
from ...services.safety import check_prompt_safety
from ..state import PageGenerationState


logger = logging.getLogger(__name__)


def input_guard_node(state: PageGenerationState) -> PageGenerationState:
    """Block unsafe user input before it reaches planning, RAG, LLM, or tools."""
    prompt_safety_issues = check_prompt_safety(state.request.prompt)
    if not prompt_safety_issues:
        logger.info("Input guard passed")
        return state

    state.safety_issues.extend(prompt_safety_issues)
    state.error_info.extend(f"prompt_safety_violation: {issue['code']}" for issue in prompt_safety_issues)
    audit_event(
        "prompt_safety_violation",
        {
            "stage": "input_guard",
            "action": "block",
            "issues": prompt_safety_issues,
            "prompt_len": len(state.request.prompt),
        },
    )
    logger.warning("Input guard blocked request | issues=%s", prompt_safety_issues)
    issue_codes = ",".join(str(issue["code"]) for issue in prompt_safety_issues)
    raise ValueError(f"input safety guard blocked request: {issue_codes}")
