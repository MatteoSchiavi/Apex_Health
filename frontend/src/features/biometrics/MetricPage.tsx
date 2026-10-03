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
} from "../../components/kit";
import { TrendChart } from "../../components/charts/TrendChart";
import { assess, METRIC_LABELS, useUnits } from "../../components/data";
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
  const latest = [...data.points].reverse().find((p) => p.value != null);
  const label = METRIC_LABELS[key]
    ? t(METRIC_LABELS[key])
    : key.replaceAll("_", " ");
  const status = assess(key, latest?.value ?? null);
  const unit = units.metricUnit(key, data.unit);
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
            options={[7, 30, 90, 180, 365].map((r) => ({
              value: String(r),
              label: t("biometrics." + r + "d"),
            }))}
          />
        }
      />
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
                  {fmtNum(
                    units.metric(key, latest.value),
                    ["steps", "floors"].includes(key) ? 0 : 1,
                  )}
                </span>
                <span className="ml-4 text-[18px] text-muted">{unit}</span>
              </div>
              <p className="text-[12px] text-muted">
                {data.start_date} – {data.end_date}
              </p>
            </div>
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
                value={fmtNum(units.metric(key, data.stats.mean ?? null), 1)}
                unit={unit}
              />
              <StatPod
                label={t("biometrics.min")}
                value={fmtNum(units.metric(key, data.stats.min ?? null), 1)}
                unit={unit}
              />
              <StatPod
                label={t("biometrics.max")}
                value={fmtNum(units.metric(key, data.stats.max ?? null), 1)}
                unit={unit}
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
                        {fmtNum(units.metric(key, p.value), 2)}
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
