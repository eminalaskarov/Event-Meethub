import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function RegisterPage() {
  const { register } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accountType, setAccountType] = useState<"attendee" | "organizer">("attendee");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({ full_name: fullName, email, password, account_type: accountType });
      navigate(accountType === "organizer" ? "/manage" : "/", { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 409
          ? t("errors.emailTaken")
          : errorMessage(caught),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="card mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-bold">{t("auth.registerTitle")}</h1>
      {error && <div className="alert-error">{error}</div>}
      <div>
        <label className="label" htmlFor="name">{t("auth.fullName")}</label>
        <input id="name" className="input" required maxLength={150} autoComplete="name"
          value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </div>
      <div>
        <label className="label" htmlFor="email">{t("auth.email")}</label>
        <input id="email" className="input" type="email" required autoComplete="email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div>
        <label className="label" htmlFor="password">{t("auth.password")}</label>
        <input id="password" className="input" type="password" required minLength={8} maxLength={128}
          autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      <div>
        <label className="label" htmlFor="type">{t("auth.accountType")}</label>
        <select id="type" className="input" value={accountType}
          onChange={(e) => setAccountType(e.target.value as "attendee" | "organizer")}>
          <option value="attendee">{t("auth.attendee")}</option>
          <option value="organizer">{t("auth.organizer")}</option>
        </select>
      </div>
      <button className="btn-primary w-full" disabled={busy}>
        {busy ? t("auth.creatingAccount") : t("auth.registerSubmit")}
      </button>
      <p className="text-center text-sm text-slate-600">
        {t("auth.alreadyRegistered")}{" "}
        <Link className="text-indigo-700 underline" to="/login">{t("auth.loginLink")}</Link>
      </p>
    </form>
  );
}