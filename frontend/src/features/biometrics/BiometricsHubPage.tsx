/**
 * Biometrics hub — the index of EVERY metric (mockup: HR telemetry's
 * metric-card row aesthetic). Each entry: name, live readout, assessment
 * badge, 60-day sparkline — a link to its own telemetry page
 * (/app/biometrics/{key}), so "every metric has a detailed page" is
 * structural, not aspirational.
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api, type MetricTrend } from "../../app/api";
import { Badge, Card, ErrorNote, Loading, PageHeader, Sparkline, fmtNum } from "../../components/kit";

/** Grouped catalog — keys mirror the backend CATALOG dict. */
const GROUPS: { title: string; keys: [string, string][] }[] = [
  {
    title: "biometrics.group_cardiac",
    keys: [
      ["resting_hr", "biometrics.resting_hr"],
      ["hrv_deviation", "biometrics.hrv"],
      ["spo2", "biometrics.spo2"],
      ["respiration", "biometrics.respiration_metric"],
    ],
  },
  {
    title: "sleep.title",
    keys: [
      ["sleep_duration", "biometrics.sleep_duration"],
      ["sleep_deep", "biometrics.sleep_deep_metric"],
      ["sleep_rem", "biometrics.sleep_rem_metric"],
      ["sleep_light", "biometrics.sleep_light_metric"],
      ["sleep_score", "overview.sleep_score"],
      ["restlessness", "biometrics.restlessness_metric"],
    ],
  },
  {
    title: "overview.strain_title",
    keys: [
      ["readiness", "biometrics.readiness_metric"],
      ["recovery", "biometrics.recovery_metric"],
      ["strain", "biometrics.strain_metric"],
      ["acwr", "biometrics.acwr_metric"],
      ["acute_load", "biometrics.acute_load_metric"],
      ["chronic_load", "biometrics.chronic_load_metric"],
      ["illness_risk", "biometrics.illness_risk"],
      ["injury_risk", "biometrics.injury_risk"],
    ],
  },
  {
    title: "biometrics.group_body",
    keys: [
      ["weight", "biometrics.weight"],
      ["body_fat", "biometrics.body_fat"],
      ["vo2max", "biometrics.vo2max"],
      ["steps", "biometrics.steps"],
      ["floors", "biometrics.floors"],
      ["hydration", "biometrics.hydration"],
    ],
  },
];

/** One metric card: 60-day trend + latest readout + assessment badge. */
function MetricCard({ metricKey, labelKey, unit, direction }: { metricKey: string; labelKey: string; unit: string; direction: string }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["spark", metricKey],
    queryFn: () => api.get<MetricTrend>(`/metrics/${metricKey}?days=60`),
  });
  const points = data?.points ?? [];
  const values = points.filter((p) => p.value !== null).map((p) => p.value!);
  const latest = values.at(-1) ?? null;
  const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  const tone =
    latest === null || mean === null
      ? "neutral"
      : (direction === "down" ? latest <= mean : latest >= mean)
        ? "positive"
        : "warning";
  const toneLabel =
    tone === "positive" ? t("biometrics.assess_optimal") : tone === "warning" ? t("biometrics.assess_watch") : t("biometrics.assess_no_data");

  return (
    <Link to={`/app/biometrics/${metricKey}`} className="group">
      <Card className="h-full transition-colors group-hover:bg-surface2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-[14px] font-semibold text-ink">{t(labelKey)}</div>
            <div className="num mt-1 flex items-baseline gap-1">
              <span className="text-[22px] font-bold text-ink">
                {latest === null ? "—" : fmtNum(latest, latest >= 100 ? 0 : 1)}
              </span>
              <span className="text-[10px] font-medium text-muted">{unit}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge tone={tone as "neutral" | "positive" | "warning"}>{toneLabel}</Badge>
            <ChevronRight size={14} className="text-faint transition-transform group-hover:translate-x-0.5" />
          </div>
        </div>
        <div className="mt-2 -mx-1">
          <Sparkline
            points={points.map((p) => p.value)}
            color={tone === "warning" ? "var(--c-warning)" : "var(--c-primary)"}
            height={44}
          />
        </div>
        <div className="num mt-1 flex justify-between text-[9px] text-faint">
          <span>60d</span>
          <span>{values.length} {t("sleep.readings")}</span>
        </div>
      </Card>
    </Link>
  );
}

export default function BiometricsHubPage() {
  const { t } = useTranslation();
  const catalog = useQuery({
    queryKey: ["metrics-catalog"],
    queryFn: () => api.get<Record<string, { unit: string; direction: string }>>("/metrics"),
  });

  if (catalog.isLoading) return <Loading />;
  if (catalog.isError) return <ErrorNote />;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title={t("biometrics.title")} subtitle={t("biometrics.subtitle")} />

      {GROUPS.map((group) => (
        <div key={group.title}>
          <div className="eyebrow mb-2">{t(group.title)}</div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            {group.keys.map(([key, labelKey]) => {
              const meta = catalog.data?.[key];
              if (!meta) return null;
              return (
                <MetricCard key={key} metricKey={key} labelKey={labelKey} unit={meta.unit} direction={meta.direction} />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
