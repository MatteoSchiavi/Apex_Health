"use client";

/**
 * Apex Health — Overview / Home dashboard (STRICT redesign per Part 1 spec).
 *
 * Row-by-row shape (the user explicitly asked the previous redesign to
 * follow this STRICTLY — do not invent a different arrangement):
 *
 *   Row 0 — Needs attention           (col-12, conditional, hidden when empty)
 *   Row 1 — Readiness / Recovery / Strain  (3× col-12 md:col-span-4)
 *   Row 1b — Today's plan             (Planned 5 / Event 4 / Weather 3; conditional)
 *   Row 2 — Load & vitals             (ACWR col-12 xl:col-span-8 + Biomarkers col-12 xl:col-span-4)
 *   Row 3 — Last night's sleep        (col-12, conditional on sleep != null)
 *   Row 4 — Logs & status             (Activities 5 / Gear 4 / Integrations 3)
 *
 * Critical design rules (from the user):
 *   1. DATA color reflects STATE, not the accent. Use scoreTone / acwrTone /
 *      rangeTone / hrvDevTone + toneFor for every ScoreBar / RangeBar / Badge
 *      / StatPod that displays data. Reserve `tone="primary"` for non-data
 *      UI only (active nav, brand, buttons).
 *   2. No fake / computed-from-nothing numbers. Floor/Cap row dropped. The
 *      ACWR "no overreach" static line is replaced with a tone-reactive
 *      status line. The biomarker "all normal" badge is computed from
 *      actual in-range checks.
 *   3. Strain is NEUTRAL — high strain isn't bad. Strain's ScoreBar uses
 *      a `muted` tone, never positive/alert.
 *
 * Data sources:
 *   /api/dashboard        → scores + sleep + biomarkers + activities + alerts + integration_health + gear_due
 *   /api/metrics/load?days=28 → 28-day acute (bar) / chronic (line) series for the ACWR card
 *   /api/gym/plan?date=<today> → today's GymDayPlan for Row 1b Planned session
 *   /api/events           → upcoming events for Row 1b Next event
 *   /api/gear             → gear list (filtered to ≥80% service interval here) for Row 4
 *   /api/integrations     → integration health for Row 4
 *
 * If /api/dashboard fails, the page falls back to the mock `overview` from
 * `@/lib/apex/data` so the layout still renders for development.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronRight,
  Download,
  Calendar,
  Dumbbell,
  AlertTriangle,
  Wrench,
  CloudOff,
} from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { me, overview as mockOverview } from "@/lib/apex/data";
import { localToday, addDays, dayDiff } from "@/lib/apex/localTime";
import {
  Card,
  CardHeader,
  PageHeader,
  BigStat,
  StatPod,
  DeltaChip,
  Badge,
  ScoreBar,
  RangeBar,
  Eyebrow,
  Empty,
  Loading,
  Hairline,
  ApexButton,
  SportIcon,
  InfoButton,
  MetricInfoContent,
  scoreTone,
  acwrTone,
  rangeTone,
  toneFor,
  type DataTone,
} from "@/components/apex/kit";
import { METRIC_EXPLANATIONS } from "@/lib/apex/metricInfo";
import {
  fmtNum,
  fmtHours,
  fmtDuration,
  fmtClock,
  fmtDistance,
  fmtDate,
  friendlyDiscipline,
} from "@/lib/apex/format";
import type { ActivityCard, Gear } from "@/lib/apex/types";

/* ----------------------------------------------------------- response shapes */

interface GearDueItem {
  id: number;
  name: string;
  gear_type: string;
  brand: string | null;
  usage_pct: number;
  hours_since_service: number;
  service_interval_hours: number | null;
  km_since_service: number;
  service_interval_km: number | null;
}

interface IntegrationHealthItem {
  provider: string;
  status: string;
  last_synced_at: string | null;
  is_main: boolean;
  consecutive_failures: number;
}

interface OverviewData {
  date: string;
  anchor_is_today: boolean;
  data_completeness?: "full" | "partial" | "missing";
  readiness: { value: number | null; delta_7d: number | null };
  recovery: { value: number | null; delta_7d: number | null };
  strain: { value: number | null; delta_7d: number | null };
  sleep_score: { value: number | null; delta_7d: number | null };
  sleep_hours: number | null;
  hrv_ms: number | null;
  hrv_baseline_ms: number | null;
  hrv_norm_30d: number | null;
  hrv_deviation_pct: number | null;
  resting_hr: number | null;
  resting_hr_delta_7d: number | null;
  spo2_avg: number | null;
  spo2_delta_7d: number | null;
  respiration_avg: number | null;
  weight_kg: number | null;
  vo2max: number | null;
  steps: number | null;
  acute_load: number | null;
  chronic_load: number | null;
  acwr: number | null;
  training_load_7d: number | null;
  activities: ActivityCard[];
  sleep: {
    start_time: string;
    end_time: string;
    total_sleep_s: number | null;
    sleep_score: number | null;
    stages: {
      deep_s: number | null;
      light_s: number | null;
      rem_s: number | null;
      awake_s: number | null;
    };
    respiration_avg: number | null;
    spo2_avg: number | null;
    restlessness: number | null;
  } | null;
  integration_status: { provider: string; status: string }[];
  integration_health: IntegrationHealthItem[];
  gear_due: GearDueItem[];
  alerts: { type: string; severity: "info" | "warning" | "alert"; message: string }[];
}

interface GymPlanLite {
  id: number;
  date: string;
  title: string;
  status: string;
  adjustmentNote: string | null;
  exercises: unknown[];
}

interface ApexEvent {
  id: number;
  title: string;
  kind: string;
  date: string;
  endDate?: string | null;
  priority: string;
  taperDays: number | null;
  note?: string | null;
}

interface DayLoad {
  date: string;
  load: number;
  acute: number | null;
  chronic: number | null;
  acwr: number | null;
}

/* ----------------------------------------------------------- reference ranges */
// Per spec: RHR 50-70, SpO₂ 95-100, respiration 12-20. Weight has no fixed
// range — skip from the in-range count (treated as neutral/muted).
const RHR_RANGE = { low: 50, high: 70 };
const SPO2_RANGE = { low: 95, high: 100 };
const RESP_RANGE = { low: 12, high: 20 };

// ACWR display band — for the bar's optimal-band highlight.
const ACWR_VIEW = { low: 0.5, high: 2.0 };
const ACWR_OPT = { low: 0.8, high: 1.3 };

const TODAY_LOCAL = localToday(me.timezone);

/* ----------------------------------------------------------- severity tone */
function severityTone(sev: "info" | "warning" | "alert"): "neutral" | "warning" | "alert" {
  if (sev === "alert") return "alert";
  if (sev === "warning") return "warning";
  return "neutral";
}

function acwrStatusLine(t: DataTone, acwr: number | null): string {
  if (acwr === null || !Number.isFinite(acwr)) return "No load data yet — connect Garmin to start the load pipeline.";
  if (t === "positive") return "Within the 0.8–1.3 optimal band";
  if (t === "alert") return "Above 1.5 — high injury-risk zone";
  if (acwr < 0.8) return "Undertrained — load below the optimal band";
  return "Elevated — approaching overreach";
}

/** Map a DataTone to the Badge tone union — Badge has no `muted`, so map
 *  muted → neutral. Use this instead of `toneFor` for Badge components. */
function badgeTone(t: DataTone): "neutral" | "positive" | "warning" | "alert" {
  if (t === "positive") return "positive";
  if (t === "warning") return "warning";
  if (t === "alert") return "alert";
  return "neutral";
}

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "never";
  const diffMs = Date.now() - then;
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  return `${months}mo ago`;
}

/* ============================================================== OverviewPage */
export function OverviewPage() {
  const t = useT();
  const ui = useApexUi();

  // ----- data state -------------------------------------------------------
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [plan, setPlan] = useState<GymPlanLite | null>(null);
  const [events, setEvents] = useState<ApexEvent[]>([]);
  const [load, setLoad] = useState<DayLoad[] | null>(null);
  const [gearAll, setGearAll] = useState<Gear[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationHealthItem[]>([]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/dashboard", { cache: "no-store" });
      const json = await res.json();
      if (!json.ok) throw new Error(json.error || "Failed to load dashboard");
      setData(json.overview as OverviewData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
      // graceful fallback to mock so the layout still renders
      setData(mockOverview as unknown as OverviewData);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPlan = useCallback(async () => {
    try {
      const res = await fetch(`/api/gym/plan?date=${TODAY_LOCAL}`, { cache: "no-store" });
      const json = await res.json();
      if (json.ok && json.plan) {
        setPlan({
          id: json.plan.id,
          date: json.plan.date,
          title: json.plan.title,
          status: json.plan.status,
          adjustmentNote: json.plan.adjustmentNote,
          exercises: json.plan.exercises ?? [],
        });
      }
    } catch {
      /* no-op */
    }
  }, []);

  const loadEvents = useCallback(async () => {
    try {
      const res = await fetch("/api/events", { cache: "no-store" });
      const json = await res.json();
      if (json.ok) setEvents(json.events);
    } catch {
      /* no-op */
    }
  }, []);

  const loadMetricsLoad = useCallback(async () => {
    try {
      const res = await fetch("/api/metrics/load?days=28", { cache: "no-store" });
      const json = await res.json();
      if (json.ok) setLoad(json.series);
    } catch {
      /* no-op */
    }
  }, []);

  const loadGear = useCallback(async () => {
    try {
      const res = await fetch("/api/gear", { cache: "no-store" });
      const json = await res.json();
      if (json.ok) setGearAll(json.gear);
    } catch {
      /* no-op */
    }
  }, []);

  const loadIntegrations = useCallback(async () => {
    try {
      const res = await fetch("/api/integrations", { cache: "no-store" });
      const json = await res.json();
      if (json.ok) setIntegrations(json.integrations);
    } catch {
      /* no-op */
    }
  }, []);

  useEffect(() => {
    loadAll();
    loadPlan();
    loadEvents();
    loadMetricsLoad();
    loadGear();
    loadIntegrations();
  }, [loadAll, loadPlan, loadEvents, loadMetricsLoad, loadGear, loadIntegrations]);

  // ----- derived (all hooks must run before any early return) -------------
  const todayIso = data?.date ?? TODAY_LOCAL;

  // Row 1b — events within the next 14 days, sorted ascending.
  const nextEvents = useMemo(() => {
    return events
      .filter((e) => {
        const d = dayDiff(todayIso, e.date);
        return d >= 0 && d <= 14;
      })
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [events, todayIso]);

  // Row 4 — Gear due for service (≥80% service interval). The full list
  // belongs on the Gear page; this filters to the near/at-threshold items.
  const gearDueList = useMemo(() => {
    return gearAll
      .map((g) => {
        const hoursPct =
          g.service_interval_hours && g.service_interval_hours > 0
            ? (g.hours_since_service / g.service_interval_hours) * 100
            : 0;
        const kmPct =
          g.service_interval_km && g.service_interval_km > 0
            ? (g.km_since_service / g.service_interval_km) * 100
            : 0;
        return { gear: g, usagePct: Math.max(hoursPct, kmPct, g.usage_pct) };
      })
      .filter((x) => x.usagePct >= 80)
      .sort((a, b) => b.usagePct - a.usagePct)
      .slice(0, 5);
  }, [gearAll]);

  // ----- early return for loading state (AFTER all hooks have been called) -
  if (loading || !data) {
    return (
      <div className="mx-auto max-w-[1240px] px-5 py-6 lg:px-8 lg:py-8">
        <PageHeader title={t("overview.title")} subtitle={t("welcome.preview_overview")} />
        <div className="mt-6">
          <Loading label="Loading overview…" />
        </div>
      </div>
    );
  }

  // ----- non-null `data` derivations -------------------------------------
  // Tone computations — STATE, not accent. Strain is NEUTRAL — never
  // positive/alert — handled inline via `tone="muted"` on its BigStat/ScoreBar.
  const readinessTone = scoreTone(data.readiness.value);
  const recoveryTone = scoreTone(data.recovery.value);
  const sleepTone = scoreTone(data.sleep_score.value ?? data.sleep?.sleep_score ?? null);

  const acwrValue = data.acwr;
  const acwrT = acwrTone(acwrValue);
  const acwrStatTone = toneFor(acwrT);

  // HRV deviation (computed by /api/dashboard when hrv + 30d baseline exist).
  // Available for a future "HRV vs baseline" tile on the biomarker strip;
  // currently not surfaced in the spec's Row 2.
  // Tone would be `hrvDevTone(data.hrv_deviation_pct, 8)` (imported from kit).

  // Biomarker in-range check — compute the summary badge from real values.
  // NULL values are "no data", not "in range" — so we count only the measured
  // ones. The badge reads:
  //   - "no data" (neutral) when none of RHR/SpO₂/Resp are present
  //   - "X outside range" (alert) when any measured value is out-of-band
  //   - "Y borderline" (warning) when any measured value is within 10% of a boundary
  //   - "all normal" (positive) when every measured value sits cleanly in range
  // Weight has no fixed range and is excluded from the count.
  const rhrIn = rangeTone(data.resting_hr, RHR_RANGE.low, RHR_RANGE.high);
  const spo2In = rangeTone(data.spo2_avg, SPO2_RANGE.low, SPO2_RANGE.high);
  const respIn = rangeTone(data.respiration_avg, RESP_RANGE.low, RESP_RANGE.high);
  const measuredStates: DataTone[] = [
    data.resting_hr !== null ? rhrIn : null,
    data.spo2_avg !== null ? spo2In : null,
    data.respiration_avg !== null ? respIn : null,
  ].filter((x): x is DataTone => x !== null);
  const biomarkerOutOfRange = measuredStates.filter((s) => s === "alert").length;
  const biomarkerBorderline = measuredStates.filter((s) => s === "warning").length;
  let biomarkerSummaryTone: DataTone;
  let biomarkerSummaryLabel: string;
  if (measuredStates.length === 0) {
    biomarkerSummaryTone = "muted";
    biomarkerSummaryLabel = "no data";
  } else if (biomarkerOutOfRange > 0) {
    biomarkerSummaryTone = "alert";
    biomarkerSummaryLabel = `${biomarkerOutOfRange} outside range`;
  } else if (biomarkerBorderline > 0) {
    biomarkerSummaryTone = "warning";
    biomarkerSummaryLabel = `${biomarkerBorderline} borderline`;
  } else {
    biomarkerSummaryTone = "positive";
    biomarkerSummaryLabel = "all normal";
  }

  // Row 0 — Needs attention: severity-sorted list of alerts (+ risk fields
  // when the backend starts populating them). Render only when non-empty.
  const sortedAlerts = [...data.alerts].sort((a, b) => {
    const order = { alert: 0, warning: 1, info: 2 } as const;
    return order[a.severity] - order[b.severity];
  });
  // TODO risk fields: illness_risk_score / injury_risk_score / iron_status_flag
  // / cross_discipline_fatigue_index — when the backend exposes them, merge
  // into this list client-side with tone-coloured badges.

  // Row 1b — Today's plan: render if gym plan exists OR there's an event in
  // the next 14 days.
  const nextEvent = nextEvents[0] ?? null;
  const showRow1b = !!plan || !!nextEvent;

  // Row 1b — "readiness fit" chip on Planned session
  const readinessFit = computeReadinessFit(data.readiness.value, acwrValue);

  // Row 3 — Sleep present?
  const showSleep = !!data.sleep;

  // Row 4 — Today's activities
  const activities = data.activities;

  // Row 4 — Integrations. If all healthy + recent, show a quiet "all synced"
  // line; otherwise list each row with a red dot on failure.
  const integrationsQuiet =
    integrations.length > 0 &&
    integrations.every((i) => i.status === "active" && i.consecutive_failures === 0);

  return (
    <div className="mx-auto max-w-[1240px] px-5 py-6 lg:px-8 lg:py-8">
      <PageHeader
        title={t("overview.title")}
        subtitle={t("welcome.preview_overview")}
        actions={
          <div className="flex items-center gap-2">
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => window.print()}
              icon={<Download size={13} />}
            >
              <span className="hidden sm:inline">{t("activities.export")}</span>
            </ApexButton>
            <ApexButton
              variant="secondary"
              size="sm"
              onClick={() => ui.setView("biometrics")}
              iconRight={<span aria-hidden>→</span>}
            >
              {t("nav.biometrics")}
            </ApexButton>
          </div>
        }
      />

      {error && (
        <div className="mt-3 rounded-[var(--radius-card)] border border-alert/40 bg-alertSoft px-3 py-2 text-[12px] text-alertText">
          Could not reach the dashboard API — showing demo data. ({error})
        </div>
      )}

      {/* ====================================================== ROW 0 — Needs attention */}
      {sortedAlerts.length > 0 && (
        <Card className="mt-4">
          <CardHeader
            eyebrow={
              <span className="flex items-center gap-1.5">
                <AlertTriangle size={12} className="text-alertText" />
                Needs attention
                {/* TODO i18n */}
              </span>
            }
          />
          <ul className="flex flex-col gap-2">
            {sortedAlerts.map((a, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <Badge tone={severityTone(a.severity)} dot>
                  {a.severity}
                </Badge>
                <span className="text-[13px] leading-relaxed text-ink2">{a.message}</span>
              </li>
            ))}
            {/* TODO risk fields: illness_risk_score / injury_risk_score /
                iron_status_flag / cross_discipline_fatigue_index — merge here
                once the backend populates them. */}
          </ul>
        </Card>
      )}

      {/* ====================================================== ROW 1 — Readiness / Recovery / Strain */}
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-12">
        {/* Readiness — headline size xl */}
        <Card className="md:col-span-4">
          <CardHeader
            eyebrow={
              <span className="flex items-center gap-1.5">
                {t("overview.readiness_label")}
                <InfoButton title={t("overview.readiness_label")}>
                  <MetricInfoContent
                    whatItMeasures={METRIC_EXPLANATIONS.readiness.whatItMeasures}
                    whyItMatters={METRIC_EXPLANATIONS.readiness.whyItMatters}
                    whatInfluencesIt={METRIC_EXPLANATIONS.readiness.whatInfluencesIt}
                    howToReadIt={METRIC_EXPLANATIONS.readiness.howToReadIt}
                  />
                </InfoButton>
              </span>
            }
            right={
              <div className="flex items-center gap-1.5">
                {data.data_completeness && data.data_completeness !== "full" && (
                  <Badge tone="neutral">estimated</Badge>
                )}
                <DeltaChip
                  delta={data.readiness.delta_7d}
                  goodWhen="up"
                  suffix={t("overview.vs7d")}
                />
              </div>
            }
          />
          <BigStat
            size="xl"
            value={fmtNum(data.readiness.value, 0)}
            unit="/100"
            tone={readinessTone === "positive" ? "positive" : readinessTone === "warning" ? "warning" : readinessTone === "alert" ? "alert" : "muted"}
          />
          <div className="mt-3">
            <ScoreBar value={data.readiness.value} tone={toneFor(readinessTone)} height={6} />
          </div>
        </Card>

        {/* Recovery — size lg */}
        <Card className="md:col-span-4">
          <CardHeader
            eyebrow={
              <span className="flex items-center gap-1.5">
                {t("overview.recovery_label")}
                <InfoButton title={t("overview.recovery_label")}>
                  <MetricInfoContent
                    whatItMeasures={METRIC_EXPLANATIONS.recovery.whatItMeasures}
                    whyItMatters={METRIC_EXPLANATIONS.recovery.whyItMatters}
                    whatInfluencesIt={METRIC_EXPLANATIONS.recovery.whatInfluencesIt}
                    howToReadIt={METRIC_EXPLANATIONS.recovery.howToReadIt}
                  />
                </InfoButton>
              </span>
            }
            right={<DeltaChip delta={data.recovery.delta_7d} goodWhen="up" suffix={t("overview.vs7d")} />}
          />
          <BigStat
            size="lg"
            value={fmtNum(data.recovery.value, 0)}
            unit="/100"
            tone={recoveryTone === "positive" ? "positive" : recoveryTone === "warning" ? "warning" : recoveryTone === "alert" ? "alert" : "muted"}
          />
          <div className="mt-3">
            <ScoreBar value={data.recovery.value} tone={toneFor(recoveryTone)} height={6} />
          </div>
        </Card>

        {/* Strain — size lg, NEUTRAL tone */}
        <Card className="md:col-span-4">
          <CardHeader
            eyebrow={
              <span className="flex items-center gap-1.5">
                {t("overview.strain_label")}
                <InfoButton title={t("overview.strain_label")}>
                  <MetricInfoContent
                    whatItMeasures={METRIC_EXPLANATIONS.strain.whatItMeasures}
                    whyItMatters={METRIC_EXPLANATIONS.strain.whyItMatters}
                    whatInfluencesIt={METRIC_EXPLANATIONS.strain.whatInfluencesIt}
                    howToReadIt={METRIC_EXPLANATIONS.strain.howToReadIt}
                  />
                </InfoButton>
              </span>
            }
            right={<DeltaChip delta={data.strain.delta_7d} goodWhen="none" suffix={t("overview.vs7d")} />}
          />
          <BigStat
            size="lg"
            value={fmtNum(data.strain.value, 0)}
            unit="/100"
            tone="muted"
          />
          <div className="mt-3">
            <ScoreBar value={data.strain.value} tone="muted" height={6} />
          </div>
          <div className="num mt-2 text-[10px] text-faint">
            {/* TODO i18n */}
            neutral — high strain isn&apos;t bad
          </div>
        </Card>
      </div>

      {/* ====================================================== ROW 1b — Today's plan */}
      {showRow1b && (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-12">
          {/* Planned session */}
          {plan && (
            <Card className="md:col-span-7">
              <CardHeader
                eyebrow={
                  <span className="flex items-center gap-1.5">
                    <Dumbbell size={12} />
                    Today&apos;s plan
                    {/* TODO i18n */}
                  </span>
                }
                right={
                  <Badge tone={plan.status === "active" ? "positive" : "neutral"}>
                    {plan.status}
                  </Badge>
                }
              />
              <button
                type="button"
                onClick={() => ui.setView("training")}
                className="group block w-full text-left"
              >
                <div className="text-[15px] font-semibold text-ink group-hover:text-primaryText">
                  {plan.title}
                </div>
                <div className="num mt-1 text-[11px] text-muted">
                  {Array.isArray(plan.exercises) ? plan.exercises.length : 0} exercises · {plan.date}
                </div>
                {plan.adjustmentNote && (
                  <div className="mt-2 text-[12px] leading-relaxed text-muted line-clamp-2">
                    {plan.adjustmentNote}
                  </div>
                )}
                <Hairline className="my-3" />
                <ReadinessFitChip
                  label={readinessFit.label}
                  tone={readinessFit.tone}
                />
                <div className="num mt-2 flex items-center gap-1 text-[11px] text-primaryText">
                  Open in Training
                  <ChevronRight size={11} className="transition-transform group-hover:translate-x-0.5" />
                </div>
              </button>
            </Card>
          )}

          {/* Next event */}
          {nextEvent && (
            <Card className={plan ? "md:col-span-5" : "md:col-span-12"}>
              <CardHeader
                eyebrow={
                  <span className="flex items-center gap-1.5">
                    <Calendar size={12} />
                    Next event
                    {/* TODO i18n */}
                  </span>
                }
              />
              <NextEventBlock event={nextEvent} otherEvents={nextEvents.slice(1, 3)} todayIso={todayIso} />
            </Card>
          )}

          {/* Weather window — HIDDEN (no weather route exists). */}
          {/* TODO weather window — needs /api/weather/forecast */}
          {!plan && !nextEvent && (
            <Card className="md:col-span-12">
              <div className="flex items-center gap-2 text-[12px] text-muted">
                <CloudOff size={14} />
                {/* TODO i18n */}
                No weather forecast available.
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ====================================================== ROW 2 — Load & vitals */}
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* ACWR / load card */}
        <Card className="xl:col-span-8">
          <CardHeader
            eyebrow={t("overview.acwr_title")}
            right={
              <span className="num text-[10px] text-faint">
                {t("overview.optimal_window")}: {fmtNum(ACWR_OPT.low, 2)}–{fmtNum(ACWR_OPT.high, 2)}
              </span>
            }
          />
          <div className="flex items-baseline gap-3">
            <BigStat
              value={fmtNum(acwrValue, 2)}
              unit="ratio"
              size="lg"
              tone={acwrStatTone === "positive" ? "positive" : acwrStatTone === "warning" ? "warning" : acwrStatTone === "alert" ? "alert" : "muted"}
            />
          </div>

          {/* ACWR band indicator — optimal band highlighted, current marker */}
          {acwrValue !== null && Number.isFinite(acwrValue) && (
            <div className="num mt-4">
              <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface3">
                <div
                  className="absolute inset-y-0 bg-positiveSoft"
                  style={{
                    left: `${((ACWR_OPT.low - ACWR_VIEW.low) / (ACWR_VIEW.high - ACWR_VIEW.low)) * 100}%`,
                    width: `${((ACWR_OPT.high - ACWR_OPT.low) / (ACWR_VIEW.high - ACWR_VIEW.low)) * 100}%`,
                  }}
                />
                <div
                  className="absolute top-1/2 h-3.5 w-[3px] -translate-y-1/2 rounded-full bg-ink"
                  style={{
                    left: `${Math.max(0, Math.min(100, ((acwrValue - ACWR_VIEW.low) / (ACWR_VIEW.high - ACWR_VIEW.low)) * 100))}%`,
                  }}
                />
              </div>
              <div className="mt-1.5 flex justify-between text-[9px] text-faint">
                <span>0.5</span>
                <span>1.0</span>
                <span>1.5</span>
                <span>2.0</span>
              </div>
            </div>
          )}

          {/* 28-day acute (bar) / chronic (line) chart */}
          <div className="mt-4">
            {load && load.length > 0 ? (
              <LoadChart series={load} />
            ) : (
              <div className="rounded-[var(--radius-card)] border border-dashed border-hairline2 px-4 py-6 text-center text-[12px] text-muted">
                {/* TODO i18n */}
                No load data yet — connect Garmin to populate the 28-day chart.
              </div>
            )}
          </div>

          {/* Stat trio */}
          <div className="mt-4 grid grid-cols-3 gap-3">
            <StatPod label={t("overview.acute_load")} value={fmtNum(data.acute_load, 0)} unit="TSS" sub="7-day sum" />
            <StatPod label={t("overview.chronic_load")} value={fmtNum(data.chronic_load, 0)} unit="TSS" sub="28-day mean" />
            <StatPod
              label={t("overview.acwr_index")}
              value={fmtNum(acwrValue, 2)}
              tone={acwrStatTone === "positive" ? "positive" : acwrStatTone === "warning" ? "warning" : acwrStatTone === "alert" ? "alert" : "ink"}
            />
          </div>

          {/* Tone-reactive status line — FIXES the "no overreach" bug */}
          <div
            className={`mt-3 text-[12px] ${
              acwrT === "positive"
                ? "text-positiveText"
                : acwrT === "warning"
                ? "text-warningText"
                : acwrT === "alert"
                ? "text-alertText"
                : "text-muted"
            }`}
          >
            {acwrStatusLine(acwrT, acwrValue)}
          </div>
        </Card>

        {/* Biomarker strip */}
        <Card className="xl:col-span-4">
          <CardHeader
            eyebrow={t("overview.biomarkers")}
            right={<Badge tone={badgeTone(biomarkerSummaryTone)} dot>{biomarkerSummaryLabel}</Badge>}
          />
          <div className="flex flex-col gap-3">
            <BiomarkerTile
              label={t("overview.resting_hr")}
              value={data.resting_hr}
              unit="bpm"
              range={RHR_RANGE}
              tone={toneFor(rhrIn)}
              delta={data.resting_hr_delta_7d}
              goodWhen="down"
              info={METRIC_EXPLANATIONS.resting_hr}
              infoTitle={t("overview.resting_hr")}
            />
            <BiomarkerTile
              label={t("overview.spo2")}
              value={data.spo2_avg}
              unit="%"
              range={SPO2_RANGE}
              tone={toneFor(spo2In)}
              delta={data.spo2_delta_7d}
              goodWhen="up"
              info={METRIC_EXPLANATIONS.spo2_avg}
              infoTitle={t("overview.spo2")}
            />
            <BiomarkerTile
              label={t("overview.respiration")}
              value={data.respiration_avg}
              unit="brpm"
              range={RESP_RANGE}
              tone={toneFor(respIn)}
              info={METRIC_EXPLANATIONS.respiration_avg}
              infoTitle={t("overview.respiration")}
            />
            <BiomarkerTile
              label={t("overview.weight_kg")}
              value={data.weight_kg}
              unit="kg"
              range={null}
              tone="muted"
              info={METRIC_EXPLANATIONS.weight_kg}
              infoTitle={t("overview.weight_kg")}
            />
          </div>
        </Card>
      </div>

      {/* ====================================================== ROW 3 — Last night's sleep */}
      {showSleep && data.sleep && (
        <Card className="mt-4" pad>
          <CardHeader
            eyebrow={t("overview.last_night")}
            right={
              <div className="flex items-center gap-1.5">
                <DeltaChip delta={data.sleep_score.delta_7d} goodWhen="up" suffix={t("overview.vs7d")} />
                <ApexButton
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    ui.selectSleepDate(data.date);
                    ui.setView("sleep-night");
                  }}
                  iconRight={<ChevronRight size={11} />}
                >
                  {/* TODO i18n */}
                  Open night
                </ApexButton>
              </div>
            }
          />
          <button
            type="button"
            onClick={() => { ui.selectSleepDate(data.date); ui.setView("sleep"); }}
            className="group block w-full text-left"
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-12">
              {/* Score + total */}
              <div className="md:col-span-4">
                <Eyebrow>{t("overview.sleep_score")}</Eyebrow>
                <BigStat
                  size="xl"
                  value={fmtNum(data.sleep?.sleep_score ?? 0, 0)}
                  unit="/100"
                  tone={sleepTone === "positive" ? "positive" : sleepTone === "warning" ? "warning" : sleepTone === "alert" ? "alert" : "muted"}
                />
                <div className="mt-3">
                  <ScoreBar value={data.sleep?.sleep_score ?? null} tone={toneFor(sleepTone)} height={6} />
                </div>
                <div className="num mt-3 flex items-baseline gap-1.5 text-[11px] text-muted">
                  <span>{t("sleep.total")}</span>
                  <span className="text-[16px] font-bold text-ink">{fmtHours(data.sleep?.total_sleep_s ?? null)}</span>
                </div>
              </div>

              {/* Stage bar + legend */}
              <div className="md:col-span-5">
                <SleepStageBar sleep={data.sleep} />
              </div>

              {/* Mini stats: respiration / spo2 / restlessness */}
              <div className="md:col-span-3">
                <div className="grid grid-cols-3 gap-2 md:grid-cols-1">
                  <StatPod label={t("sleep.respiration")} value={fmtNum(data.sleep?.respiration_avg ?? null, 1)} unit="brpm" />
                  <StatPod label={t("sleep.spo2")} value={fmtNum(data.sleep?.spo2_avg ?? null, 1)} unit="%" />
                  <StatPod label={t("sleep.restlessness")} value={fmtNum(data.sleep?.restlessness ?? null, 0)} unit="%" />
                </div>
              </div>
            </div>
          </button>
        </Card>
      )}

      {/* ====================================================== ROW 4 — Logs & status */}
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-12">
        {/* Today's activities */}
        <Card className="md:col-span-5">
          <CardHeader eyebrow={t("overview.calibrated")} />
          {activities.length === 0 ? (
            <Empty title={t("overview.no_activities")} />
          ) : (
            <ul className="flex flex-col gap-2">
              {activities.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => { ui.selectActivity(a.id); ui.setView("activity-detail"); }}
                    className="group flex w-full items-start gap-2.5 rounded-[var(--radius-card)] border border-hairline bg-surface2 p-2.5 text-left transition-colors hover:border-hairline2"
                  >
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted transition-colors group-hover:bg-primarySoft group-hover:text-primaryText">
                      <SportIcon discipline={a.discipline} size={14} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] font-semibold leading-tight text-ink" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                        {a.title}
                      </div>
                      <div className="num mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted">
                        <span>{friendlyDiscipline(a.discipline, ui.locale)}</span>
                        <span aria-hidden className="text-faint">·</span>
                        <span>{fmtClock(a.start_time, ui.locale)}</span>
                        <span aria-hidden className="text-faint">·</span>
                        <Badge tone="neutral">{fmtDuration(a.duration_s)}</Badge>
                        {a.distance_m !== null && (
                          <><span aria-hidden className="text-faint">·</span><span>{fmtDistance(a.distance_m, "metric", 1)} km</span></>
                        )}
                        {a.avg_hr !== null && (
                          <><span aria-hidden className="text-faint">·</span><span>{a.avg_hr} bpm</span></>
                        )}
                        {a.training_load !== null && (
                          <><span aria-hidden className="text-faint">·</span><span>{fmtNum(a.training_load, 0)} TSS</span></>
                        )}
                      </div>
                    </div>
                    <ChevronRight size={12} className="mt-1 shrink-0 text-faint transition-colors group-hover:text-ink" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Gear due for service */}
        {gearDueList.length > 0 && (
          <Card className="md:col-span-4">
            <CardHeader
              eyebrow={
                <span className="flex items-center gap-1.5">
                  <Wrench size={12} />
                  Gear due for service
                  {/* TODO i18n */}
                </span>
              }
              right={
                <ApexButton
                  variant="ghost"
                  size="sm"
                  onClick={() => ui.setView("gear")}
                  iconRight={<ChevronRight size={11} />}
                >
                  {/* TODO i18n */}
                  All
                </ApexButton>
              }
            />
            <ul className="flex flex-col gap-3">
              {gearDueList.map(({ gear, usagePct }) => {
                const gearTone: DataTone = usagePct >= 100 ? "alert" : usagePct >= 90 ? "warning" : "positive";
                const hoursLeft =
                  gear.service_interval_hours != null
                    ? Math.max(0, gear.service_interval_hours - gear.hours_since_service)
                    : null;
                const kmLeft =
                  gear.service_interval_km != null
                    ? Math.max(0, gear.service_interval_km - gear.km_since_service)
                    : null;
                return (
                  <li key={gear.id}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-[13px] font-semibold text-ink">{gear.name}</div>
                        <div className="num text-[10px] text-faint">
                          {gear.gear_type}
                          {gear.brand ? ` · ${gear.brand}` : ""}
                        </div>
                      </div>
                      <Badge tone={badgeTone(gearTone)} dot>
                        {Math.round(usagePct)}%
                      </Badge>
                    </div>
                    <div className="mt-1.5">
                      <ScoreBar value={usagePct} tone={toneFor(gearTone)} height={4} />
                    </div>
                    <div className="num mt-1 text-[10px] text-muted">
                      {hoursLeft !== null && `~${fmtNum(hoursLeft, 0)} hrs to service`}
                      {hoursLeft !== null && kmLeft !== null && " · "}
                      {kmLeft !== null && `~${fmtNum(kmLeft, 0)} km to service`}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}

        {/* Integration health */}
        <Card className={gearDueList.length > 0 ? "md:col-span-3" : "md:col-span-7"}>
          <CardHeader eyebrow={t("overview.integrations")} />
          {integrations.length === 0 ? (
            <Empty title="No integrations connected" />
          ) : integrationsQuiet ? (
            <div className="flex items-center gap-2 text-[12px] text-positiveText">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-positive" />
              {/* TODO i18n */}
              All synced
            </div>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {integrations.map((i, idx) => {
                const failed = i.consecutive_failures > 0 || i.status === "error";
                const paused = i.status === "paused";
                const statusTone: DataTone = failed ? "alert" : paused ? "warning" : "positive";
                return (
                  <li key={`${i.provider}-${idx}`} className="flex items-center gap-2">
                    <span
                      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                        statusTone === "alert" ? "bg-alert" : statusTone === "warning" ? "bg-warning" : "bg-positive"
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-[12px] font-semibold text-ink">{i.provider}</span>
                        <span className="num shrink-0 text-[10px] text-faint">
                          {relativeTime(i.last_synced_at)}
                        </span>
                      </div>
                      <div className="num text-[10px] text-muted">
                        {i.is_main ? "main · " : ""}
                        {failed ? `${i.consecutive_failures} failure${i.consecutive_failures === 1 ? "" : "s"}` : paused ? "paused" : "active"}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>

      {/* ------------------------------------------------- date stamp */}
      <div className="num mt-4 text-right text-[10px] text-faint">
        {fmtDate(data.date, ui.locale)}
      </div>
    </div>
  );
}

/* ============================================================== sub-components */

function BiomarkerTile({
  label,
  value,
  unit,
  range,
  tone,
  delta,
  goodWhen,
  info,
  infoTitle,
}: {
  label: string;
  value: number | null;
  unit: string;
  range: { low: number; high: number } | null;
  tone: "positive" | "warning" | "alert" | "muted";
  delta?: number | null;
  goodWhen?: "up" | "down";
  info: { whatItMeasures: string; whyItMatters: string; whatInfluencesIt: string; howToReadIt: string };
  infoTitle: string;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-hairline bg-surface2 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Eyebrow className="truncate">{label}</Eyebrow>
          <InfoButton title={infoTitle}>
            <MetricInfoContent
              whatItMeasures={info.whatItMeasures}
              whyItMatters={info.whyItMatters}
              whatInfluencesIt={info.whatInfluencesIt}
              howToReadIt={info.howToReadIt}
            />
          </InfoButton>
        </div>
        {delta !== undefined && goodWhen && (
          <DeltaChip delta={delta} goodWhen={goodWhen} compact suffix={undefined} showSuffix={false} />
        )}
      </div>
      <div className="num mt-1 flex items-baseline gap-1 text-[20px] font-bold text-ink">
        {fmtNum(value, value !== null && Math.abs(value) < 100 ? 1 : 0)}
        <span className="text-[10px] font-medium text-muted">{unit}</span>
      </div>
      <div className="mt-1.5">
        <RangeBar
          value={value}
          low={range ? range.low : 0}
          high={range ? range.high : 100}
          tone={tone}
          unit={unit}
          height={4}
        />
        {range && (
          <div className="num mt-0.5 flex justify-between text-[9px] text-faint">
            <span>{range.low}</span>
            <span>{range.high}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** Sleep stage bar — Deep / REM / Light / Awake stacked + legend. */
function SleepStageBar({
  sleep,
}: {
  sleep: {
    stages: {
      deep_s: number | null;
      light_s: number | null;
      rem_s: number | null;
      awake_s: number | null;
    };
  };
}) {
  const deep = sleep.stages.deep_s ?? 0;
  const light = sleep.stages.light_s ?? 0;
  const rem = sleep.stages.rem_s ?? 0;
  const awake = sleep.stages.awake_s ?? 0;
  const total = deep + light + rem + awake || 1;
  const segments = [
    { label: "Deep", value: deep, color: "var(--c-stage-deep)" },
    { label: "REM", value: rem, color: "var(--c-stage-rem)" },
    { label: "Light", value: light, color: "var(--c-stage-core)" },
    { label: "Awake", value: awake, color: "var(--c-stage-awake)" },
  ];
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-[var(--radius-control)]">
        {segments.map((s, i) => (
          <div
            key={i}
            style={{ width: `${(s.value / total) * 100}%`, background: s.color, height: "100%" }}
            title={`${s.label}: ${fmtHours(s.value)}`}
          />
        ))}
      </div>
      <div className="num mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted">
        {segments.map((s, i) => (
          <span key={i} className="flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
            {s.label}
            <span className="text-faint">{fmtHours(s.value)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** "readiness fit" chip for the Planned session card. */
function ReadinessFitChip({ label, tone }: { label: string; tone: DataTone }) {
  const cls =
    tone === "positive"
      ? "text-positiveText bg-positiveSoft"
      : tone === "warning"
      ? "text-warningText bg-warningSoft"
      : tone === "alert"
      ? "text-alertText bg-alertSoft"
      : "text-muted bg-surface3";
  return (
    <span className={`eyebrow inline-flex items-center gap-1.5 rounded-[var(--radius-control)] px-1.5 py-0.5 !text-[10px] ${cls}`}>
      {label}
    </span>
  );
}

/** Compute the readiness-fit chip from today's readiness + ACWR. */
function computeReadinessFit(
  readiness: number | null,
  acwr: number | null,
): { label: string; tone: DataTone } {
  if (readiness === null) return { label: "No readiness data", tone: "muted" };
  if (readiness < 50) {
    if (acwr !== null && acwr > 1.3) return { label: `Hard session on ${readiness} readiness`, tone: "alert" };
    return { label: `Tough day — readiness ${readiness}`, tone: "warning" };
  }
  if (readiness < 70) {
    return { label: `Fair readiness ${readiness}`, tone: "warning" };
  }
  return { label: `Ready to train — ${readiness}`, tone: "positive" };
}

/** Next-event block: big countdown + taper progress dots. */
function NextEventBlock({
  event,
  otherEvents,
  todayIso,
}: {
  event: ApexEvent;
  otherEvents: ApexEvent[];
  todayIso: string;
}) {
  const days = Math.max(0, dayDiff(todayIso, event.date));
  // Taper: if the event has taperDays and we're inside the taper window
  // (today is within [eventDate - taperDays, eventDate)).
  let taperLine: string | null = null;
  if (event.taperDays && event.taperDays > 0) {
    const taperStart = addDays(event.date, -event.taperDays);
    const taperDayIdx = dayDiff(taperStart, todayIso); // 0..taperDays-1 within the window
    if (taperDayIdx >= 0 && taperDayIdx < event.taperDays) {
      taperLine = `taper day ${taperDayIdx + 1} of ${event.taperDays}`;
    }
  }
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <BigStat value={days} unit="days" size="lg" tone="ink" />
        <span className="num text-[11px] text-muted">until</span>
      </div>
      <div className="mt-1 text-[14px] font-semibold text-ink">{event.title}</div>
      <div className="num mt-0.5 text-[11px] text-muted">
        {event.kind} · {event.priority}
      </div>
      {taperLine && (
        <div className="num mt-2 text-[11px] text-warningText">
          {taperLine}
        </div>
      )}
      {otherEvents.length > 0 && (
        <div className="mt-3 border-t border-hairline pt-2">
          <div className="eyebrow !text-[9px] text-faint">Also upcoming</div>
          <ul className="mt-1 flex flex-col gap-1">
            {otherEvents.map((e) => (
              <li key={e.id} className="num flex items-center justify-between text-[11px]">
                <span className="truncate text-muted">{e.title}</span>
                <span className="shrink-0 text-faint">{Math.max(0, dayDiff(todayIso, e.date))}d</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** 28-day acute (bar) / chronic (line) SVG chart. */
function LoadChart({ series }: { series: DayLoad[] }) {
  // Render only days where acute + chronic are both non-null (the first ~27
  // days have null chronic because the rolling window isn't full).
  const usable = series.filter((d) => d.acute !== null && d.chronic !== null);
  if (usable.length < 2) {
    return (
      <div className="rounded-[var(--radius-card)] border border-dashed border-hairline2 px-4 py-6 text-center text-[12px] text-muted">
        Not enough load history yet — the 28-day chart needs ~28 days of data.
      </div>
    );
  }
  const W = 600;
  const H = 96;
  const padL = 4;
  const padR = 4;
  const padT = 6;
  const padB = 14;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const maxVal = Math.max(
    ...usable.map((d) => Math.max(d.acute ?? 0, d.chronic ?? 0)),
    10,
  );
  const barW = innerW / usable.length;
  const x = (i: number) => padL + i * barW + barW / 2;
  const y = (v: number) => padT + innerH - (v / maxVal) * innerH;

  // Chronic line as a polyline path.
  const linePath = usable
    .map((d, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(d.chronic ?? 0).toFixed(1)}`)
    .join(" ");

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ aspectRatio: `${W} / ${H}` }}>
        {/* horizontal grid lines */}
        {[0.25, 0.5, 0.75, 1].map((f, i) => (
          <line
            key={i}
            x1={padL}
            x2={W - padR}
            y1={padT + innerH * (1 - f)}
            y2={padT + innerH * (1 - f)}
            stroke="var(--c-hairline)"
            strokeWidth="0.5"
          />
        ))}
        {/* acute bars (state-tone coloured: positive when in optimal band,
            warning when elevated, alert when >1.5) */}
        {usable.map((d, i) => {
          const aT = acwrTone(d.acwr != null && d.chronic != null && d.chronic > 0 ? d.acwr / d.chronic : null);
          const fill =
            aT === "positive" ? "var(--c-positive)" : aT === "warning" ? "var(--c-warning)" : aT === "alert" ? "var(--c-alert)" : "var(--c-hairline2)";
          const v = d.acute ?? 0;
          const h = (v / maxVal) * innerH;
          return (
            <rect
              key={i}
              x={padL + i * barW + barW * 0.15}
              y={padT + innerH - h}
              width={barW * 0.7}
              height={h}
              fill={fill}
              rx={1}
            />
          );
        })}
        {/* chronic line */}
        <path d={linePath} fill="none" stroke="var(--c-primary)" strokeWidth="1.5" strokeLinejoin="round" />
        {/* x-axis: first / mid / last date */}
        <text x={padL} y={H - 2} fontSize="9" fill="var(--c-text-faint)" className="num">
          {usable[0].date.slice(5)}
        </text>
        <text x={W / 2} y={H - 2} fontSize="9" fill="var(--c-text-faint)" textAnchor="middle" className="num">
          {usable[Math.floor(usable.length / 2)].date.slice(5)}
        </text>
        <text x={W - padR} y={H - 2} fontSize="9" fill="var(--c-text-faint)" textAnchor="end" className="num">
          {usable[usable.length - 1].date.slice(5)}
        </text>
      </svg>
      <div className="num mt-1 flex items-center gap-3 text-[10px] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-2.5 rounded-sm bg-positive" />
          Acute (7d)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 bg-primary" />
          Chronic (28d)
        </span>
      </div>
    </div>
  );
}
