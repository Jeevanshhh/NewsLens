import { useEffect, useState } from "react";

import { analytics } from "../api/client";
import type { AnalyticsOverview, DistEntry, TimelineEntry } from "../api/types";
import ExportMenu from "../components/ExportMenu";
import LocationMap from "../components/LocationMap";
import { titleCase } from "../utils/format";

const SOURCES = ["google_news", "gnews", "newsdata"];

// Filter out the rule-based classifier's neutral placeholders so we never show
// an "Unknown"/"Other" bar or donut slice as if it were a real category.
function meaningfulRows(rows: DistEntry[]): DistEntry[] {
  return rows.filter((r) => {
    const k = (r.key ?? "").trim().toLowerCase();
    return k !== "" && k !== "unknown" && k !== "other" && k !== "n/a" && k !== "none";
  });
}

const PALETTE = ["#4f46e5", "#2563eb", "#06b6d4", "#8b5cf6", "#f59e0b", "#16a34a", "#ef4444", "#0ea5e9"];

function StatCard({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="card stat-card">
      <div className="label">{label}</div>
      <div className="stat-num">{value.toLocaleString()}</div>
      {hint && <div className="stat-delta flat">{hint}</div>}
    </div>
  );
}

function LineChart({ data }: { data: TimelineEntry[] }) {
  const w = 640;
  const h = 220;
  const pad = { l: 34, r: 12, t: 14, b: 26 };
  const rows = data.slice(-14);
  if (rows.length === 0) return <p className="muted">No timeline data yet.</p>;

  const max = Math.max(...rows.map((r) => r.count), 1);
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const stepX = rows.length > 1 ? innerW / (rows.length - 1) : 0;
  const pts = rows.map((r, i) => {
    const x = pad.l + i * stepX;
    const y = pad.t + innerH - (r.count / max) * innerH;
    return { x, y, r };
  });
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = `${line} L${pts[pts.length - 1].x.toFixed(1)},${(pad.t + innerH).toFixed(1)} L${pts[0].x.toFixed(1)},${(pad.t + innerH).toFixed(1)} Z`;

  return (
    <svg className="linechart" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Articles over time">
      <defs>
        <linearGradient id="lcFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 0.25, 0.5, 0.75, 1].map((g) => {
        const y = pad.t + innerH * g;
        return <line key={g} x1={pad.l} y1={y} x2={w - pad.r} y2={y} style={{ stroke: "var(--border)" }} strokeWidth={1} />;
      })}
      <path d={area} fill="url(#lcFill)" />
      <path d={line} fill="none" style={{ stroke: "var(--accent)" }} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} style={{ fill: "var(--surface)", stroke: "var(--accent)" }} strokeWidth={2} />
      ))}
      {pts.map((p, i) =>
        i % Math.ceil(pts.length / 6 || 1) === 0 ? (
          <text key={`t${i}`} x={p.x} y={h - 8} fontSize={10} style={{ fill: "var(--muted)" }} textAnchor="middle">
            {new Date(p.r.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          </text>
        ) : null,
      )}
    </svg>
  );
}

function Donut({ data }: { data: DistEntry[] }) {
  const rows = meaningfulRows(data);
  if (rows.length === 0) return <p className="muted">No source data yet.</p>;
  const total = rows.reduce((s, r) => s + r.count, 0) || 1;
  const r = 60;
  const circ = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="donut-wrap">
      <svg className="donut" viewBox="0 0 160 160" role="img" aria-label="Share by source">
        <g transform="rotate(-90 80 80)">
          <circle cx="80" cy="80" r={r} fill="none" style={{ stroke: "var(--border)" }} strokeWidth={20} />
          {rows.map((row, i) => {
            const frac = row.count / total;
            const dash = frac * circ;
            const el = (
              <circle
                key={row.key ?? i}
                cx="80"
                cy="80"
                r={r}
                fill="none"
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={20}
                strokeDasharray={`${dash} ${circ - dash}`}
                strokeDashoffset={-offset}
              />
            );
            offset += dash;
            return el;
          })}
        </g>
        <text x="80" y="76" textAnchor="middle" fontSize="20" fontWeight="700" style={{ fill: "var(--text)" }}>{total}</text>
        <text x="80" y="92" textAnchor="middle" fontSize="10" style={{ fill: "var(--muted)" }}>articles</text>
      </svg>
      <ul className="legend">
        {rows.map((row, i) => (
          <li className="legend-item" key={row.key ?? i}>
            <span className="swatch" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="lname">{titleCase(row.key)}</span>
            <span className="lval">{row.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Bars({ title, data, empty }: { title: string; data: DistEntry[]; empty?: string }) {
  const rows = meaningfulRows(data).slice(0, 8);
  const max = rows.reduce((m, r) => Math.max(m, r.count), 0) || 1;
  return (
    <section className="card panel">
      <h3 className="panel-title">{title}</h3>
      {rows.length === 0 ? (
        <p className="muted">{empty ?? "No data yet."}</p>
      ) : (
        <ul className="bars">
          {rows.map((row) => (
            <li className="bar-row" key={row.key ?? "x"}>
              <span className="bar-label" title={row.key ?? ""}>{titleCase(row.key)}</span>
              <span className="bar-track">
                <span className="bar-fill" style={{ width: `${(row.count / max) * 100}%` }} />
              </span>
              <span className="bar-count">{row.count}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [provider, setProvider] = useState("");
  const [state, setState] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    analytics
      .overview({ provider: provider || undefined, state: state || undefined })
      .then((d) => active && setData(d))
      .catch(() => active && setError("Could not load analytics"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [provider, state]);

  return (
    <div className="container">
      <div className="results-head">
        <div>
          <h1 className="results-title">Analytics</h1>
          <p className="results-sub">A research view of everything you’ve collected.</p>
        </div>
        <ExportMenu params={{ provider: provider || undefined, state: state || undefined }} />
      </div>

      <div className="toolbar">
        <div className="filters">
          <select value={provider} onChange={(e) => setProvider(e.target.value)} aria-label="Source">
            <option value="">All sources</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input
            style={{ minWidth: "160px" }}
            value={state}
            placeholder="Location (e.g. Delhi)"
            onChange={(e) => setState(e.target.value)}
            aria-label="Location"
          />
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}
      {loading ? (
        <div className="center-block">
          <span className="spinner" />
        </div>
      ) : (
        <>
          <div className="stat-cards">
            <StatCard label="Total articles" value={data?.total_articles ?? 0} />
            <StatCard label="Unique articles" value={data?.unique_articles ?? 0} hint="after URL de-duplication" />
            <StatCard label="Sources" value={data?.source_count ?? 0} hint="distinct providers" />
            <StatCard label="Searches run" value={data?.search_count ?? 0} hint="by you" />
          </div>

          <section className="card panel">
            <h3 className="panel-title">Articles over time</h3>
            <LineChart data={data?.timeline ?? []} />
          </section>

          <div className="grid-2">
            <section className="card panel">
              <h3 className="panel-title">Share by source</h3>
              <Donut data={data?.by_provider ?? []} />
            </section>
            <Bars title="By topic" data={data?.by_category ?? []} empty="Topics are assigned automatically (keyword rules with a topic-model fallback) once enough articles exist." />
          </div>

          <section className="card panel">
            <h3 className="panel-title">By location</h3>
            <p className="panel-sub">
              Markers are placed only for regions publishers actually reported an article
              from, sized by real article count - no geographic data is invented.
            </p>
            <LocationMap data={data?.by_state ?? []} />
          </section>

          <Bars title="Top locations" data={data?.by_state ?? []} empty="No location data yet." />
        </>
      )}
    </div>
  );
}
