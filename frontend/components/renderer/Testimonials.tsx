import type { TestimonialsSection } from "@/lib/pageDsl";

export default function Testimonials({ section }: { section: TestimonialsSection }) {
  return (
    <section className={`section ${section.style_token.background} align-${section.style_token.text_align}`}>
      <div className="testimonials-panel">
        <h3>{section.props.title}</h3>
        <div className="testimonial-grid">
          {section.props.items.map((item) => (
            <figure className="testimonial-item" key={`${item.author_name}-${item.author_title}`}>
              <blockquote>{item.quote}</blockquote>
              <figcaption>
                <strong>{item.author_name}</strong>
                <span>{item.author_title}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}
