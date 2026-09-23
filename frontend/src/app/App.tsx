/**
 * App root: providers (Query, Router) + session boot + routes.
 *
 * Session model: the backend answers GET /me with the account (session
 * cookie). While unresolved we render nothing (no login flash); 401 sends
 * the user to /login. Invite onboarding lives at /join.
 */

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, type ReactNode } from "react";
import { api, type Me } from "./api";
import { useUi } from "./stores/ui";
import { AppShell } from "../components/layout/AppShell";
import Login from "../features/auth/Login";
import Join from "../features/auth/Join";
import OverviewPage from "../features/overview/OverviewPage";
import ActivitiesPage from "../features/activities/ActivitiesPage";
import ActivityDetailPage from "../features/activities/ActivityDetailPage";
import SleepListPage from "../features/sleep/SleepListPage";
import SleepNightPage from "../features/sleep/SleepNightPage";
import BiometricsHubPage from "../features/biometrics/BiometricsHubPage";
import MetricPage from "../features/biometrics/MetricPage";
import TrainingPage from "../features/training/TrainingPage";
import CoachPage from "../features/coach/CoachPage";
import SocialPage from "../features/social/SocialPage";
import SettingsPage from "../features/settings/SettingsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false },
  },
});

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
  const me = useUi((s) => s.me);
  const { isLoading, isError } = useSession();
  if (isLoading) return <div className="min-h-dvh bg-canvas" />;
  if (isError)
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  // The /me effect lands one commit after the query resolves; pages read
  // the store for account prefs, so hold the shell until it is populated.
  if (!me) return <div className="min-h-dvh bg-canvas" />;
  return <AppShell>{children}</AppShell>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/join" element={<Join />} />
          <Route path="/app" element={<Protected><OverviewPage /></Protected>} />
          <Route path="/app/activities" element={<Protected><ActivitiesPage /></Protected>} />
          <Route path="/app/activities/:id" element={<Protected><ActivityDetailPage /></Protected>} />
          <Route path="/app/sleep" element={<Protected><SleepListPage /></Protected>} />
          <Route path="/app/sleep/:date" element={<Protected><SleepNightPage /></Protected>} />
          <Route path="/app/biometrics" element={<Protected><BiometricsHubPage /></Protected>} />
          <Route path="/app/biometrics/:key" element={<Protected><MetricPage /></Protected>} />
          <Route path="/app/training" element={<Protected><TrainingPage /></Protected>} />
          <Route path="/app/coach" element={<Protected><CoachPage /></Protected>} />
          <Route path="/app/social" element={<Protected><SocialPage /></Protected>} />
          <Route path="/app/settings" element={<Protected><SettingsPage /></Protected>} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
