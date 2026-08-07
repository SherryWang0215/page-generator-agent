import CTAButton from "./CTAButton";
import FeatureCards from "./FeatureCards";
import HeroBanner from "./HeroBanner";
import Testimonials from "./Testimonials";
import type {
  CTAButtonSection,
  FeatureCardsSection,
  HeroBannerSection,
  PageDSL,
  PageSection,
  TestimonialsSection,
} from "@/lib/pageDsl";

function renderSection(section: PageSection) {
  switch (section.component_type) {
    case "hero_banner":
      return <HeroBanner key={section.section_id} section={section as HeroBannerSection} />;
    case "feature_cards":
      return <FeatureCards key={section.section_id} section={section as FeatureCardsSection} />;
    case "cta_button":
      return <CTAButton key={section.section_id} section={section as CTAButtonSection} />;
    case "testimonials":
      return <Testimonials key={section.section_id} section={section as TestimonialsSection} />;
    default:
      return null;
  }
}

export default function PageRenderer({ page }: { page: PageDSL }) {
  const orderedSections = [...page.sections].sort((left, right) => left.order - right.order);
  return <>{orderedSections.map((section) => renderSection(section))}</>;
}
