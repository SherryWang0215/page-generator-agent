from __future__ import annotations

import logging

from ...services.page_generator import infer_audience, infer_goal, infer_subject
from ..state import AgentTask, PageGenerationState


logger = logging.getLogger(__name__)


def plan_node(state: PageGenerationState) -> PageGenerationState:
    request = state.request
    subject = infer_revision_subject(state) if state.base_page_dsl else infer_subject(request.prompt)
    instruction = state.revision_instruction or request.prompt

    # Determine mode from conversation context
    intent_mode = "revision" if state.base_page_dsl else "generation"
    # If conversation_id exists, allow "chat" mode
    if state.conversation_id and intent_mode == "generation":
        # Simple heuristic: very short prompts in existing conversations are likely chat
        prompt_len = len(request.prompt.strip())
        if prompt_len < 8 and not any(kw in request.prompt for kw in ("生成", "创建", "制作", "设计", "落地页", "页面")):
            intent_mode = "chat"

    state.parsed_intent = {
        "subject": subject,
        "page_type": request.page_type,
        "brand_style": request.brand_style,
        "audience": infer_audience(request.page_type),
        "goal": infer_goal(request.page_type),
        "mode": intent_mode,
    }

    if state.base_page_dsl:
        state.task_plan = build_revision_tasks(instruction, subject)
        logger.info("Plan node finished revision | subject=%s | tasks=%s", subject, len(state.task_plan))
        return state

    state.task_plan = [
        AgentTask(
            task_id="task_select_layout",
            action="select_layout",
            params={"page_type": request.page_type, "template_id": "tpl_single_column"},
        ),
        AgentTask(
            task_id="task_generate_hero",
            action="generate_component",
            params={"component_type": "hero_banner", "subject": subject},
        ),
        AgentTask(
            task_id="task_generate_features",
            action="generate_component",
            params={"component_type": "feature_cards", "subject": subject, "count": 3},
        ),
        AgentTask(
            task_id="task_generate_cta",
            action="generate_component",
            params={"component_type": "cta_button", "subject": subject},
        ),
    ]

    logger.info("Plan node finished | subject=%s | tasks=%s", subject, len(state.task_plan))
    return state


def infer_revision_subject(state: PageGenerationState) -> str:
    if state.base_page_dsl is None:
        return infer_subject(state.request.prompt)

    page_name = state.base_page_dsl.page_meta.name
    for suffix in ("页面方案", "推广页", "落地页", "专题页", "页面"):
        if page_name.endswith(suffix):
            page_name = page_name[: -len(suffix)]
            break
    return page_name or infer_subject(state.request.prompt)


def build_revision_tasks(instruction: str, subject: str) -> list[AgentTask]:
    tasks: list[AgentTask] = []
    normalized = instruction.lower()

    if any(keyword in instruction for keyword in ("标题", "主标题", "hero", "商务", "企业", "高端")):
        tasks.append(
            AgentTask(
                task_id="task_rewrite_hero",
                action="rewrite_component",
                params={
                    "component_type": "hero_banner",
                    "target_section_id": "hero_001",
                    "subject": subject,
                    "instruction": instruction,
                },
            )
        )

    if any(keyword in instruction for keyword in ("卖点", "功能", "亮点", "feature")):
        tasks.append(
            AgentTask(
                task_id="task_rewrite_features",
                action="rewrite_component",
                params={
                    "component_type": "feature_cards",
                    "target_section_id": "features_001",
                    "subject": subject,
                    "instruction": instruction,
                },
            )
        )

    if any(keyword in instruction for keyword in ("按钮", "cta", "购买", "报名", "转化", "咨询")) or "call to action" in normalized:
        tasks.append(
            AgentTask(
                task_id="task_rewrite_cta",
                action="rewrite_component",
                params={
                    "component_type": "cta_button",
                    "target_section_id": "cta_001",
                    "subject": subject,
                    "instruction": instruction,
                },
            )
        )

    if any(keyword in instruction for keyword in ("客户案例", "用户评价", "客户评价", "证言", "testimonial")):
        tasks.append(
            AgentTask(
                task_id="task_generate_testimonials",
                action="generate_component",
                params={
                    "component_type": "testimonials",
                    "subject": subject,
                    "instruction": instruction,
                },
            )
        )

    if not tasks:
        tasks.append(
            AgentTask(
                task_id="task_rewrite_hero",
                action="rewrite_component",
                params={
                    "component_type": "hero_banner",
                    "target_section_id": "hero_001",
                    "subject": subject,
                    "instruction": instruction,
                },
            )
        )

    return tasks
