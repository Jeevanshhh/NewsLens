import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { bookmarks, search as searchApi } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface Counts {
  bookmarks: number;
  saved: number;
}

export default function Profile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [counts, setCounts] = useState<Counts>({ bookmarks: 0, saved: 0 });

  useEffect(() => {
    let active = true;
    Promise.all([bookmarks.list(), searchApi.history(true)])
      .then(([b, s]) => active && setCounts({ bookmarks: b.count, saved: s.count }))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  const initial = (user?.name || user?.email || "?").trim().charAt(0).toUpperCase();

  const row = (
    path: string,
    ico: string,
    title: string,
    sub: string,
  ) => (
    <button className="card setting-row" onClick={() => navigate(path)}>
      <span className="setting-ico">{ico}</span>
      <span style={{ textAlign: "left" }}>
        <span className="st-title">{title}</span>
        <br />
        <span className="st-sub">{sub}</span>
      </span>
      <span className="chev">›</span>
    </button>
  );

  return (
    <div className="container">
      <div className="profile-head">
        <h1>Profile</h1>
        <p className="results-sub">Your account and personal library.</p>
      </div>

      <div className="card profile-card">
        <div className="avatar-lg">{initial}</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "1.15rem", fontWeight: 700 }}>{user?.name ?? "You"}</div>
          <div className="muted">{user?.email ?? "—"}</div>
        </div>
      </div>

      <div className="setting-list">
        {row("/bookmarks", "🔖", "Bookmarks", `${counts.bookmarks} saved article${counts.bookmarks === 1 ? "" : "s"}`)}
        {row("/saved", "🔎", "Saved Searches", `${counts.saved} saved search${counts.saved === 1 ? "" : "es"}`)}
        {row("/analytics", "📊", "Analytics", "Explore your collected corpus")}
        {row("/settings", "⚙️", "Settings", "Account and session")}

        <button className="card setting-row danger" onClick={doLogout}>
          <span className="setting-ico">↩</span>
          <span style={{ textAlign: "left" }}>
            <span className="st-title">Log out</span>
            <br />
            <span className="st-sub">End your session on this device</span>
          </span>
          <span className="chev">›</span>
        </button>
      </div>
    </div>
  );
}
