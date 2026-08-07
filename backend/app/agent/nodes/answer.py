from __future__ import annotations

import logging

from ...schemas.page_dsl import PageDSL
from ...services.page_generator import build_page_from_template
from ..state import PageGenerationState


logger = logging.getLogger(__name__)


def answer_node(state: PageGenerationState) -> PageGenerationState:
    if state.page_dsl is None or (state.reflection_result and not state.reflection_result.passed):
        state.page_dsl = build_page_from_template(state.request)
        state.generation_source = "fallback"
        state.error_info.append("answer_node_repaired_page_dsl")
    else:
        state.page_dsl = PageDSL.model_validate(state.page_dsl.model_dump())

    if state.generation_source is None:
        state.generation_source = "fallback"

    section_count = len(state.page_dsl.sections)
    logger.info(
        "Answer node finished | source=%s | sections=%s",
        state.generation_source,
        section_count,
    )
    return state
