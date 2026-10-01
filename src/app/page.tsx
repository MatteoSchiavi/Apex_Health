"use client";

/**
 * Apex Health — single-page app entry. State-based view switching driven by
 * the Zustand UI store. The `/` route is the only user-visible route per
 * sandbox constraints; all Apex "pages" are components rendered by this file.
 */

import { useEffect } from "react";
import { useApexUi } from "@/lib/apex";
import { I18nProvider, useT } from "@/lib/apex/i18nContext";
import { AppShell, Breadcrumb } from "@/components/apex/layout/AppShell";
import type { ViewKey } from "@/lib/apex/types";
import { WelcomeScreen } from "@/features/apex/welcome/WelcomeScreen";
import { LoginScreen } from "@/features/apex/auth/LoginScreen";
import { JoinScreen } from "@/features/apex/auth/JoinScreen";
import { OverviewPage } from "@/features/apex/overview/OverviewPage";
import { ActivitiesPage } from "@/features/apex/activities/ActivitiesPage";
import { ActivityDetailPage } from "@/features/apex/activities/ActivityDetailPage";
import { SleepPage } from "@/features/apex/sleep/SleepPage";
import { SleepNightPage } from "@/features/apex/sleep/SleepNightPage";
import { BiometricsPage } from "@/features/apex/biometrics/BiometricsPage";
import { MetricPage } from "@/features/apex/biometrics/MetricPage";
import { TrainingPage } from "@/features/apex/training/TrainingPage";
import { CoachPage } from "@/features/apex/coach/CoachPage";
import { SocialPage } from "@/features/apex/social/SocialPage";
import { SettingsPage } from "@/features/apex/settings/SettingsPage";
import { GearPage } from "@/features/apex/gear/GearPage";
import { LabsPage } from "@/features/apex/labs/LabsPage";
import { NutritionPage } from "@/features/apex/nutrition/NutritionPage";

export default function Home() {
  const ui = useApexUi();
  const { view, authed } = ui;

  // If somehow authed but view is a public one, send back to overview
  useEffect(() => {
    if (!authed && view !== "welcome" && view !== "login" && view !== "join") {
      ui.setView("welcome");
    }
  }, [authed, view, ui]);

  if (!authed || view === "welcome" || view === "login" || view === "join") {
    return (
      <I18nProvider locale={ui.locale} setLocale={ui.setLocale}>
        {view === "login" ? (
          <LoginScreen />
        ) : view === "join" ? (
          <JoinScreen />
        ) : (
          <WelcomeScreen />
        )}
      </I18nProvider>
    );
  }

  return (
    <I18nProvider locale={ui.locale} setLocale={ui.setLocale}>
      <AuthenticatedShell view={view} setView={ui.setView} />
    </I18nProvider>
  );
}

/** Authenticated shell — lives INSIDE the I18nProvider so useT() works. */
function AuthenticatedShell({ view, setView }: { view: ViewKey; setView: (v: ViewKey) => void }) {
  const t = useT();
  return (
    <AppShell
      current={view}
      breadcrumb={<Breadcrumb items={breadcrumbFor(view, t, setView)} />}
      onNav={setView}
    >
      {renderView(view)}
    </AppShell>
  );
}

function breadcrumbFor(view: string, t: (p: string) => string, setView: (v: ViewKey) => void) {
  const home = { label: t("nav.overview"), onClick: () => setView("overview") };
  switch (view) {
    case "overview":
      return [home];
    case "activities":
      return [home, { label: t("nav.activities"), onClick: () => setView("activities") }];
    case "activity-detail":
      return [
        home,
        { label: t("nav.activities"), onClick: () => setView("activities") },
        { label: t("activities.detail_title") },
      ];
    case "sleep":
      return [home, { label: t("nav.sleep"), onClick: () => setView("sleep") }];
    case "sleep-night":
      return [
        home,
        { label: t("nav.sleep"), onClick: () => setView("sleep") },
        { label: t("sleep.detail_title") },
      ];
    case "biometrics":
      return [home, { label: t("nav.biometrics"), onClick: () => setView("biometrics") }];
    case "metric":
      return [
        home,
        { label: t("nav.biometrics"), onClick: () => setView("biometrics") },
        { label: t("biometrics.view_trend") },
      ];
    case "training":
      return [home, { label: t("nav.training"), onClick: () => setView("training") }];
    case "coach":
      return [home, { label: t("nav.coach"), onClick: () => setView("coach") }];
    case "social":
      return [home, { label: t("nav.social"), onClick: () => setView("social") }];
    case "gear":
      return [home, { label: t("nav.gear"), onClick: () => setView("gear") }];
    case "labs":
      return [home, { label: t("nav.labs"), onClick: () => setView("labs") }];
    case "nutrition":
      return [home, { label: t("nav.nutrition"), onClick: () => setView("nutrition") }];
    case "settings":
      return [home, { label: t("nav.settings"), onClick: () => setView("settings") }];
    default:
      return [home];
  }
}

function renderView(view: string): React.ReactNode {
  switch (view) {
    case "overview":
      return <OverviewPage />;
    case "activities":
      return <ActivitiesPage />;
    case "activity-detail":
      return <ActivityDetailPage />;
    case "sleep":
      return <SleepPage />;
    case "sleep-night":
      return <SleepNightPage />;
    case "biometrics":
      return <BiometricsPage />;
    case "metric":
      return <MetricPage />;
    case "training":
      return <TrainingPage />;
    case "coach":
      return <CoachPage />;
    case "social":
      return <SocialPage />;
    case "gear":
      return <GearPage />;
    case "labs":
      return <LabsPage />;
    case "nutrition":
      return <NutritionPage />;
    case "settings":
      return <SettingsPage />;
    default:
      return <OverviewPage />;
  }
}
