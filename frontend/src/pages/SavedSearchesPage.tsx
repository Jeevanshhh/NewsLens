import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { search as searchApi } from "../api/client";
import type { SearchHistoryItem } from "../api/types";
import { formatDate } from "../utils/format";
import { PromptModal } from "../components/Modal";
import LibraryTabs from "../components/LibraryTabs";

export default function SavedSearchesPage() {
  const [items, setItems] = useState<SearchHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [target, setTarget] = useState<SearchHistoryItem | null>(null);
  const navigate = useNavigate();

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    searchApi
      .history(true)
      .then((res) => active && setItems(res.items))
      .catch(() => active && setError("Could not load saved searches"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [tick]);

  const open = (item: SearchHistoryItem) =>
    navigate(`/results/${item.id}`, {
      state: { query: item.name || item.query, filters: item.filters },
    });

  const doUnsave = async (item: SearchHistoryItem) => {
    try {
      await searchApi.unsave(item.id);
      refresh();
    } catch {
      setError("Could not unsave search");
    }
  };

  const doRename = async (name: string) => {
    if (!target) return;
    try {
      await searchApi.save(target.id, name || target.query);
      setTarget(null);
      refresh();
    } catch {
      setError("Could not update search");
    }
  };

  return (
    <div className="container">
      <div className="results-head">
        <h1 className="results-title">Library</h1>
      </div>
      <LibraryTabs />
      <p className="results-sub">Searches you’ve kept to revisit later.</p>

      {error && <div className="alert error">{error}</div>}
      {loading ? (
        <div className="center-block">
          <span className="spinner" />
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <div className="big">🔖</div>
          <div>No saved searches yet. Run a search and choose “Save search”.</div>
        </div>
      ) : (
        <div className="lib-list">
          {items.map((item) => (
            <div className="card lib-item" key={item.id}>
              <span className="lib-ico" style={{ background: "var(--grad-brand)" }}>🔎</span>
              <div className="lib-main">
                <div className="lib-title">{item.name || item.query}</div>
                <div className="lib-meta">
                  {item.query} · {item.result_count} result{item.result_count === 1 ? "" : "s"}
                  {item.created_at ? ` · saved ${formatDate(item.created_at)}` : ""}
                </div>
              </div>
              <div className="lib-actions">
                <button className="btn small primary" onClick={() => open(item)}>
                  Open
                </button>
                <button className="btn small" onClick={() => setTarget(item)}>
                  Rename
                </button>
                <button className="btn small danger" onClick={() => doUnsave(item)}>
                  Unsave
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <PromptModal
        open={target !== null}
        title="Rename saved search"
        label="Name"
        initialValue={target?.name ?? ""}
        confirmText="Save"
        onCancel={() => setTarget(null)}
        onSubmit={doRename}
      />
    </div>
  );
}
