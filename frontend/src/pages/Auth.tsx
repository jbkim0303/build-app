import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorBox } from "../components/ui";

function useRedirectBack() {
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  return () => navigate(from && !from.startsWith("/login") && !from.startsWith("/register") ? from : "/", { replace: true });
}

export function Login() {
  const { login } = useAuth();
  const done = useRedirectBack();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try { await login(email, password); done(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };

  return (
    <form className="card narrow form" onSubmit={submit}>
      <h1>Log in</h1>
      <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      {error && <ErrorBox message={error} />}
      <button className="btn btn-primary" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
      <p className="muted">No account? <Link to="/register" state={location.state}>Sign up</Link></p>
    </form>
  );
}

export function Register() {
  const { register } = useAuth();
  const done = useRedirectBack();
  const location = useLocation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try { await register(email, name, password); done(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };

  return (
    <form className="card narrow form" onSubmit={submit}>
      <h1>Create account</h1>
      <label>Name<input autoComplete="name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label>Password<input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} />
        <small className="muted">At least 8 characters</small></label>
      {error && <ErrorBox message={error} />}
      <button className="btn btn-primary" disabled={busy}>{busy ? "Creating…" : "Sign up"}</button>
      <p className="muted">Already registered? <Link to="/login" state={location.state}>Log in</Link></p>
    </form>
  );
}
