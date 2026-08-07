export type PageType = "landing_page" | "product_page" | "campaign_page";
export type ThemeType = "tech_clean" | "business_formal" | "growth_marketing";
export type BackgroundType = "white" | "light" | "dark" | "brand";
export type TextAlignType = "left" | "center";

export interface PageMeta {
  name: string;
  page_type: PageType;
  theme: ThemeType;
  audience: string;
  goal: string;
}

export interface LayoutConfig {
  template_id: string;
}

export interface StyleToken {
  spacing: "sm" | "md" | "lg";
  background: BackgroundType;
  text_align: TextAlignType;
}

export interface HeroBannerProps {
  title: string;
  subtitle: string;
  button_text: string;
  image_url: string;
}

export interface FeatureCardItem {
  title: string;
  description: string;
}

export interface FeatureCardsProps {
  title: string;
  items: FeatureCardItem[];
}

export interface CTAButtonProps {
  title: string;
  description: string;
  button_text: string;
  action_type: "navigate" | "submit_form" | "open_modal";
  target_url?: string | null;
}

export interface TestimonialItem {
  quote: string;
  author_name: string;
  author_title: string;
}

export interface TestimonialsProps {
  title: string;
  items: TestimonialItem[];
}

interface BaseSection {
  section_id: string;
  order: number;
  style_token: StyleToken;
}

export interface HeroBannerSection extends BaseSection {
  component_type: "hero_banner";
  props: HeroBannerProps;
}

export interface FeatureCardsSection extends BaseSection {
  component_type: "feature_cards";
  props: FeatureCardsProps;
}

export interface CTAButtonSection extends BaseSection {
  component_type: "cta_button";
  props: CTAButtonProps;
}

export interface TestimonialsSection extends BaseSection {
  component_type: "testimonials";
  props: TestimonialsProps;
}

export type PageSection = HeroBannerSection | FeatureCardsSection | CTAButtonSection | TestimonialsSection;

export interface PageDSL {
  page_meta: PageMeta;
  layout: LayoutConfig;
  sections: PageSection[];
}

export interface GeneratePageRequest {
  prompt: string;
  page_type: PageType;
  brand_style: ThemeType;
}

export interface GeneratePageResponse {
  request_id: string;
  status: "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED";
  celery_task_id?: string | null;
  page_id?: string | null;
  preview_url?: string | null;
  generation_source?: "llm" | "llm_normalized" | "fallback" | "revision" | null;
  agent_trace?: AgentTraceStep[];
  page_dsl?: PageDSL | null;
  error_message?: string | null;
}

export interface RevisePageRequest {
  page_id: string;
  instruction: string;
}

export interface StoredPageResponse {
  page_id: string;
  request_id?: string | null;
  generation_source?: "llm" | "llm_normalized" | "fallback" | "revision" | null;
  agent_trace?: AgentTraceStep[];
  page_dsl: PageDSL;
}

export interface AgentTraceStep {
  node: string;
  status: "success" | "failed";
  duration_ms: number;
  message: string;
  metadata: Record<string, unknown>;
}
