from __future__ import annotations

from typing import Any

from ...schemas.components import (
    CTAButtonProps,
    FeatureCardsProps,
    HeroBannerProps,
    StyleToken,
    TestimonialItem,
    TestimonialsProps,
)
from ...schemas.page_dsl import (
    CTAButtonSection,
    FeatureCardsSection,
    HeroBannerSection,
    LayoutConfig,
    TestimonialsSection,
)
from ...services.page_generator import build_feature_items


def select_layout_tool(params: dict[str, Any]) -> LayoutConfig:
    page_type = params.get("page_type")
    if page_type == "product_page":
        return LayoutConfig(template_id="tpl_product_story")
    if page_type == "campaign_page":
        return LayoutConfig(template_id="tpl_single_column_emphasis")
    return LayoutConfig(template_id=params.get("template_id") or "tpl_single_column")


def generate_hero_tool(params: dict[str, Any]) -> HeroBannerSection:
    subject = str(params.get("subject") or "产品方案")
    return HeroBannerSection(
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


def generate_features_tool(params: dict[str, Any]) -> FeatureCardsSection:
    subject = str(params.get("subject") or "产品方案")
    return FeatureCardsSection(
        section_id="features_001",
        component_type="feature_cards",
        order=2,
        style_token=StyleToken(spacing="lg", background="white", text_align="center"),
        props=FeatureCardsProps(
            title="核心亮点",
            items=build_feature_items(subject),
        ),
    )


def generate_cta_tool(params: dict[str, Any]) -> CTAButtonSection:
    subject = str(params.get("subject") or "产品方案")
    return CTAButtonSection(
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


def rewrite_hero_tool(params: dict[str, Any], base_section: HeroBannerSection | None = None) -> HeroBannerSection:
    subject = str(params.get("subject") or "产品方案")
    instruction = str(params.get("instruction") or "")
    title = f"{subject}，让核心价值一眼看懂"
    subtitle = f"围绕{subject}的关键卖点、使用收益与行动引导，快速生成一页结构清晰的展示页面。"

    if any(keyword in instruction for keyword in ("商务", "企业", "高端")):
        title = f"面向企业客户的{subject}解决方案"
        subtitle = f"以更专业、可信的表达方式呈现{subject}价值，帮助企业客户快速判断合作收益。"

    return HeroBannerSection(
        section_id=base_section.section_id if base_section else "hero_001",
        component_type="hero_banner",
        order=base_section.order if base_section else 1,
        style_token=base_section.style_token if base_section else StyleToken(spacing="lg", background="brand", text_align="left"),
        props=HeroBannerProps(
            title=title,
            subtitle=subtitle,
            button_text=base_section.props.button_text if base_section else "立即了解",
            image_url=base_section.props.image_url
            if base_section
            else "https://images.unsplash.com/photo-1510017803434-a899398421b3?auto=format&fit=crop&w=1200&q=80",
        ),
    )


def rewrite_features_tool(params: dict[str, Any], base_section: FeatureCardsSection | None = None) -> FeatureCardsSection:
    subject = str(params.get("subject") or "产品方案")
    section = generate_features_tool({"subject": subject})
    return FeatureCardsSection(
        section_id=base_section.section_id if base_section else section.section_id,
        component_type="feature_cards",
        order=base_section.order if base_section else section.order,
        style_token=base_section.style_token if base_section else section.style_token,
        props=section.props,
    )


def rewrite_cta_tool(params: dict[str, Any], base_section: CTAButtonSection | None = None) -> CTAButtonSection:
    subject = str(params.get("subject") or "产品方案")
    instruction = str(params.get("instruction") or "")
    button_text = "获取方案"
    if any(keyword in instruction for keyword in ("购买", "抢购")):
        button_text = "立即购买"
    elif any(keyword in instruction for keyword in ("咨询", "联系")):
        button_text = "预约咨询"
    elif any(keyword in instruction for keyword in ("报名", "活动")):
        button_text = "立即报名"

    return CTAButtonSection(
        section_id=base_section.section_id if base_section else "cta_001",
        component_type="cta_button",
        order=base_section.order if base_section else 3,
        style_token=base_section.style_token if base_section else StyleToken(spacing="md", background="light", text_align="center"),
        props=CTAButtonProps(
            title=f"现在开始了解{subject}",
            description="查看完整方案细节，并获取下一步行动建议。",
            button_text=button_text,
            action_type="navigate",
            target_url=base_section.props.target_url if base_section and base_section.props.target_url else "https://example.com/next-step",
        ),
    )


def generate_testimonials_tool(params: dict[str, Any], order: int) -> TestimonialsSection:
    subject = str(params.get("subject") or "产品方案")
    return TestimonialsSection(
        section_id="testimonials_001",
        component_type="testimonials",
        order=order,
        style_token=StyleToken(spacing="lg", background="white", text_align="center"),
        props=TestimonialsProps(
            title="客户评价",
            items=[
                TestimonialItem(
                    quote=f"{subject}页面让我们更快讲清楚产品价值，销售沟通效率明显提升。",
                    author_name="陈经理",
                    author_title="市场运营负责人",
                ),
                TestimonialItem(
                    quote="页面结构清晰，重点突出，适合快速用于活动推广和客户介绍。",
                    author_name="李女士",
                    author_title="业务增长负责人",
                ),
            ],
        ),
    )
