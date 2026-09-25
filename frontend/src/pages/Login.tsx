import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { ApiError, auth } from "../api/client";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [forgot, setForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotMsg, setForgotMsg] = useState<string | null>(null);
  const [forgotErr, setForgotErr] = useState<string | null>(null);
  const [forgotBusy, setForgotBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  const submitForgot = async (e: FormEvent) => {
    e.preventDefault();
    setForgotMsg(null);
    setForgotErr(null);
    setForgotBusy(true);
    try {
      const res = await auth.requestPasswordReset(forgotEmail);
      setForgotMsg(res.detail);
    } catch (err) {
      setForgotErr(err instanceof ApiError ? err.detail : "Could not request reset");
    } finally {
      setForgotBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <h1 className="brand-lg">
          <span className="logo">◑</span> NewsLens
        </h1>
        <p className="muted">Sign in to your research workspace</p>

        {error && <div className="alert error">{error}</div>}

        <label>
          Email
          <input
            type="email"
            value={email}
            autoComplete="username"
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        <button className="btn primary block" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="muted center">
          No account? <Link to="/register">Create one</Link>
        </p>
        <p className="muted center">
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setForgot((v) => !v);
              setForgotMsg(null);
              setForgotErr(null);
            }}
          >
            Forgot password?
          </button>
        </p>
      </form>

      {forgot && (
        <form className="card auth-card" onSubmit={submitForgot}>
          <h2 className="panel-title">Reset your password</h2>
          <p className="muted">
            Enter your account email and we’ll send a link to choose a new password.
          </p>
          {forgotMsg && <div className="alert success">{forgotMsg}</div>}
          {forgotErr && <div className="alert error">{forgotErr}</div>}
          <label>
            Email
            <input
              type="email"
              value={forgotEmail}
              autoComplete="email"
              onChange={(e) => setForgotEmail(e.target.value)}
              required
            />
          </label>
          <button className="btn primary block" disabled={forgotBusy}>
            {forgotBusy ? "Sending…" : "Send reset link"}
          </button>
        </form>
      )}

      <div className="auth-legal">
        <Link to="/about">About</Link> · <Link to="/privacy">Privacy</Link> ·{" "}
        <Link to="/terms">Terms</Link> · <Link to="/security">Security</Link> ·{" "}
        <Link to="/copyright">Copyright</Link>
      </div>
    </div>
  );
}
