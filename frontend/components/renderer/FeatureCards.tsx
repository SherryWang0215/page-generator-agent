import type { FeatureCardsSection } from "@/lib/pageDsl";

export default function FeatureCards({ section }: { section: FeatureCardsSection }) {
  return (
    <section className={`section ${section.style_token.background} align-${section.style_token.text_align}`}>
      <div className="feature-panel">
        <h3>{section.props.title}</h3>
        <div className="feature-grid">
          {section.props.items.map((item) => (
            <article className="feature-item" key={item.title}>
              <h4>{item.title}</h4>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
