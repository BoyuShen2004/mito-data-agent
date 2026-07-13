import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { homePathForRole } from "../routes/AppRoutes";
import type { LoginPortal } from "../api/auth";

// Standard accounts created by `python manage.py seed_dev`. Shown on the login
// page in development only (Vite `import.meta.env.DEV`) as a convenience — this
// block is stripped from production builds.
const DEV_PASSWORD = "demo12345";
const DEV_ACCOUNTS: { username: string; role: string; portal: LoginPortal }[] = [
  { username: "manager", role: "Manager", portal: "annotator" },
  { username: "alice", role: "Annotator", portal: "annotator" },
  { username: "bob", role: "Annotator", portal: "annotator" },
  { username: "carol", role: "Annotator", portal: "annotator" },
  { username: "dave", role: "Annotator", portal: "annotator" },
];

export default function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [portal, setPortal] = useState<LoginPortal>("requester");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fillDevAccount = (account: (typeof DEV_ACCOUNTS)[number]) => {
    setPortal(account.portal);
    setUsername(account.username);
    setPassword(DEV_PASSWORD);
    setError(null);
  };

  if (user) {
    navigate(homePathForRole(user.role), { replace: true });
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(username, password, portal);
      navigate(homePathForRole(u.role), { replace: true });
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
            Requesters register image volumes from HPC storage; managers create
            projects and assign annotators; annotators complete and submit
            frame-based tasks — with progress tracked throughout.
          </p>
        </div>
        <ul className="brand-features">
          <li>
            <span className="tick">✓</span> Register HPC datasets, volumes &amp;
            chunks
          </li>
          <li>
            <span className="tick">✓</span> Manual task assignment &amp; review
            with QC
          </li>
          <li>
            <span className="tick">✓</span> Live project progress &amp; metadata
          </li>
        </ul>
      </aside>

      <main className="login-form-panel">
        <div className="login-card">
          <div className="login-mobile-brand">🧬 Mito Data Agent</div>
          <h2>Welcome back</h2>
          <p className="subtitle">Sign in to your workspace</p>

          <div className="tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={portal === "requester"}
              className={`tab ${portal === "requester" ? "tab-active" : ""}`}
              onClick={() => setPortal("requester")}
            >
              Requester Login
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={portal === "annotator"}
              className={`tab ${portal === "annotator" ? "tab-active" : ""}`}
              onClick={() => setPortal("annotator")}
            >
              Annotator Login
            </button>
          </div>

          {portal === "annotator" && (
            <p className="subtitle">
              Managers sign in here using their manager account.
            </p>
          )}

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
            Need an account? <Link to="/register">Create one</Link> as an
            annotator or a requester.
          </div>

          {import.meta.env.DEV && (
            <div className="dev-accounts">
              <div className="dev-accounts-title">
                Dev accounts — click to fill (password <code>{DEV_PASSWORD}</code>)
              </div>
              <div className="dev-accounts-list">
                {DEV_ACCOUNTS.map((a) => (
                  <button
                    type="button"
                    key={a.username}
                    className="dev-chip"
                    onClick={() => fillDevAccount(a)}
                  >
                    {a.username}
                    <span className="dev-chip-role">{a.role}</span>
                  </button>
                ))}
              </div>
              <div className="dev-accounts-note">
                All use the Annotator tab. Run{" "}
                <code>python manage.py seed_dev</code> if they don't exist yet.
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
