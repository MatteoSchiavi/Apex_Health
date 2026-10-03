import { useTranslation } from "react-i18next";
import { EChart, useChartTheme } from "./EChart";
import { Empty } from "../kit";
import { shiftDay } from "../data";
export function TrendChart({
  points,
  unit,
  label,
  height = 220,
  bar = false,
  start,
  end,
  reference,
}: {
  points: { date: string; value: number | null }[];
  unit: string;
  label: string;
  height?: number;
  bar?: boolean;
  start?: string;
  end?: string;
  reference?: number | null;
}) {
  const c = useChartTheme();
  const { t } = useTranslation();
  if (!points.some((p) => p.value != null))
    return <Empty>{t("biometrics.no_data")}</Empty>;
  // Add missing calendar days so a sparse history never looks continuous.
  const byDate = new Map(points.map((p) => [p.date, p.value]));
  const rows: { date: string; value: number | null }[] = [];
  const first = start ?? points[0].date;
  const last = end ?? points.at(-1)!.date;
  for (let day = first; day <= last; day = shiftDay(day, 1))
    rows.push({ date: day, value: byDate.get(day) ?? null });
  const latest = [...rows].reverse().find((p) => p.value != null);
  return (
    <div
      role="img"
      aria-label={label + " · " + unit + " · " + first + " – " + last}
    >
      <EChart
        height={height}
        option={{
          animation: false,
          grid: { left: 48, right: 16, top: 16, bottom: 32 },
          tooltip: {
            trigger: "axis",
            confine: true,
            backgroundColor: c.surface,
            borderColor: c.hairline,
            textStyle: { color: c.ink, fontFamily: "Geist", fontSize: 13 },
            valueFormatter: (v: number | null) =>
              v == null
                ? "—"
                : v.toLocaleString(undefined, { maximumFractionDigits: 2 }) +
                  " " +
                  unit,
          },
          xAxis: {
            type: "category",
            data: rows.map((p) => p.date),
            boundaryGap: bar,
            axisLine: { show: false },
            axisTick: { show: false },
            axisLabel: {
              color: c.muted,
              fontSize: 12,
              hideOverlap: true,
              formatter: (v: string) =>
                new Date(v + "T12:00:00").toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                }),
            },
          },
          yAxis: {
            type: "value",
            scale: !bar,
            splitNumber: 2,
            axisLabel: { color: c.muted, fontSize: 12 },
            splitLine: { lineStyle: { color: c.hairline } },
          },
          series: [
            {
              name: label,
              type: bar ? "bar" : "line",
              data: rows.map((p) => p.value),
              connectNulls: false,
              showSymbol: false,
              smooth: false,
              barMaxWidth: 12,
              lineStyle: { color: c.ink, width: 2 },
              itemStyle: { color: c.ink, opacity: bar ? 0.65 : 1 },
              markPoint:
                !bar && latest
                  ? {
                      symbol: "circle",
                      symbolSize: 6,
                      label: { show: false },
                      data: [{ coord: [latest.date, latest.value] }],
                    }
                  : undefined,
              markLine:
                reference != null
                  ? {
                      silent: true,
                      symbol: "none",
                      label: { show: false },
                      lineStyle: { color: c.muted, type: "dashed" },
                      data: [{ yAxis: reference }],
                    }
                  : undefined,
            },
          ],
        }}
      />
    </div>
  );
}
