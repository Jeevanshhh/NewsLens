import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, auth } from "../api/client";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("This reset link is missing its token. Request a new one.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await auth.confirmPasswordReset(token, password);
      navigate("/login", { replace: true, state: { resetDone: true } });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reset password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <h1 className="brand-lg">
          <span className="logo">◑</span> NewsLens
        </h1>
        <p className="muted">Choose a new password</p>

        {!token && (
          <div className="alert error">
            This reset link is missing its token.{" "}
            <Link to="/login">Return to sign in</Link> to request a new one.
          </div>
        )}
        {error && <div className="alert error">{error}</div>}

        <label>
          New password
          <input
            type="password"
            value={password}
            autoComplete="new-password"
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>
        <label>
          Confirm password
          <input
            type="password"
            value={confirm}
            autoComplete="new-password"
            onChange={(e) => setConfirm(e.target.value)}
            minLength={8}
            required
          />
        </label>
        <small className="muted">At least 8 characters.</small>

        <button className="btn primary block" disabled={busy || !token}>
          {busy ? "Resetting…" : "Set new password"}
        </button>

        <p className="muted center">
          Remembered it? <Link to="/login">Back to sign in</Link>
        </p>
      </form>
    </div>
  );
}
