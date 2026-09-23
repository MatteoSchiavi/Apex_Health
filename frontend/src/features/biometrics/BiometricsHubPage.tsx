/**
 * Biometrics hub — the index of EVERY metric. Each entry is a link to its
 * own telemetry page (/app/biometrics/{key}), so "every metric has a
 * detailed page" is structural, not aspirational: the catalog comes from
 * GET /metrics and pages render generically.
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { api, type MetricTrend } from "../../app/api";
import { Badge, Card, ErrorNote, Loading, fmtNum } from "../../components/kit";
import { EChart, useChartTheme } from "../../components/charts/EChart";

/** Grouped catalog — keys mirror the backend CATALOG dict. */
const GROUPS: { title: string; keys: [string, string][] }[] = [
  {
    title: "biometrics.title",
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
    title: "settings.profile",
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

/** One 60-day sparkline per group shown on the hub via the shared trend API. */
function GroupSpark({ keys }: { keys: string[] }) {
  const c = useChartTheme();
  const first = keys[0];
  const { data } = useQuery({
    queryKey: ["spark", first],
    queryFn: () => api.get<MetricTrend>(`/metrics/${first}?days=60`),
  });
  if (!data || !data.points.some((p) => p.value !== null)) return null;
  return (
    <EChart
      option={{
        grid: { left: 0, right: 0, top: 4, bottom: 0 },
        xAxis: { type: "category", show: false, data: data.points.map((p) => p.date) },
        yAxis: { type: "value", show: false },
        series: [
          {
            type: "line",
            data: data.points.map((p) => p.value),
            showSymbol: false,
            smooth: true,
            lineStyle: { color: c.primary, width: 1.4 },
            areaStyle: { color: c.primary, opacity: 0.1 },
          },
        ]}
      }
      height={56}
    />
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
    <div className="flex flex-col gap-4">
      <div>
        <div className="eyebrow">{t("app.name")} {t("app.suffix")}</div>
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">
          {t("biometrics.title")}
        </h1>
        <div className="mt-0.5 text-[12px] text-muted">{t("biometrics.subtitle")}</div>
      </div>

      {GROUPS.map((group) => (
        <div key={group.title}>
          <div className="eyebrow mb-2">{t(group.title)}</div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {group.keys.map(([key, labelKey]) => {
              const meta = catalog.data?.[key];
              if (!meta) return null;
              return (
                <Link key={key} to={`/app/biometrics/${key}`}>
                  <Card className="transition-colors hover:bg-surface2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-[14px] font-semibold text-ink">{t(labelKey)}</div>
                        <div className="num mt-0.5 text-[11px] text-muted">{meta.unit}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone="neutral">
                          {meta.direction === "down"
                            ? t("common.low")
                            : meta.direction === "up"
                              ? t("common.high")
                              : t("common.fair")}
                        </Badge>
                        <ChevronRight size={14} className="text-faint" />
                      </div>
                    </div>
                    <div className="mt-2 -mx-1">
                      <GroupSpark keys={[key]} />
                    </div>
                  </Card>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export function fmtStat(v: number | null | undefined, digits = 1): string {
  return fmtNum(v, digits);
}
