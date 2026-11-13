import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import type { Language } from "../i18n";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${
    isActive ? "bg-indigo-100 text-indigo-800" : "text-slate-600 hover:bg-slate-100"
  }`;

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const canManage = user?.role === "organizer" || user?.role === "admin";

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
          <Link to="/" className="mr-auto text-lg font-bold text-indigo-700">
            {t("navbar.brand")}
          </Link>
          <nav className="flex flex-wrap items-center gap-1">
            <select
              aria-label={t("navbar.language")}
              className="mr-1 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={i18n.resolvedLanguage ?? "en"}
              onChange={(event) => void i18n.changeLanguage(event.target.value as Language)}
            >
              <option value="en">EN</option>
              <option value="az">AZ</option>
            </select>

            <NavLink to="/" end className={navClass}>
              {t("navbar.explore")}
            </NavLink>
            {user && (
              <NavLink to="/wallet" className={navClass}>
                {t("navbar.wallet")}
              </NavLink>
            )}
            {user && (
              <NavLink to="/scan" className={navClass}>
                {t("navbar.scan")}
              </NavLink>
            )}
            {canManage && (
              <NavLink to="/manage" className={navClass}>
                {t("navbar.manage")}
              </NavLink>
            )}

            {user ? (
              <button
                type="button"
                className="btn-secondary ml-2 !py-1.5"
                onClick={() => {
                  logout();
                  navigate("/");
                }}
              >
                {t("navbar.logout")}
              </button>
            ) : (
              <>
                <NavLink to="/login" className={navClass}>
                  {t("navbar.login")}
                </NavLink>
                <Link to="/register" className="btn-primary !py-1.5">
                  {t("navbar.signup")}
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}