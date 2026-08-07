from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


ComponentType = Literal[
    "hero_banner",
    "feature_cards",
    "image_text",
    "cta_button",
    "faq",
    "testimonials",
]


COMPONENT_WHITELIST: tuple[str, ...] = (
    "hero_banner",
    "feature_cards",
    "image_text",
    "cta_button",
    "faq",
    "testimonials",
)


class StyleToken(BaseModel):
    spacing: Literal["sm", "md", "lg"] = "md"
    background: Literal["white", "light", "dark", "brand"] = "white"
    text_align: Literal["left", "center"] = "left"


class HeroBannerProps(BaseModel):
    title: str = Field(..., min_length=4, max_length=60)
    subtitle: str = Field(..., min_length=8, max_length=160)
    button_text: str = Field(..., min_length=2, max_length=20)
    image_url: str | HttpUrl


class FeatureCardItem(BaseModel):
    title: str = Field(..., min_length=2, max_length=30)
    description: str = Field(..., min_length=8, max_length=80)


class FeatureCardsProps(BaseModel):
    title: str = Field(..., min_length=2, max_length=20)
    items: list[FeatureCardItem] = Field(..., min_length=2, max_length=6)


class ImageTextProps(BaseModel):
    title: str = Field(..., min_length=2, max_length=30)
    description: str = Field(..., min_length=12, max_length=200)
    image_url: str | HttpUrl
    image_position: Literal["left", "right"] = "right"


class CTAButtonProps(BaseModel):
    title: str = Field(..., min_length=4, max_length=40)
    description: str = Field(..., min_length=8, max_length=120)
    button_text: str = Field(..., min_length=2, max_length=20)
    action_type: Literal["navigate", "submit_form", "open_modal"] = "navigate"
    target_url: str | HttpUrl | None = None


class FAQItem(BaseModel):
    question: str = Field(..., min_length=6, max_length=60)
    answer: str = Field(..., min_length=12, max_length=200)


class FAQProps(BaseModel):
    title: str = Field(..., min_length=2, max_length=20)
    items: list[FAQItem] = Field(..., min_length=2, max_length=8)


class TestimonialItem(BaseModel):
    quote: str = Field(..., min_length=12, max_length=120)
    author_name: str = Field(..., min_length=2, max_length=20)
    author_title: str = Field(..., min_length=2, max_length=40)


class TestimonialsProps(BaseModel):
    title: str = Field(..., min_length=2, max_length=20)
    items: list[TestimonialItem] = Field(..., min_length=1, max_length=6)
