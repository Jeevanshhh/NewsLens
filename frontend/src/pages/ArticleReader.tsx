import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { articles as articlesApi, bookmarks } from "../api/client";
import type { Article } from "../api/types";
import {
  decodeHtmlEntities,
  formatDate,
  isMeaningful,
  relativeTime,
  titleCase,
} from "../utils/format";

// In-app reader. Shows only legitimately-stored metadata (headline, source,
// date, image, snippet, classification) plus related coverage and a link to
// the original publisher. We do NOT fetch or republish full copyrighted text.
export default function ArticleReader() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const navigate = useNavigate();

  const [article, setArticle] = useState<Article | null>(null);
  const [related, setRelated] = useState<Article[]>([]);
  const [bookmarked, setBookmarked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Hide the hero image if its URL fails to load - no broken-image box.
  const [heroFailed, setHeroFailed] = useState(false);

  useEffect(() => {
    if (Number.isNaN(id)) {
      setError("Invalid article.");
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([articlesApi.detail(id), articlesApi.related(id, 6)])
      .then(([detail, rel]) => {
        if (!active) return;
        setArticle(detail);
        setRelated(rel.items);
      })
      .catch(() => active && setError("Could not load this article."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [id]);

  useEffect(() => {
    if (!article) return;
    let active = true;
    bookmarks
      .status([article.id])
      .then((res) => active && setBookmarked(Boolean(res.status[String(article.id)])))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [article]);

  const toggle = useCallback(async () => {
    if (!article || busy) return;
    setBusy(true);
    const next = !bookmarked;
    try {
      if (next) await bookmarks.add(article.id);
      else await bookmarks.remove(article.id);
      setBookmarked(next);
    } catch {
      setError("Could not update bookmark.");
    } finally {
      setBusy(false);
    }
  }, [article, bookmarked, busy]);

  if (loading) {
    return (
      <div className="container">
        <div className="center-block">
          <span className="spinner" />
        </div>
      </div>
    );
  }

  if (error && !article) {
    return (
      <div className="container">
        <div className="results-head">
          <button className="back-link" onClick={() => navigate(-1)}>
            ‹ Back
          </button>
        </div>
        <div className="alert error">{error}</div>
      </div>
    );
  }

  const a = article!;
  const title = decodeHtmlEntities(a.title);
  const rawDesc = decodeHtmlEntities(a.description);
  const source = decodeHtmlEntities(a.source) || a.provider;
  const initials = (source || "?").replace(/[^a-zA-Z]/g, "").slice(0, 2).toUpperCase();
  const when = a.published_at ?? a.published_date;

  const facts: { k: string; v: string }[] = [
    { k: "Source", v: source },
    { k: "Provider", v: titleCase(a.provider) },
    { k: "Published", v: formatDate(when) },
  ];
  if (isMeaningful(a.author)) facts.push({ k: "Author", v: decodeHtmlEntities(a.author)! });
  if (isMeaningful(a.category)) facts.push({ k: "Topic", v: titleCase(a.category) });
  if (isMeaningful(a.state)) facts.push({ k: "Location", v: titleCase(a.state) });
  if (isMeaningful(a.country)) facts.push({ k: "Country", v: titleCase(a.country) });
  if (isMeaningful(a.language)) facts.push({ k: "Language", v: (a.language ?? "").toUpperCase() });

  return (
    <div className="container">
      <div className="reader">
        <div className="reader-main">
          <div className="reader-topbar">
            <button className="back-link" onClick={() => navigate(-1)}>
              ‹ Back to results
            </button>
            <div className="row-actions">
              <button
                className={`btn small bookmark${bookmarked ? " on" : ""}`}
                onClick={toggle}
                disabled={busy}
                aria-pressed={bookmarked}
              >
                {bookmarked ? "★ Saved" : "☆ Save"}
              </button>
              <a
                className="btn small primary"
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open Original Source ↗
              </a>
            </div>
          </div>

          <div className="reader-src">
            <span className="src-badge" title={source}>
              {initials || "•"}
            </span>
            <strong>{source}</strong>
            {when && (
              <span className="muted">
                · {relativeTime(when) || formatDate(when)}
              </span>
            )}
          </div>

          <h1 className="reader-title">{title}</h1>

          {a.image_url && !heroFailed && (
            <img
              className="reader-hero"
              src={a.image_url}
              alt=""
              loading="lazy"
              onError={() => setHeroFailed(true)}
            />
          )}

          {rawDesc ? (
            <p className="reader-text">{rawDesc}</p>
          ) : (
            <p className="muted">
              This source did not provide a summary snippet.
            </p>
          )}

          <div className="reader-note">
            NewsLens stores headline and metadata only and links out to the
            publisher. To read the full article, open the original source.
          </div>

          <section className="keyinfo">
            <h3>Key Information</h3>
            <div className="keyinfo-grid">
              {facts.map((f) => (
                <div className="keyinfo-item card" key={f.k}>
                  <div className="k">{f.k}</div>
                  <div className="v">{f.v}</div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <aside className="related">
          <h3>Related Coverage</h3>
          {related.length === 0 ? (
            <p className="muted">No related articles in your corpus yet.</p>
          ) : (
            <div className="related-list">
              {related.map((r) => (
                <a
                  key={r.id}
                  className="related-item"
                  href={`/articles/${r.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(`/articles/${r.id}`);
                  }}
                >
                  {r.image_url ? (
                    <img
                      className="related-thumb"
                      src={r.image_url}
                      alt=""
                      loading="lazy"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  ) : null}
                  <div style={{ minWidth: 0 }}>
                    <div className="related-title">{decodeHtmlEntities(r.title)}</div>
                    <div className="related-meta">
                      {decodeHtmlEntities(r.source) || r.provider}
                      {r.published_at ? ` · ${relativeTime(r.published_at)}` : ""}
                    </div>
                  </div>
                </a>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
