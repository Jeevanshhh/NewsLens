import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export default function ProfileMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const initial = (user?.name || user?.email || "?").trim().charAt(0).toUpperCase();

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="menu-wrap" ref={ref}>
      <button className="avatar" onClick={() => setOpen((o) => !o)} aria-label="Profile menu">
        {initial}
      </button>
      {open && (
        <div className="menu">
          <div style={{ padding: "0.5rem 0.6rem" }}>
            <div style={{ fontWeight: 600 }}>{user?.name}</div>
            <div className="muted" style={{ fontSize: "0.82rem" }}>{user?.email}</div>
          </div>
          <div className="menu-sep" />
          <button className="menu-item" onClick={() => go("/profile")}>👤 Profile</button>
          <button className="menu-item" onClick={() => go("/bookmarks")}>🔖 Bookmarks</button>
          <button className="menu-item" onClick={() => go("/saved")}>🔎 Saved searches</button>
          <button className="menu-item" onClick={() => go("/analytics")}>📊 Analytics</button>
          <button className="menu-item" onClick={() => go("/settings")}>⚙️ Settings</button>
          <div className="menu-sep" />
          <button className="menu-item" onClick={() => go("/about")}>ℹ️ About</button>
          <button className="menu-item" onClick={() => go("/privacy")}>🔒 Privacy</button>
          <button className="menu-item" onClick={() => go("/terms")}>📄 Terms</button>
          <button className="menu-item" onClick={() => go("/security")}>🛡️ Security</button>
          <div className="menu-sep" />
          <button className="menu-item" onClick={doLogout}>Log out</button>
        </div>
      )}
    </div>
  );
}
