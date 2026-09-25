import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { useTheme, type ThemeMode } from "../theme/ThemeContext";
import { ApiError, auth, downloadMyData } from "../api/client";

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: string }[] = [
  { value: "light", label: "Light", icon: "☀" },
  { value: "dark", label: "Dark", icon: "☾" },
  { value: "system", label: "System", icon: "⚙" },
];

export default function SettingsPage() {
  const { user, login, logout } = useAuth();
  const { mode, setMode } = useTheme();
  const navigate = useNavigate();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [pwErr, setPwErr] = useState<string | null>(null);
  const [pwBusy, setPwBusy] = useState(false);

  const [exportErr, setExportErr] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const doLogout = () => {
    logout();
    navigate("/login");
  };

  const submitChange = async (e: FormEvent) => {
    e.preventDefault();
    setPwMsg(null);
    setPwErr(null);
    if (next.length < 8) {
      setPwErr("New password must be at least 8 characters.");
      return;
    }
    setPwBusy(true);
    try {
      await auth.changePassword(current, next);
      // Changing the password invalidates the previous token server-side, so we
      // immediately re-authenticate with the new one to stay signed in here.
      if (user) await login(user.email, next);
      setCurrent("");
      setNext("");
      setPwMsg("Password updated. Other sessions were signed out.");
    } catch (err) {
      setPwErr(err instanceof ApiError ? err.detail : "Could not change password");
    } finally {
      setPwBusy(false);
    }
  };

  const doExport = async () => {
    setExportErr(null);
    setExporting(true);
    try {
      await downloadMyData();
    } catch (err) {
      setExportErr(err instanceof ApiError ? err.detail : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const doDelete = async () => {
    setDelErr(null);
    setDeleting(true);
    try {
      await auth.deleteAccount();
      logout();
      navigate("/login");
    } catch (err) {
      setDelErr(err instanceof ApiError ? err.detail : "Could not delete account");
      setDeleting(false);
    }
  };

  return (
    <div className="container">
      <div className="profile-head">
        <h1>Settings</h1>
        <p className="results-sub">Your account and session.</p>
      </div>

      <section className="card panel">
        <h3 className="panel-title">Account</h3>
        <div className="keyinfo-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="keyinfo-item" style={{ padding: 0 }}>
            <div className="k">Name</div>
            <div className="v">{user?.name ?? "—"}</div>
          </div>
          <div className="keyinfo-item" style={{ padding: 0 }}>
            <div className="k">Email</div>
            <div className="v">{user?.email ?? "—"}</div>
          </div>
        </div>
      </section>

      <section className="card panel">
        <h3 className="panel-title">Password</h3>
        {pwMsg && <div className="alert success">{pwMsg}</div>}
        {pwErr && <div className="alert error">{pwErr}</div>}
        <form onSubmit={submitChange} className="stack">
          <label>
            Current password
            <input
              type="password"
              value={current}
              autoComplete="current-password"
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </label>
          <label>
            New password
            <input
              type="password"
              value={next}
              autoComplete="new-password"
              onChange={(e) => setNext(e.target.value)}
              minLength={8}
              required
            />
          </label>
          <small className="muted">At least 8 characters. You stay signed in here; other devices must sign in again.</small>
          <button className="btn primary" disabled={pwBusy}>
            {pwBusy ? "Updating…" : "Update password"}
          </button>
        </form>
      </section>

      <section className="card panel">
        <h3 className="panel-title">Your data</h3>
        {exportErr && <div className="alert error">{exportErr}</div>}
        <p className="muted" style={{ marginBottom: "0.9rem" }}>
          Download everything NewsLens holds about you — your profile, saved
          searches, bookmarks and report records — as a JSON file.
        </p>
        <button className="btn" onClick={doExport} disabled={exporting}>
          {exporting ? "Preparing…" : "Export my data"}
        </button>
      </section>

      <section className="card panel">
        <h3 className="panel-title">Appearance</h3>
        <p className="muted" style={{ marginBottom: "0.8rem" }}>
          Choose a theme. “System” follows your device’s light/dark setting.
        </p>
        <div className="tabs" role="group" aria-label="Theme">
          {THEME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`tab${mode === opt.value ? " active" : ""}`}
              aria-pressed={mode === opt.value}
              onClick={() => setMode(opt.value)}
            >
              <span aria-hidden style={{ marginRight: "0.35rem" }}>{opt.icon}</span>
              {opt.label}
            </button>
          ))}
        </div>
      </section>

      <section className="card panel">
        <h3 className="panel-title">Session</h3>
        <p className="muted" style={{ marginBottom: "0.9rem" }}>
          You’ll be returned to the sign-in screen. Your saved searches and bookmarks are kept.
        </p>
        <button className="btn danger" onClick={doLogout}>
          Log out
        </button>
      </section>

      <section className="card panel danger-zone">
        <h3 className="panel-title">Delete account</h3>
        {delErr && <div className="alert error">{delErr}</div>}
        <p className="muted" style={{ marginBottom: "0.9rem" }}>
          Permanently erase your account and all personal data (searches,
          bookmarks and reports). This cannot be undone.
        </p>
        {!confirmDelete ? (
          <button className="btn danger" onClick={() => setConfirmDelete(true)}>
            Delete my account…
          </button>
        ) : (
          <div className="danger-confirm">
            <span className="muted">Are you sure? This erases everything immediately.</span>
            <div className="danger-confirm-actions">
              <button className="btn" onClick={() => setConfirmDelete(false)} disabled={deleting}>
                Cancel
              </button>
              <button className="btn danger" onClick={doDelete} disabled={deleting}>
                {deleting ? "Deleting…" : "Yes, delete forever"}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
