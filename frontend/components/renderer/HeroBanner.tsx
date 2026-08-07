import type { HeroBannerSection } from "@/lib/pageDsl";

function backgroundClass(background: HeroBannerSection["style_token"]["background"]) {
  return background;
}

export default function HeroBanner({ section }: { section: HeroBannerSection }) {
  return (
    <section className={`section ${backgroundClass(section.style_token.background)} align-${section.style_token.text_align}`}>
      <div className="hero-grid">
        <div className="hero-copy">
          <h2>{section.props.title}</h2>
          <p>{section.props.subtitle}</p>
          <a className="cta-link" href="#cta-target">
            {section.props.button_text}
          </a>
        </div>
        <div className="hero-media">
          <img src={section.props.image_url} alt={section.props.title} />
        </div>
      </div>
    </section>
  );
}
