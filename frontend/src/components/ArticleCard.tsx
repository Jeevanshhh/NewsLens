import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Article } from "../api/types";
import { bookmarks } from "../api/client";
import { decodeHtmlEntities, isMeaningful, relativeTime } from "../utils/format";

interface Props {
  article: Article;
  initialBookmarked: boolean;
  onToggle?: (bookmarkedNow: boolean) => void;
}

// Collapse to letters/digits so punctuation and source-name differences don't
// stop us from spotting a description that merely echoes the headline.
function isRedundantSnippet(title: string, desc: string): boolean {
  if (!desc) return true;
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const t = norm(title);
  const d = norm(desc);
  if (!d) return true;
  if (!t) return false;
  const rest = d.replace(t, " ").trim();
  return rest.length < 15;
}

export default function ArticleCard({ article, initialBookmarked, onToggle }: Props) {
  const [bookmarked, setBookmarked] = useState(initialBookmarked);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A provider image URL can 404 or be hotlink-blocked; if it fails we drop
  // back to the existing text-first placeholder rather than showing a broken box.
  const [imgFailed, setImgFailed] = useState(false);
  const navigate = useNavigate();

  const toggle = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    const next = !bookmarked;
    try {
      if (next) await bookmarks.add(article.id);
      else await bookmarks.remove(article.id);
      setBookmarked(next);
      onToggle?.(next);
    } catch {
      setError("Could not update bookmark");
    } finally {
      setBusy(false);
    }
  };

  const open = () => navigate(`/articles/${article.id}`);

  const title = decodeHtmlEntities(article.title);
  const rawDesc = decodeHtmlEntities(article.description);
  const when = relativeTime(article.published_at ?? article.published_date);
  const source = decodeHtmlEntities(article.source) || article.provider;
  const description = isRedundantSnippet(title, rawDesc) ? "" : rawDesc;
  const initials = (source || "?").replace(/[^a-zA-Z]/g, "").slice(0, 2).toUpperCase();

  const chips = [article.category, article.state, article.country].filter(isMeaningful);

  return (
    <article className="card article">
      {article.image_url && !imgFailed ? (
        <img
          className="article-thumb"
          src={article.image_url}
          alt=""
          loading="lazy"
          onError={() => setImgFailed(true)}
        />
      ) : (
        <div className="article-thumb placeholder" aria-hidden>
          🗞️
        </div>
      )}

      <div className="article-body">
        <a className="article-title" href={`/articles/${article.id}`} onClick={(e) => { e.preventDefault(); open(); }}>
          {title}
        </a>

        <div className="article-meta">
          <span className="src-badge" title={source}>{initials || "•"}</span>
          <span>{source}</span>
          {when && (
            <>
              <span>·</span>
              <span>{when}</span>
            </>
          )}
        </div>

        {description && <p className="article-desc">{description}</p>}

        <div className="article-foot">
          {chips.length > 0 ? (
            <div className="chips">
              {chips.map((c) => (
                <span key={c} className="chip">
                  {c}
                </span>
              ))}
            </div>
          ) : (
            <span />
          )}

          <div className="article-actions">
            <button
              className={`btn small bookmark${bookmarked ? " on" : ""}`}
              onClick={toggle}
              disabled={busy}
              aria-pressed={bookmarked}
            >
              {bookmarked ? "★ Saved" : "☆ Save"}
            </button>
            <button className="btn small" onClick={open}>
              Read →
            </button>
          </div>
        </div>
        {error && <div className="alert error" style={{ marginTop: "0.5rem" }}>{error}</div>}
      </div>
    </article>
  );
}
