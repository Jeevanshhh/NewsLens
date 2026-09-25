import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { search as searchApi } from "../api/client";
import type { SearchHistoryItem } from "../api/types";

function dayLabel(iso: string | null): string {
  if (!iso) return "Earlier";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Earlier";
  const today = new Date();
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diffDays = Math.round((startOf(today) - startOf(d)) / 86400000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function Sidebar({ open, onClose }: { open: boolean; onClose?: () => void }) {
  const [items, setItems] = useState<SearchHistoryItem[]>([]);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    let active = true;
    searchApi
      .history(false)
      .then((res) => active && setItems(res.items))
      .catch(() => active && setItems([]));
    return () => {
      active = false;
    };
    // refetch whenever the route changes (e.g. after a new search completes)
  }, [location.pathname]);

  const groups = useMemo(() => {
    const map = new Map<string, SearchHistoryItem[]>();
    for (const it of items) {
      const key = dayLabel(it.created_at);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(it);
    }
    return Array.from(map.entries());
  }, [items]);

  const openSearch = (item: SearchHistoryItem) => {
    onClose?.();
    navigate(`/results/${item.id}`, {
      state: { query: item.query, filters: item.filters },
    });
  };

  return (
    <aside className={`sidebar${open ? " open" : ""}`}>
      <button className="btn new-search" onClick={() => { onClose?.(); navigate("/"); }}>
        <span style={{ fontSize: "1.05rem" }}>+</span> New Search
      </button>

      <div>
        <div className="side-section-title">Recent</div>
        {groups.length === 0 ? (
          <div className="side-empty">No searches yet.</div>
        ) : (
          groups.map(([label, list]) => (
            <div className="side-group" key={label}>
              <div className="side-section-title">{label}</div>
              {list.slice(0, 12).map((it) => (
                <button
                  key={it.id}
                  className={`side-item${location.pathname === `/results/${it.id}` ? " active" : ""}`}
                  onClick={() => openSearch(it)}
                  title={it.query}
                >
                  {it.is_saved ? "★ " : ""}
                  {it.name || it.query}
                </button>
              ))}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
