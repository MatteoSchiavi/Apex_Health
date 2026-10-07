import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api, type MetricTrend } from "../../app/api";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  Segmented,
  StatPod,
  fmtNum,
  fmtHours,
} from "../../components/kit";
import { TrendChart } from "../../components/charts/TrendChart";
import {
  assess,
  LEGACY_HEURISTICS,
  METRIC_LABELS,
  useUnits,
} from "../../components/data";
import { MetricDirection, PersonalRange, RANGE_METRICS } from "../../components/MetricInterpretation";
import { explainMetric } from "./education/explain";
import { MetricEducationDisclosure } from "./education/MetricEducationDisclosure";
export default function MetricPage() {
  const { key = "" } = useParams();
  const { t } = useTranslation();
  const units = useUnits();
  const [range, setRange] = useState("90");
  const trend = useQuery({
    queryKey: ["metric", key, range],
    queryFn: () =>
      api.get<MetricTrend>(
        "/metrics/" + encodeURIComponent(key) + "?days=" + range,
      ),
    enabled: !!key,
  });
  if (trend.isLoading) return <Loading />;
  if (trend.isError || !trend.data) return <ErrorNote />;
  const data = trend.data;
  const education = explainMetric(data);
  const latest = [...data.points].reverse().find((p) => p.value != null);
  const label = METRIC_LABELS[key]
    ? t(METRIC_LABELS[key])
    : key.replaceAll("_", " ");
  const status = assess(key, latest?.value ?? null);
  const unit = units.metricUnit(key, data.unit);
  const formatValue = (value: number | null) => data.unit === "h" ? fmtHours(value == null ? null : value * 3600) : fmtNum(units.metric(key, value), ["steps", "floors"].includes(key) ? 0 : 1);
  return (
    <div className="flex flex-col gap-6">
      <Link className="text-link text-muted" to="/app/biometrics">
        <ArrowLeft size={16} />
        {t("biometrics.title")}
      </Link>
      <PageHeader
        title={label}
        subtitle={t("design.metric_detail_sub")}
        actions={
          <Segmented
            value={range}
            onChange={setRange}
            options={[7, 28, 90, 180, 365].map((r) => ({
              value: String(r),
              label: [7,28,180].includes(r) ? t("metricView.days" + r) : t("biometrics." + r + "d"),
            }))}
          />
        }
      />
      {LEGACY_HEURISTICS.includes(key) && (
        <p className="text-[13px] text-muted">
          {t("lab.legacy_metric_note")}{" "}
          <Link className="text-link" to="/app/lab">
            {t("lab.baselines")} ↗
          </Link>
        </p>
      )}
      {!latest ? (
        <Card>
          <Empty>{t("biometrics.no_data")}</Empty>
        </Card>
      ) : (
        <>
          <Card className="!p-6 md:!p-8">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
              <div>
                <div className="mb-5 flex items-center gap-4">
                  <span className="text-[13px] text-muted">
                    {t("biometrics.latest")} · {latest.date}
                  </span>
                  <Badge tone={status.tone}>{t(status.key)}</Badge>
                </div>
                <span className="num hero-number">
                  {formatValue(latest.value)}
                </span>
                {data.unit !== "h" && <span className="ml-4 text-[18px] text-muted">{unit}</span>}
                <div className="mt-3"><MetricDirection metric={key} points={data.points} /></div>
                {RANGE_METRICS.has(key) && <div className="mt-5"><PersonalRange trend={data} /></div>}
              </div>
              <p className="text-[12px] text-muted">
                {data.start_date} – {data.end_date}
              </p>
            </div>
            {education && <MetricEducationDisclosure key={key} education={education} />}
            <TrendChart
              label={label}
              unit={unit}
              points={data.points.map((p) => ({
                ...p,
                value: units.metric(key, p.value),
              }))}
              start={data.start_date}
              end={data.end_date}
              height={300}
              bar={["steps", "floors", "hydration"].includes(key)}
              reference={units.metric(key, data.stats.mean ?? null)}
            />
            <div className="mt-6 grid grid-cols-2 gap-4 border-t border-hairline pt-3 md:grid-cols-4">
              <StatPod
                label={t("biometrics.mean")}
                value={formatValue(data.stats.mean ?? null)}
                unit={data.unit === "h" ? undefined : unit}
              />
              <StatPod
                label={t("biometrics.min")}
                value={formatValue(data.stats.min ?? null)}
                unit={data.unit === "h" ? undefined : unit}
              />
              <StatPod
                label={t("biometrics.max")}
                value={formatValue(data.stats.max ?? null)}
                unit={data.unit === "h" ? undefined : unit}
              />
              <StatPod
                label={t("biometrics.count")}
                value={fmtNum(data.stats.count)}
              />
            </div>
            <p className="mt-3 text-[12px] text-muted">
              {t("design.chart_note")}
            </p>
          </Card>
          <details className="border-y border-hairline py-5">
            <summary className="cursor-pointer text-[14px] font-medium">
              {t("design.show_measurements")}
            </summary>
            <div className="table-scroll mt-4 max-h-96">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("training.event_date")}</th>
                    <th className="numeric">
                      {label} · {unit}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.points].reverse().map((p) => (
                    <tr key={p.date}>
                      <td>{p.date}</td>
                      <td className="numeric">
                        {formatValue(p.value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
