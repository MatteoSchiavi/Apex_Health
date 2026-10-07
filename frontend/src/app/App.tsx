/**
 * App root: providers (Query, Router) + session boot + routes.
 *
 * Session model: the backend answers GET /me with the account (session
 * cookie). While unresolved we render nothing (no login flash); 401 sends
 * the user to /login. Invite onboarding lives at /join.
 */

import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { api, ApiError, type Me } from "./api";
import { clearAllAccountStorage, useUi } from "./stores/ui";
import { PageBoundary } from "../components/PageBoundary";
import { AppShell } from "../components/layout/AppShell";
import Login from "../features/auth/Login";
import Join from "../features/auth/Join";
import WelcomePage from "../features/landing/WelcomePage";
const OverviewPage = lazy(() => import("../features/overview/OverviewPage"));
const ActivitiesPage = lazy(
  () => import("../features/activities/ActivitiesPage"),
);
const ActivityDetailPage = lazy(
  () => import("../features/activities/ActivityDetailPage"),
);
const SleepListPage = lazy(() => import("../features/sleep/SleepListPage"));
const SleepNightPage = lazy(() => import("../features/sleep/SleepNightPage"));
const BiometricsHubPage = lazy(
  () => import("../features/biometrics/BiometricsHubPage"),
);
const MetricPage = lazy(() => import("../features/biometrics/MetricPage"));
const TrainingPage = lazy(() => import("../features/training/TrainingPage"));
const CoachPage = lazy(() => import("../features/coach/CoachPage"));
const SocialPage = lazy(() => import("../features/social/SocialPage"));
const LabPage = lazy(() => import("../features/lab/LabPage"));
const CalendarPage = lazy(() => import("../features/lab/CalendarPage"));
const GearPage = lazy(() => import("../features/lab/GearPage"));
const SettingsPage = lazy(() => import("../features/settings/SettingsPage"));
const LegalPage = lazy(() => import("../features/legal/LegalPage"));
const AdminPage = lazy(() => import("../features/admin/AdminPage"));

import { queryClient } from "./query";
import { Button, ErrorNote, Loading } from "../components/kit";
import { useTranslation } from "react-i18next";

function useSession() {
  const setMe = useUi((s) => s.setMe);
  const query = useQuery<Me, Error>({
    queryKey: ["me"],
    queryFn: () => api.get<Me>("/me"),
    staleTime: 5 * 60_000,
  });
  useEffect(() => {
    if (query.data) setMe(query.data);
  }, [query.data, setMe]);
  return query;
}

function Protected({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { t } = useTranslation();
  const me = useUi((s) => s.me);
  const { isLoading, isError, error, refetch } = useSession();
  useEffect(() => {
    if (isError && error instanceof ApiError && error.status === 401) {
      clearAllAccountStorage();
      if (me) useUi.getState().setMe(null);
    }
  }, [isError, error, me]);
  if (isLoading) return <Loading />;
  if (isError && error instanceof ApiError && error.status === 401)
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (isError)
    return (
      <div className="mx-auto max-w-lg p-10">
        <ErrorNote />
        <Button variant="ghost" onClick={() => refetch()} className="mt-4">
          {t("common.retry")}
        </Button>
      </div>
    );
  // The /me effect lands one commit after the query resolves; pages read
  // the store for account prefs, so hold the shell until it is populated.
  if (!me) return <div className="min-h-dvh bg-canvas" />;
  return (
    <AppShell>
      <PageBoundary key={location.pathname}>
        <Suspense fallback={<Loading />}>{children}</Suspense>
      </PageBoundary>
    </AppShell>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="/login" element={<Login />} />
          <Route path="/join" element={<Join />} />
          <Route path="/legal/privacy" element={<Suspense fallback={<Loading />}><LegalPage /></Suspense>} />
          <Route path="/legal/terms" element={<Suspense fallback={<Loading />}><LegalPage /></Suspense>} />
          <Route path="/legal/cookies" element={<Suspense fallback={<Loading />}><LegalPage /></Suspense>} />
          <Route path="/privacy" element={<Navigate to="/legal/privacy" replace />} />
          <Route path="/terms" element={<Navigate to="/legal/terms" replace />} />
          <Route path="/cookies" element={<Navigate to="/legal/cookies" replace />} />
          <Route
            path="/app"
            element={
              <Protected>
                <OverviewPage />
              </Protected>
            }
          />
          <Route
            path="/app/activities"
            element={
              <Protected>
                <ActivitiesPage />
              </Protected>
            }
          />
          <Route path="/admin" element={<Protected><OwnerAdmin /></Protected>} />
          <Route
            path="/app/activities/:id"
            element={
              <Protected>
                <ActivityDetailPage />
              </Protected>
            }
          />
          <Route
            path="/app/sleep"
            element={
              <Protected>
                <SleepListPage />
              </Protected>
            }
          />
          <Route
            path="/app/sleep/:date"
            element={
              <Protected>
                <SleepNightPage />
              </Protected>
            }
          />
          <Route
            path="/app/biometrics"
            element={
              <Protected>
                <BiometricsHubPage />
              </Protected>
            }
          />
          <Route
            path="/app/biometrics/:key"
            element={
              <Protected>
                <MetricPage />
              </Protected>
            }
          />
          <Route
            path="/app/training"
            element={
              <Protected>
                <TrainingPage />
              </Protected>
            }
          />
          <Route
            path="/app/coach"
            element={
              <Protected>
                <CoachPage />
              </Protected>
            }
          />
          <Route
            path="/app/social"
            element={
              <Protected>
                <SocialPage />
              </Protected>
            }
          />
          <Route
            path="/app/settings"
            element={
              <Protected>
                <SettingsPage />
              </Protected>
            }
          />
          <Route
            path="/app/lab"
            element={
              <Protected>
                <LabPage />
              </Protected>
            }
          />
          <Route
            path="/app/data-health"
            element={
              <Protected>
                <Navigate to="/app/settings?tab=data-health" replace />
              </Protected>
            }
          />
          <Route
            path="/app/calendar"
            element={
              <Protected>
                <CalendarPage />
              </Protected>
            }
          />
          <Route
            path="/app/notifications"
            element={
              <Protected>
                <Navigate to="/app/settings?tab=notifications" replace />
              </Protected>
            }
          />
          <Route
            path="/app/gear"
            element={
              <Protected>
                <GearPage />
              </Protected>
            }
          />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function OwnerAdmin() {
  const me = useUi((s) => s.me);
  return me?.role === "owner" ? <AdminPage /> : <Navigate to="/app" replace />;
}
