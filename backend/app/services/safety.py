from __future__ import annotations

import re
from typing import Any

from ..config import settings
from ..schemas.page_dsl import PageDSL


FORBIDDEN_OUTPUT_PATTERNS = {
    "absolute_best_claim": re.compile(r"(全网第一|行业第一|最[佳强]|100%|百分百|保证治愈|稳赚不赔)"),
    "sensitive_contact": re.compile(r"(\d{3}-?\d{4}-?\d{4}|[\w.+-]+@[\w-]+\.[\w.-]+)"),
    "unsafe_medical_claim": re.compile(r"(治疗|治愈|药到病除|替代医生|诊断疾病)"),
}

PROMPT_INJECTION_PATTERNS = {
    "ignore_previous_instructions": re.compile(r"(忽略.*指令|ignore .*instructions|forget .*rules)", re.I),
    "system_prompt_extraction": re.compile(r"(系统提示词|system prompt|开发者消息|developer message)", re.I),
}


def check_prompt_safety(prompt: str) -> list[dict[str, Any]]:
    if not settings.safety_enabled:
        return []

    return [
        {
            "code": code,
            "severity": "high",
            "message": "Prompt may contain injection or system extraction intent.",
        }
        for code, pattern in PROMPT_INJECTION_PATTERNS.items()
        if pattern.search(prompt)
    ]


def check_page_compliance(page_dsl: PageDSL) -> list[dict[str, Any]]:
    if not settings.safety_enabled:
        return []

    issues: list[dict[str, Any]] = []
    for field_path, text in _iter_page_text(page_dsl):
        for code, pattern in FORBIDDEN_OUTPUT_PATTERNS.items():
            if pattern.search(text):
                issues.append(
                    {
                        "code": code,
                        "severity": "medium",
                        "field_path": field_path,
                        "message": "Generated content matched a compliance rule.",
                    }
                )
    return issues


def _iter_page_text(page_dsl: PageDSL):
    yield "page_meta.name", page_dsl.page_meta.name
    yield "page_meta.audience", page_dsl.page_meta.audience
    yield "page_meta.goal", page_dsl.page_meta.goal

    for section in page_dsl.sections:
        props = section.props.model_dump()
        for key, value in props.items():
            if key.endswith("_url") or key in {"image_url", "target_url"}:
                continue
            if isinstance(value, str):
                yield f"sections.{section.section_id}.props.{key}", value
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        for item_key, item_value in item.items():
                            if isinstance(item_value, str):
                                yield (
                                    f"sections.{section.section_id}.props.{key}.{index}.{item_key}",
                                    item_value,
                                )
