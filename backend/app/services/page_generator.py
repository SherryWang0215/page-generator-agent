from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import ValidationError

from ..schemas.components import (
    CTAButtonProps,
    FeatureCardItem,
    FeatureCardsProps,
    HeroBannerProps,
    StyleToken,
)
from ..schemas.page_dsl import (
    CTAButtonSection,
    FeatureCardsSection,
    GenerationRequestDraft,
    HeroBannerSection,
    LayoutConfig,
    PageDSL,
    PageMeta,
)
from .llm_client import LLMGenerationError, OpenAICompatibleClient


llm_client = OpenAICompatibleClient()
logger = logging.getLogger(__name__)


def infer_subject(prompt: str) -> str:
    normalized = prompt.strip()
    keyword_map = {
        "智能手表": "智能手表",
        "手表": "智能手表",
        "课程": "课程产品",
        "SaaS": "SaaS 产品",
        "软件": "软件产品",
        "招聘": "招聘活动",
        "活动": "活动方案",
    }
    for keyword, subject in keyword_map.items():
        if keyword.lower() in normalized.lower():
            return subject

    matched = re.search(r"(生成|创建|做一个|做一页)(.*?)(页面|落地页|推广页|专题页)", normalized)
    if matched:
        candidate = matched.group(2).strip(" ，。,.")
        if 2 <= len(candidate) <= 20:
            return candidate

    return "产品方案"


def infer_audience(page_type: str) -> str:
    if page_type == "campaign_page":
        return "对活动主题感兴趣的目标用户"
    if page_type == "product_page":
        return "正在评估产品价值的潜在客户"
    return "需要快速理解产品卖点的潜在用户"


def infer_goal(page_type: str) -> str:
    if page_type == "campaign_page":
        return "活动报名转化"
    if page_type == "product_page":
        return "产品价值传达"
    return "营销转化"


def build_feature_items(subject: str) -> list[FeatureCardItem]:
    if subject == "智能手表":
        return [
            FeatureCardItem(
                title="全天候监测",
                description="持续追踪关键健康指标，帮助用户及时感知身体变化。",
            ),
            FeatureCardItem(
                title="精准睡眠分析",
                description="自动识别不同睡眠阶段，输出更易理解的睡眠建议。",
            ),
            FeatureCardItem(
                title="长续航体验",
                description="满足高频佩戴和连续监测需求，减少充电焦虑。",
            ),
        ]

    return [
        FeatureCardItem(
            title="价值聚焦",
            description=f"围绕{subject}的核心卖点进行集中表达，减少用户理解成本。",
        ),
        FeatureCardItem(
            title="信息清晰",
            description="通过模块化结构呈现重点信息，帮助用户快速完成浏览判断。",
        ),
        FeatureCardItem(
            title="转化导向",
            description="在关键节点设置明确行动引导，让页面更贴近业务目标。",
        ),
    ]


def build_system_prompt(rag_context: str = "") -> str:
    base_prompt = """
你是页面生成 Agent 的结构化输出模块。

你的任务是根据用户输入，生成一个合法的 PageDSL JSON。

必须遵守以下规则：
1. 只能输出 JSON，不能输出解释。
2. 顶层字段必须是：
   - page_meta
   - layout
   - sections
3. 当前只允许使用 3 个组件：
   - hero_banner
   - feature_cards
   - cta_button
   section 中的字段名必须使用 component_type，不能使用 component。
4. sections 至少 3 个，顺序固定为：
   - hero_banner
   - feature_cards
   - cta_button
5. page_type 只能是：
   - landing_page
   - product_page
   - campaign_page
6. theme 只能是：
   - tech_clean
   - business_formal
   - growth_marketing
7. layout.template_id 固定使用：
   - tpl_single_column
8. 每个 section_id 使用小写字母、数字、下划线，例如：
   - hero_001
   - features_001
   - cta_001
9. page_meta 中必须包含：
   - name
   - page_type
   - theme
   - audience
   - goal
10. hero_banner.props 必须包含：
   - title
   - subtitle
   - button_text
   - image_url
11. feature_cards.props 必须包含：
   - title
   - items
   items 中每项必须包含：
   - title
   - description
12. cta_button.props 必须包含：
   - title
   - description
   - button_text
   - action_type
   - target_url
13. 每个 section 都必须包含 order。
14. image_url 必须返回一个合法的 https URL。
15. 所有字段都必须完整，不允许缺失 props。
16. 文案必须使用中文，内容要具体、专业、有说服力。
"""

    if rag_context:
        return (
            base_prompt
            + "\n【重要：以下参考知识来自产品资料库，生成页面内容时应优先使用其中的事实信息，"
              "避免编造与参考知识矛盾的内容】\n\n"
            + rag_context
        )

    return base_prompt


def build_user_prompt(payload: GenerationRequestDraft, task_plan: list[Any] | None = None) -> str:
    task_plan_text = _format_task_plan(task_plan)
    plan_instruction = ""
    if task_plan_text:
        plan_instruction = f"""

执行计划 task_plan：
{task_plan_text}

请严格按照 task_plan 生成页面结构：
- select_layout 任务决定 layout.template_id
- generate_component 任务决定 sections 中需要出现的组件
- 每个组件任务至少生成一个对应 section
- section 顺序应与 task_plan 中组件任务顺序一致
"""

    return f"""
用户需求：{payload.prompt}
页面类型：{payload.page_type}
品牌风格：{payload.brand_style}
{plan_instruction}

请生成一个适合预览渲染的 PageDSL。
""".strip()


def build_page_with_llm(
    payload: GenerationRequestDraft,
    rag_context: str = "",
    task_plan: list[Any] | None = None,
) -> PageDSL:
    if not llm_client.enabled:
        raise LLMGenerationError("llm is not configured")

    raw_payload = llm_client.generate_json(
        system_prompt=build_system_prompt(rag_context),
        user_prompt=build_user_prompt(payload, task_plan=task_plan),
    )
    normalized_payload = normalize_llm_payload(raw_payload, payload)
    logger.info(
        "LLM structured payload parsed successfully | raw_payload=%s | normalized_payload=%s",
        raw_payload,
        normalized_payload,
    )
    try:
        return PageDSL.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.exception(
            "LLM output does not match PageDSL schema | raw_payload=%s | normalized_payload=%s",
            raw_payload,
            normalized_payload,
        )
        raise LLMGenerationError("llm output does not match PageDSL schema") from exc


def build_page_from_request(
    payload: GenerationRequestDraft,
    rag_context: str = "",
    task_plan: list[Any] | None = None,
) -> PageDSL:
    try:
        logger.info(
            "Trying LLM generation first | request=%s | rag_context_len=%d",
            payload.model_dump(),
            len(rag_context),
        )
        return build_page_with_llm(payload, rag_context, task_plan=task_plan)
    except LLMGenerationError as exc:
        logger.warning("LLM generation failed, fallback to template generator | reason=%s", exc)

    return build_page_from_template(payload)


def _format_task_plan(task_plan: list[Any] | None) -> str:
    if not task_plan:
        return ""

    lines: list[str] = []
    for index, task in enumerate(task_plan, start=1):
        task_data = task.model_dump() if hasattr(task, "model_dump") else dict(task)
        params = task_data.get("params", {})
        component_type = params.get("component_type")
        template_id = params.get("template_id")
        subject = params.get("subject")
        detail = ", ".join(
            str(value)
            for value in (component_type, template_id, subject)
            if value
        )
        lines.append(
            f"{index}. task_id={task_data.get('task_id')}; "
            f"action={task_data.get('action')}; "
            f"params={detail or params}"
        )
    return "\n".join(lines)


def build_page_from_template(payload: GenerationRequestDraft) -> PageDSL:
    subject = infer_subject(payload.prompt)
    audience = infer_audience(payload.page_type)
    goal = infer_goal(payload.page_type)

    page_meta = PageMeta(
        name=f"{subject}页面方案",
        page_type=payload.page_type,
        theme=payload.brand_style,
        audience=audience,
        goal=goal,
    )
    layout = LayoutConfig(template_id="tpl_single_column")

    hero_section = HeroBannerSection(
        section_id="hero_001",
        component_type="hero_banner",
        order=1,
        style_token=StyleToken(spacing="lg", background="brand", text_align="left"),
        props=HeroBannerProps(
            title=f"{subject}，让核心价值一眼看懂",
            subtitle=f"围绕{subject}的关键卖点、使用收益与行动引导，快速生成一页结构清晰的展示页面。",
            button_text="立即了解",
            image_url="https://images.unsplash.com/photo-1510017803434-a899398421b3?auto=format&fit=crop&w=1200&q=80",
        ),
    )

    feature_section = FeatureCardsSection(
        section_id="features_001",
        component_type="feature_cards",
        order=2,
        style_token=StyleToken(spacing="lg", background="white", text_align="center"),
        props=FeatureCardsProps(
            title="核心亮点",
            items=build_feature_items(subject),
        ),
    )

    cta_section = CTAButtonSection(
        section_id="cta_001",
        component_type="cta_button",
        order=3,
        style_token=StyleToken(spacing="md", background="light", text_align="center"),
        props=CTAButtonProps(
            title=f"现在开始了解{subject}",
            description="查看完整方案细节，并获取下一步行动建议。",
            button_text="获取方案",
            action_type="navigate",
            target_url="https://example.com/next-step",
        ),
    )

    return PageDSL(
        page_meta=page_meta,
        layout=layout,
        sections=[hero_section, feature_section, cta_section],
    )


def normalize_llm_payload(raw_payload: dict[str, Any], payload: GenerationRequestDraft) -> dict[str, Any]:
    subject = infer_subject(payload.prompt)
    audience = infer_audience(payload.page_type)
    goal = infer_goal(payload.page_type)

    page_meta = raw_payload.get("page_meta", {})
    normalized_page_meta = {
        "name": fit_text(
            page_meta.get("name") or page_meta.get("title") or f"{subject}页面方案",
            fallback=f"{subject}页面方案",
            max_length=40,
        ),
        "page_type": page_meta.get("page_type") or payload.page_type,
        "theme": page_meta.get("theme") or payload.brand_style,
        "audience": fit_text(
            page_meta.get("audience") or audience,
            fallback=audience,
            max_length=40,
        ),
        "goal": fit_text(
            page_meta.get("goal") or goal,
            fallback=goal,
            max_length=40,
        ),
    }

    layout = raw_payload.get("layout", {})
    normalized_layout = {
        "template_id": layout.get("template_id") or "tpl_single_column",
    }

    raw_sections = raw_payload.get("sections", [])
    normalized_sections = [
        normalize_section(section, index)
        for index, section in enumerate(raw_sections, start=1)
    ]

    return {
        "page_meta": normalized_page_meta,
        "layout": normalized_layout,
        "sections": normalized_sections,
    }


def normalize_section(section: dict[str, Any], order: int) -> dict[str, Any]:
    component_type = section.get("component_type") or section.get("component")
    props = section.get("props", {})

    normalized = {
        "section_id": section.get("section_id") or f"section_{order:03d}",
        "component_type": component_type,
        "order": section.get("order") or order,
        "style_token": section.get("style_token") or default_style_token(component_type),
        "props": normalize_props(component_type, props),
    }
    return normalized


def default_style_token(component_type: str | None) -> dict[str, str]:
    if component_type == "hero_banner":
        return {"spacing": "lg", "background": "brand", "text_align": "left"}
    if component_type == "feature_cards":
        return {"spacing": "lg", "background": "white", "text_align": "center"}
    return {"spacing": "md", "background": "light", "text_align": "center"}


def normalize_props(component_type: str | None, props: dict[str, Any]) -> dict[str, Any]:
    if component_type == "hero_banner":
        return {
            "title": fit_text(
                props.get("title") or props.get("headline") or "页面主标题",
                fallback="页面主标题",
                max_length=60,
            ),
            "subtitle": fit_text(
                props.get("subtitle") or props.get("subheadline") or "页面副标题",
                fallback="页面副标题",
                max_length=160,
            ),
            "button_text": fit_text(
                props.get("button_text") or props.get("cta_text") or "立即了解",
                fallback="立即了解",
                max_length=20,
            ),
            "image_url": props.get("image_url")
            or "https://images.unsplash.com/photo-1510017803434-a899398421b3?auto=format&fit=crop&w=1200&q=80",
        }

    if component_type == "feature_cards":
        raw_items = props.get("items") or props.get("cards") or []
        items = []
        for item in raw_items:
            items.append(
                {
                    "title": fit_text(
                        item.get("title") or "功能亮点",
                        fallback="功能亮点",
                        max_length=30,
                    ),
                    "description": fit_text(
                        item.get("description") or "功能描述",
                        fallback="功能描述",
                        max_length=80,
                    ),
                }
            )
        return {
            "title": fit_text(
                props.get("title") or props.get("headline") or "核心亮点",
                fallback="核心亮点",
                max_length=20,
            ),
            "items": items,
        }

    if component_type == "cta_button":
        target_url = props.get("target_url") or props.get("cta_link") or "https://example.com/next-step"
        raw_action_type = props.get("action_type") or "navigate"
        return {
            "title": fit_text(
                props.get("title") or props.get("headline") or "现在开始了解更多",
                fallback="现在开始了解更多",
                max_length=40,
            ),
            "description": fit_text(
                props.get("description") or props.get("subheadline") or "查看完整内容并进入下一步。",
                fallback="查看完整内容并进入下一步。",
                max_length=120,
            ),
            "button_text": fit_text(
                props.get("button_text") or props.get("cta_text") or "立即查看",
                fallback="立即查看",
                max_length=20,
            ),
            "action_type": normalize_action_type(raw_action_type),
            "target_url": target_url,
        }

    return props


def fit_text(value: Any, fallback: str, max_length: int) -> str:
    text = str(value).strip() if value is not None else fallback
    if not text:
        text = fallback
    if len(text) <= max_length:
        return text

    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_length:
        return compact

    return compact[:max_length].rstrip(" ,，。.;；:")


def normalize_action_type(value: Any) -> str:
    normalized = str(value).strip().lower() if value is not None else "navigate"
    alias_map = {
        "link": "navigate",
        "url": "navigate",
        "jump": "navigate",
        "redirect": "navigate",
        "submit": "submit_form",
        "form": "submit_form",
        "modal": "open_modal",
        "popup": "open_modal",
    }
    normalized = alias_map.get(normalized, normalized)
    if normalized in {"navigate", "submit_form", "open_modal"}:
        return normalized
    return "navigate"
