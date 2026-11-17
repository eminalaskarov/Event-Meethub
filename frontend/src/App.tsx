import { useTranslation } from "react-i18next";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import type { Role } from "./api/types";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import EventDetailPage from "./pages/EventDetailPage";
import ExplorePage from "./pages/ExplorePage";
import LoginPage from "./pages/LoginPage";
import ManageDashboardPage from "./pages/ManageDashboardPage";
import ManageEventPage from "./pages/ManageEventPage";
import NewEventPage from "./pages/NewEventPage";
import NewVenuePage from "./pages/NewVenuePage";
import RegisterPage from "./pages/RegisterPage";
import ScannerPage from "./pages/ScannerPage";
import WalletPage from "./pages/WalletPage";

function RequireAuth({ roles }: { roles?: Role[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  const { t } = useTranslation();

  if (loading) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ExplorePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="events/:eventId" element={<EventDetailPage />} />

        <Route element={<RequireAuth />}>
          <Route path="wallet" element={<WalletPage />} />
          <Route path="scan" element={<ScannerPage />} />
        </Route>

        <Route element={<RequireAuth roles={["organizer", "admin"]} />}>
          <Route path="manage" element={<ManageDashboardPage />} />
          <Route path="manage/venues/new" element={<NewVenuePage />} />
          <Route path="manage/events/new" element={<NewEventPage />} />
          <Route path="manage/events/:eventId" element={<ManageEventPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}