import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const destination = (location.state as { from?: string } | null)?.from ?? "/";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(destination, { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 401
          ? t("errors.invalidCredentials")
          : errorMessage(caught),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="card mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-bold">{t("auth.loginTitle")}</h1>
      {error && <div className="alert-error">{error}</div>}
      <div>
        <label className="label" htmlFor="email">{t("auth.email")}</label>
        <input id="email" className="input" type="email" required autoComplete="email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div>
        <label className="label" htmlFor="password">{t("auth.password")}</label>
        <input id="password" className="input" type="password" required autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      <button className="btn-primary w-full" disabled={busy}>
        {busy ? t("auth.loggingIn") : t("auth.loginSubmit")}
      </button>
      <p className="text-center text-sm text-slate-600">
        {t("auth.newHere")}{" "}
        <Link className="text-indigo-700 underline" to="/register">{t("auth.createAccountLink")}</Link>
      </p>
    </form>
  );
}