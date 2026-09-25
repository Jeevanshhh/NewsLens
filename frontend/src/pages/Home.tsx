import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { news, search as searchApi } from "../api/client";
import { ApiError } from "../api/client";
import type { LiveHeadline } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { decodeHtmlEntities, relativeTime } from "../utils/format";

const SOURCE_OPTIONS = [
  { value: "google_news", label: "Google News" },
  { value: "all", label: "All sources" },
  { value: "gnews", label: "GNews" },
  { value: "newsdata", label: "NewsData" },
];

const DATE_OPTIONS = [
  { value: "", label: "Any time" },
  { value: "day", label: "Last 24 hours" },
  { value: "week", label: "Last 7 days" },
  { value: "month", label: "Last 30 days" },
];

const POPULAR = [
  "climate change",
  "AI regulation",
  "stock market",
  "sports news",
  "space exploration",
  "global economy",
];

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Home() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("google_news");
  const [dateRange, setDateRange] = useState("");
  const [maxResults, setMaxResults] = useState(50);
  const [moreOpen, setMoreOpen] = useState(false);
  const [language, setLanguage] = useState("en");
  const [country, setCountry] = useState("IN");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [live, setLive] = useState<LiveHeadline[]>([]);
  const [liveState, setLiveState] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const autoRan = useRef(false);

  useEffect(() => {
    let active = true;
    news
      .live(8)
      .then((res) => {
        if (!active) return;
        setLive(res.items);
        setLiveState(res.items.length ? "ready" : "empty");
      })
      .catch(() => active && setLiveState("error"));
    return () => {
      active = false;
    };
  }, []);

  const run = async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    const sources = source === "all" ? ["google_news", "gnews", "newsdata"] : [source];
    const days = dateRange === "day" ? 1 : dateRange === "week" ? 7 : dateRange === "month" ? 30 : 0;
    try {
      const res = await searchApi.run({
        query: trimmed,
        sources,
        max_results: maxResults,
        from_date: days ? isoDaysAgo(days) : undefined,
        language,
        country,
      });
      navigate(`/results/${res.search_id}`, {
        state: { query: res.query, justSearched: true, result: res },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Search failed. Is the backend running?");
      setBusy(false);
    }
  };

  // Auto-run a search handed over from the top bar (?q=...).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q && !autoRan.current) {
      autoRan.current = true;
      setQuery(q);
      void run(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(query);
  };

  const firstName = (user?.name || "").split(" ")[0];

  return (
    <div className="home">
      <div className="home-hero">
        <p className="greeting">
          {greeting()}
          {firstName ? `, ${firstName}` : ""} 👋
        </p>
        <h1>What would you like to know about today?</h1>
        <p className="tagline">
          Search for news, topics, people, locations or events in natural language.
        </p>

        <form onSubmit={submit}>
          <div className="search-box">
            <input
              autoFocus
              value={query}
              placeholder="e.g. Show me news about accidents in Delhi"
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search query"
            />
            <button className="go" disabled={busy || !query.trim()} aria-label="Search">
              {busy ? (
                <span className="spinner" style={{ borderColor: "#fff", borderTopColor: "transparent" }} />
              ) : (
                "🔍"
              )}
            </button>
          </div>

          <div className="filters-row">
            <select value={dateRange} onChange={(e) => setDateRange(e.target.value)} aria-label="Date">
              {DATE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Sources">
              {SOURCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <select value={maxResults} onChange={(e) => setMaxResults(Number(e.target.value))} aria-label="Max results">
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>Max results: {n}</option>
              ))}
            </select>
            <button type="button" className="btn" onClick={() => setMoreOpen((o) => !o)}>
              ⚙ More filters
            </button>
          </div>

          {moreOpen && (
            <div className="filters-row" style={{ marginTop: 8 }}>
              <select value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Language">
                <option value="en">English</option>
                <option value="hi">Hindi</option>
              </select>
              <select value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country">
                <option value="IN">India</option>
                <option value="US">United States</option>
                <option value="GB">United Kingdom</option>
                <option value="AU">Australia</option>
              </select>
            </div>
          )}
        </form>

        {error && <div className="alert error" style={{ marginTop: "1rem" }}>{error}</div>}

        <div className="section-label">Popular searches</div>
        <div className="suggestions">
          {POPULAR.map((s) => (
            <button key={s} className="suggestion" onClick={() => { setQuery(s); void run(s); }}>
              {s}
            </button>
          ))}
        </div>

        <p className="hint">Press Enter to search. Google News works without an API key.</p>
      </div>

      <aside className="live-brief glass">
        <div className="live-head">
          <span className="live-dot" />
          <h3>Live Brief</h3>
        </div>
        <div className="live-sub">Global headlines · from Google News</div>

        {liveState === "loading" && (
          <div className="live-list">
            {Array.from({ length: 5 }).map((_, i) => (
              <div className="live-item" key={i}>
                <div className="skeleton" style={{ width: 46, height: 46, borderRadius: 10, flex: "none" }} />
                <div style={{ flex: 1 }}>
                  <div className="skeleton" style={{ height: 12, marginBottom: 6 }} />
                  <div className="skeleton" style={{ height: 12, width: "60%" }} />
                </div>
              </div>
            ))}
          </div>
        )}
        {liveState === "error" && <div className="live-sub">Live headlines unavailable right now.</div>}
        {liveState === "empty" && <div className="live-sub">No current headlines returned.</div>}
        {liveState === "ready" && (
          <div className="live-list">
            {live.map((h, i) => (
              <a
                className="live-item"
                key={i}
                href={h.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {h.image_url ? (
                  <img
                    className="live-thumb"
                    src={h.image_url}
                    alt=""
                    loading="lazy"
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                    }}
                  />
                ) : null}
                <div className="live-info">
                  <div className="live-title">{decodeHtmlEntities(h.title)}</div>
                  <div className="live-meta">
                    {h.source ? `${decodeHtmlEntities(h.source)} · ` : ""}
                    {relativeTime(h.published_at) || "recent"}
                  </div>
                </div>
              </a>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
