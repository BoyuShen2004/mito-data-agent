import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { login, user, isManager } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) {
    navigate(isManager ? "/manager" : "/annotator", { replace: true });
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(username, password);
      navigate(u.role === "manager" ? "/manager" : "/annotator", {
        replace: true,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <aside className="login-brand">
        <div className="brand-mark">🧬 Mito Data Agent</div>
        <div className="brand-hero">
          <h1>
            Mitochondria annotation,
            <br />
            organized end to end.
          </h1>
          <p>
            Register image volumes, split them into frame-based tasks, assign
            annotators, and review submissions — with progress and payment
            tracked automatically.
          </p>
        </div>
        <ul className="brand-features">
          <li>
            <span className="tick">✓</span> Frame-based task splitting &amp;
            rule-based assignment
          </li>
          <li>
            <span className="tick">✓</span> Submission review with built-in QC
          </li>
          <li>
            <span className="tick">✓</span> Live progress, workload &amp;
            payment summaries
          </li>
        </ul>
      </aside>

      <main className="login-form-panel">
        <div className="login-card">
          <div className="login-mobile-brand">🧬 Mito Data Agent</div>
          <h2>Welcome back</h2>
          <p className="subtitle">Sign in to your workspace</p>

          {error && <div className="error">{error}</div>}

          <form onSubmit={onSubmit}>
            <label className="field">
              <span>Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="you@lab"
                autoFocus
              />
            </label>
            <label className="field">
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </label>
            <button type="submit" className="btn-block" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="login-hint">
            Demo logins (after seeding): manager <code>manager</code> /{" "}
            <code>demo12345</code> · annotator <code>alice</code> /{" "}
            <code>demo12345</code>
          </div>
        </div>
      </main>
    </div>
  );
}
