import { useTranslation } from "react-i18next";
import { useUi } from "../../app/stores/ui";
import type { SleepList } from "../../app/api";
import { EChart, useChartTheme } from "../../components/charts/EChart";
import { fmtHours } from "../../components/kit";

import { sleepWindow } from "./sleep-timing";
export function SleepTimingChart({ nights }: { nights: SleepList["items"] }) {
  const { t } = useTranslation();
  const timezone = useUi(s => s.me?.timezone) ?? "Europe/Rome";
  const c = useChartTheme();
  const ordered = [...nights].sort((a, b) => a.local_date.localeCompare(b.local_date));
  const windows = ordered.map(n => sleepWindow(n.start_time, n.end_time, n.local_date, timezone));
  const clock = (v: number) => { const minutes = ((Math.round(v * 60) % 1440) + 1440) % 1440; return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`; };
  const lower = Math.floor(Math.min(-6, ...windows.map(w => w[0])));
  const upper = Math.ceil(Math.max(12, ...windows.map(w => w[1])));
  return <EChart height={260} option={{
    animation: false, grid: { left: 45, right: 12, top: 16, bottom: 36 },
    tooltip: { trigger: "item", confine: true, backgroundColor: c.surface, borderColor: c.hairline, textStyle: { color: c.ink },
      formatter: (p: { dataIndex: number }) => { const n = ordered[p.dataIndex], w = windows[p.dataIndex]; return `${n.local_date}<br>${t("sleep.bed_window")}: ${clock(w[0])}–${clock(w[1])}<br>${t("sleep.time_asleep")}: ${fmtHours(n.total_sleep_s)}`; } },
    xAxis: { type: "category", data: ordered.map(n => n.local_date), axisLabel: { color: c.muted, formatter: (v: string) => v.slice(5) }, axisTick: { show: false }, axisLine: { lineStyle: { color: c.hairline } } },
    yAxis: { type: "value", inverse: true, min: lower, max: upper, interval: 3, axisLabel: { color: c.muted, formatter: clock }, splitLine: { lineStyle: { color: c.hairline } } },
    series: [{ type: "custom", clip: true, data: windows.map((w, i) => [i, w[0], w[1]]),
      renderItem: (_: unknown, api: { value: (i: number) => number; coord: (v: number[]) => number[]; size: (v: number[]) => number[] }) => {
        const bed = api.coord([api.value(0), api.value(1)]), wake = api.coord([api.value(0), api.value(2)]);
        const width = Math.max(3, api.size([1, 0])[0] * 0.6);
        return { type: "rect", shape: { x: bed[0] - width / 2, y: Math.min(bed[1], wake[1]), width, height: Math.max(1, Math.abs(wake[1] - bed[1])) }, style: { fill: c.stage.core } };
      } }],
  }} />;
}
