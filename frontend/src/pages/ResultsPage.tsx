import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import {
  articles as articlesApi,
  bookmarks,
  search as searchApi,
} from "../api/client";
import type { Article, ArticlesList, SearchRunResult } from "../api/types";
import ArticleCard from "../components/ArticleCard";
import ExportMenu from "../components/ExportMenu";
import Pagination from "../components/Pagination";
import { PromptModal } from "../components/Modal";

const SOURCES = ["google_news", "gnews", "newsdata"];

interface LocationState {
  query?: string;
  justSearched?: boolean;
  result?: SearchRunResult;
}

export default function ResultsPage() {
  const { searchId: searchIdParam } = useParams();
  const searchId = Number(searchIdParam);
  const location = useLocation();
  const state = (location.state as LocationState | null) ?? null;

  const [query, setQuery] = useState<string>(state?.query ?? "");
  // Search-run summary only exists right after a fresh search; on restore it's null.
  const runInfo: SearchRunResult | null = state?.justSearched
    ? state.result ?? null
    : null;

  const [provider, setProvider] = useState("");
  const [category, setCategory] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [sort, setSort] = useState("date_desc");
  const [term, setTerm] = useState(""); // free-text filter within these results
  const [page, setPage] = useState(1);

  const [list, setList] = useState<ArticlesList | null>(null);
  const [marked, setMarked] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [saved, setSaved] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);

  // Resolve the query label when landing directly (refresh / sidebar restore)
  // and no query came through router state.
  useEffect(() => {
    if (query || Number.isNaN(searchId)) return;
    let active = true;
    searchApi
      .history(false)
      .then((res) => {
        const found = res.items.find((i) => i.id === searchId);
        if (active && found) setQuery(found.name || found.query);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [searchId, query]);

  const load = useCallback(async () => {
    if (Number.isNaN(searchId)) {
      setError("Invalid search.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await articlesApi.list({
        search_id: searchId,
        provider: provider || undefined,
        category: category || undefined,
        state: stateFilter || undefined,
        sort,
        q: term || undefined,
        page,
        page_size: 10,
      });
      setList(res);
      const ids = res.items.map((a: Article) => a.id);
      if (ids.length) {
        const st = await bookmarks.status(ids);
        setMarked(
          new Set(
            Object.entries(st.status)
              .filter(([, v]) => v)
              .map(([k]) => Number(k)),
          ),
        );
      } else {
        setMarked(new Set());
      }
    } catch {
      setError("Could not load results. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, [searchId, provider, category, stateFilter, sort, term, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSaveSearch = async (name: string) => {
    setPromptOpen(false);
    try {
      await searchApi.save(searchId, name || undefined);
      setSaved(true);
    } catch {
      setError("Could not save search");
    }
  };

  const exportParams = {
    search_id: searchId,
    provider: provider || undefined,
    category: category || undefined,
    state: stateFilter || undefined,
    sort,
  };

  const activeChips = [
    provider && { key: "provider", label: `Source: ${provider}`, clear: () => setProvider("") },
    category && { key: "category", label: `Topic: ${category}`, clear: () => setCategory("") },
    stateFilter && { key: "state", label: `Location: ${stateFilter}`, clear: () => setStateFilter("") },
    term && { key: "term", label: `Contains: “${term}”`, clear: () => setTerm("") },
  ].filter(Boolean) as { key: string; label: string; clear: () => void }[];

  const clearAll = () => {
    setProvider("");
    setCategory("");
    setStateFilter("");
    setTerm("");
    setPage(1);
  };

  return (
    <div className="container">
      <div className="results-head">
        <Link to="/" className="back-link">
          ‹ New search
        </Link>
        <div className="row-actions">
          <button
            className="btn small"
            onClick={() => setPromptOpen(true)}
            disabled={saved}
          >
            {saved ? "Saved ✓" : "☆ Save search"}
          </button>
          <ExportMenu params={exportParams} />
        </div>
      </div>

      <h1 className="results-title">{query || "Search results"}</h1>
      <p className="results-sub">
        {runInfo
          ? `Collected ${runInfo.total_collected} · ${runInfo.unique_results} unique · ${runInfo.new_stored} new`
          : list
            ? `${list.total} article${list.total === 1 ? "" : "s"}`
            : ""}
      </p>

      <div className="toolbar">
        <div className="filters">
          <input
            style={{ minWidth: "180px" }}
            placeholder="Filter these results…"
            value={term}
            onChange={(e) => {
              setTerm(e.target.value);
              setPage(1);
            }}
            aria-label="Filter results"
          />
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setPage(1);
            }}
            aria-label="Source"
          >
            <option value="">All sources</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            style={{ minWidth: "130px" }}
            placeholder="Topic (e.g. Sports)"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(1);
            }}
            aria-label="Topic filter"
          />
          <input
            style={{ minWidth: "130px" }}
            placeholder="Location (e.g. Delhi)"
            value={stateFilter}
            onChange={(e) => {
              setStateFilter(e.target.value);
              setPage(1);
            }}
            aria-label="Location filter"
          />
          <select
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setPage(1);
            }}
            aria-label="Sort"
          >
            <option value="date_desc">Newest first</option>
            <option value="date_asc">Oldest first</option>
          </select>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      {activeChips.length > 0 && (
        <div className="active-filters">
          {activeChips.map((c) => (
            <span className="fchip" key={c.key}>
              {c.label}
              <button onClick={c.clear} aria-label={`Clear ${c.label}`}>
                ×
              </button>
            </span>
          ))}
          <button className="clear-all" onClick={clearAll}>
            Clear all
          </button>
        </div>
      )}

      {loading ? (
        <div className="center-block">
          <span className="spinner" />
        </div>
      ) : !list || list.items.length === 0 ? (
        <div className="empty-state">
          <div className="big">🗞️</div>
          <div>No articles match these filters.</div>
        </div>
      ) : (
        <>
          {list.items.map((a) => (
            <ArticleCard
              key={a.id}
              article={a}
              initialBookmarked={marked.has(a.id)}
            />
          ))}
          <Pagination page={list.page} pages={list.pages} onChange={setPage} />
        </>
      )}

      <PromptModal
        open={promptOpen}
        title="Save this search"
        label="Name (optional)"
        placeholder={query || "My saved search"}
        confirmText="Save"
        initialValue=""
        onCancel={() => setPromptOpen(false)}
        onSubmit={onSaveSearch}
      />
    </div>
  );
}
