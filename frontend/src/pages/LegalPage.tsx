import { Link, useParams } from "react-router-dom";

import { CONTACT_EMAIL, LEGAL_DOCS, LEGAL_NAV, type LegalDoc } from "../legal/content";

const SLUGS = LEGAL_NAV.map((n) => n.slug);

export default function LegalPage({ slug }: { slug?: string }) {
  const params = useParams();
  const active = slug ?? params.slug ?? "about";
  const doc: LegalDoc | undefined = LEGAL_DOCS[active];

  if (!doc || !SLUGS.includes(active)) {
    return (
      <div className="legal-wrap">
        <div className="card legal-card">
          <h1>Page not found</h1>
          <p className="muted">
            That page isn’t here. <Link to="/about">Back to About</Link>.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="legal-wrap">
      <header className="legal-header">
        <Link to="/" className="brand">
          <span className="logo">◐</span> NewsLens
        </Link>
      </header>

      <div className="legal-body">
        <nav className="legal-nav" aria-label="Legal">
          {LEGAL_NAV.map((item) => (
            <Link
              key={item.slug}
              to={`/${item.slug}`}
              className={item.slug === active ? "active" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <main className="card legal-card">
          <h1>{doc.title}</h1>
          <p className="muted legal-updated">Last updated: {doc.updated}</p>
          <p className="legal-intro">{doc.intro}</p>

          {doc.sections.map((section, i) => (
            <section key={i} className="legal-section">
              {section.heading && <h2>{section.heading}</h2>}
              {section.paragraphs.map((p, j) => (
                <p key={j}>{p}</p>
              ))}
            </section>
          ))}
        </main>
      </div>

      <footer className="legal-footer">
        <span className="muted">
          NewsLens is a research prototype · <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        </span>
      </footer>
    </div>
  );
}
