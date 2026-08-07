from __future__ import annotations

import logging
from urllib.parse import urlparse

from pydantic import ValidationError

from ...schemas.page_dsl import CTAButtonSection, FeatureCardsSection, HeroBannerSection, PageDSL
from ...services.audit_service import audit_event
from ...services.safety import check_page_compliance
from ..state import PageGenerationState, ReflectionResult


logger = logging.getLogger(__name__)


REQUIRED_COMPONENTS = {"hero_banner", "feature_cards", "cta_button"}


def reflect_node(state: PageGenerationState) -> PageGenerationState:
    issues: list[str] = []

    if state.page_dsl is None:
        issues.append("page_dsl_missing")
    else:
        try:
            PageDSL.model_validate(state.page_dsl.model_dump())
        except ValidationError as exc:
            issues.append(f"page_dsl_schema_invalid: {exc.errors()}")

        component_types = {section.component_type for section in state.page_dsl.sections}
        missing_components = sorted(REQUIRED_COMPONENTS - component_types)
        if missing_components:
            issues.append(f"missing_required_components: {missing_components}")

        issues.extend(check_quality_rules(state.page_dsl))
        compliance_issues = check_page_compliance(state.page_dsl)
        if compliance_issues:
            issues.extend(f"output_compliance_violation: {issue['code']}" for issue in compliance_issues)
            audit_event(
                "output_compliance_violation",
                {
                    "issues": compliance_issues,
                    "page_type": state.page_dsl.page_meta.page_type,
                    "theme": state.page_dsl.page_meta.theme,
                },
            )

    if issues:
        state.error_info.extend(issues)
        state.reflection_result = ReflectionResult(
            passed=False,
            issues=issues,
        )
        logger.warning("Reflect node found issues | issues=%s", issues)
        return state

    state.reflection_result = ReflectionResult(passed=True, issues=[])
    logger.info("Reflect node finished | passed=true")
    return state


def check_quality_rules(page_dsl: PageDSL) -> list[str]:
    issues: list[str] = []

    hero = find_section(page_dsl, HeroBannerSection)
    if hero and not is_valid_https_url(str(hero.props.image_url)):
        issues.append("hero_image_url_must_be_https")

    features = find_section(page_dsl, FeatureCardsSection)
    if features and len(features.props.items) < 3:
        issues.append("feature_cards_should_have_at_least_3_items")

    cta = find_section(page_dsl, CTAButtonSection)
    if cta:
        if cta.props.action_type == "navigate" and not cta.props.target_url:
            issues.append("cta_navigate_requires_target_url")
        if cta.props.target_url and not is_valid_url(str(cta.props.target_url)):
            issues.append("cta_target_url_invalid")

    return issues


def find_section(page_dsl: PageDSL, section_type):
    for section in page_dsl.sections:
        if isinstance(section, section_type):
            return section
    return None


def is_valid_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
