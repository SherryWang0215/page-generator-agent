import type { CTAButtonSection } from "@/lib/pageDsl";

export default function CTAButton({ section }: { section: CTAButtonSection }) {
  return (
    <section
      id="cta-target"
      className={`section ${section.style_token.background} align-${section.style_token.text_align}`}
    >
      <div className="cta-panel">
        <h3>{section.props.title}</h3>
        <p>{section.props.description}</p>
        <a className="cta-link" href={section.props.target_url ?? "#"}>
          {section.props.button_text}
        </a>
      </div>
    </section>
  );
}
