from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .components import (
    CTAButtonProps,
    FAQProps,
    FeatureCardsProps,
    HeroBannerProps,
    ImageTextProps,
    TestimonialsProps,
    StyleToken,
)


PageType = Literal["landing_page", "product_page", "campaign_page"]
ThemeType = Literal["tech_clean", "business_formal", "growth_marketing"]
TemplateType = Literal[
    "tpl_single_column",
    "tpl_single_column_emphasis",
    "tpl_product_story",
]


class PageMeta(BaseModel):
    name: str = Field(..., min_length=4, max_length=40)
    page_type: PageType
    theme: ThemeType
    audience: str = Field(..., min_length=2, max_length=40)
    goal: str = Field(..., min_length=2, max_length=40)


class LayoutConfig(BaseModel):
    template_id: TemplateType


class BaseSection(BaseModel):
    section_id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    order: int = Field(..., ge=1, le=50)
    style_token: StyleToken = Field(default_factory=StyleToken)


class HeroBannerSection(BaseSection):
    component_type: Literal["hero_banner"]
    props: HeroBannerProps


class FeatureCardsSection(BaseSection):
    component_type: Literal["feature_cards"]
    props: FeatureCardsProps


class ImageTextSection(BaseSection):
    component_type: Literal["image_text"]
    props: ImageTextProps


class CTAButtonSection(BaseSection):
    component_type: Literal["cta_button"]
    props: CTAButtonProps


class FAQSection(BaseSection):
    component_type: Literal["faq"]
    props: FAQProps


class TestimonialsSection(BaseSection):
    component_type: Literal["testimonials"]
    props: TestimonialsProps


PageSection = Annotated[
    Union[
        HeroBannerSection,
        FeatureCardsSection,
        ImageTextSection,
        CTAButtonSection,
        FAQSection,
        TestimonialsSection,
    ],
    Field(discriminator="component_type"),
]


class PageDSL(BaseModel):
    page_meta: PageMeta
    layout: LayoutConfig
    sections: list[PageSection] = Field(..., min_length=3, max_length=12)


class GenerationRequestDraft(BaseModel):
    prompt: str = Field(..., min_length=8, max_length=20000)
    page_type: PageType
    brand_style: ThemeType


PHASE0_PAGE_REQUIREMENTS = {
    "page_types": ("landing_page", "product_page", "campaign_page"),
    "component_rules": {
        "required_any": ("hero_banner", "cta_button"),
        "recommended": ("feature_cards", "image_text", "faq", "testimonials"),
    },
    "section_count_range": (3, 12),
}
