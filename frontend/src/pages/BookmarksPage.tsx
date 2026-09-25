import { useCallback, useEffect, useState } from "react";

import { bookmarks } from "../api/client";
import type { BookmarkItem } from "../api/types";
import ArticleCard from "../components/ArticleCard";
import LibraryTabs from "../components/LibraryTabs";

export default function BookmarksPage() {
  const [items, setItems] = useState<BookmarkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    bookmarks
      .list()
      .then((res) => active && setItems(res.items))
      .catch(() => active && setError("Could not load bookmarks"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [tick]);

  const articles = items.filter((b) => b.article).map((b) => b.article!);

  return (
    <div className="container">
      <div className="results-head">
        <h1 className="results-title">Library</h1>
      </div>
      <LibraryTabs />
      <p className="results-sub">Articles you’ve saved to read later.</p>

      {error && <div className="alert error">{error}</div>}
      {loading ? (
        <div className="center-block">
          <span className="spinner" />
        </div>
      ) : articles.length === 0 ? (
        <div className="empty-state">
          <div className="big">☆</div>
          <div>No bookmarks yet. Use “Save” on any search result.</div>
        </div>
      ) : (
        <>
          <p className="muted result-count">{articles.length} saved</p>
          {articles.map((a) => (
            <ArticleCard
              key={a.id}
              article={a}
              initialBookmarked
              onToggle={(now) => {
                if (!now) reload();
              }}
            />
          ))}
        </>
      )}
    </div>
  );
}
