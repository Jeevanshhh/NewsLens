import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { bookmarks, search as searchApi } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface Counts {
  bookmarks: number;
  saved: number;
}

export default function AccountNav({ open, onClose }: { open: boolean; onClose?: () => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [counts, setCounts] = useState<Counts>({ bookmarks: 0, saved: 0 });

  useEffect(() => {
    let active = true;
    Promise.all([bookmarks.list(), searchApi.history(true)])
      .then(([b, s]) => active && setCounts({ bookmarks: b.count, saved: s.count }))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [location.pathname]);

  const go = (path: string) => {
    onClose?.();
    navigate(path);
  };

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  const initial = (user?.name || user?.email || "?").trim().charAt(0).toUpperCase();
  const isActive = (p: string) => location.pathname.startsWith(p);

  const navItem = (
    path: string,
    ico: string,
    label: string,
    badge?: number,
  ) => (
    <button
      className={`nav-item${isActive(path) ? " active" : ""}`}
      onClick={() => go(path)}
    >
      <span className="ico">{ico}</span>
      {label}
      {badge ? <span className="nav-badge">{badge}</span> : null}
    </button>
  );

  return (
    <aside className={`account-nav${open ? " open" : ""}`}>
      <div className="account-id">
        <div className="avatar">{initial}</div>
        <div style={{ minWidth: 0 }}>
          <div className="name">{user?.name}</div>
          <div className="email">{user?.email}</div>
        </div>
      </div>

      {navItem("/profile", "👤", "Profile")}
      {navItem("/bookmarks", "🔖", "Bookmarks", counts.bookmarks)}
      {navItem("/saved", "🔎", "Saved Searches", counts.saved)}
      {navItem("/analytics", "📊", "Analytics")}
      {navItem("/settings", "⚙️", "Settings")}

      <div style={{ flex: 1 }} />
      <button className="nav-item danger" onClick={doLogout}>
        <span className="ico">↩</span> Logout
      </button>
    </aside>
  );
}
