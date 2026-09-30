/**
 * Theme-aware ECharts wrapper. One place owns chart aesthetics so every
 * chart in the product shares the hairline/telemetry look (design law).
 * Re-renders on theme change; disposes cleanly.
 */

import { type ReactNode, useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart, BarChart, CustomChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkAreaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useUi } from "../../app/stores/ui";

echarts.use([
  LineChart, BarChart, CustomChart, ScatterChart,
  GridComponent, TooltipComponent, LegendComponent, DataZoomComponent,
  MarkLineComponent, MarkAreaComponent,
  CanvasRenderer,
]);

export type ChartOption = echarts.EChartsCoreOption;

export function useChartTheme() {
  const theme = useUi((s) => s.theme);
  const ink = theme === "light" ? "#0f172a" : "#e2e2e8";
  const muted = theme === "light" ? "#64748b" : "#8c909f";
  const hairline = theme === "light" ? "rgba(15,23,42,0.10)" : "rgba(255,255,255,0.08)";
  const surface = theme === "light" ? "#ffffff" : "#181c26";
  return {
    theme,
    ink, muted, hairline, surface,
    primary: theme === "light" ? "#2563eb" : "#3b82f6",
    positive: theme === "light" ? "#059669" : "#10b981",
    alert: theme === "light" ? "#dc2626" : "#ef4444",
    warning: theme === "light" ? "#d97706" : "#f59e0b",
    stage: {
      awake: theme === "light" ? "#dc2626" : "#ef4444",
      rem: theme === "light" ? "#3b82f6" : "#60a5fa",
      core: "#3b5bdb",
      deep: theme === "light" ? "#4338ca" : "#3730a3",
    },
    font: '12px "Geist", sans-serif',
    mono: '11px "JetBrains Mono", monospace',
  };
}

export function EChart({
  option,
  height = 280,
  onEvents,
  group,
}: {
  option: ChartOption;
  height?: number;
  onEvents?: { type: string; handler: (params: unknown) => void }[];
  group?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const t = useChartTheme();
  const theme = t.theme;

  useEffect(() => {
    if (!el.current) return;
    chart.current = echarts.init(el.current, undefined, { renderer: "canvas" });
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    c.setOption(option, { notMerge: true });
    if (group) c.group = group;
  }, [option, group]);

  useEffect(() => {
    const c = chart.current;
    if (!c || !onEvents) return;
    const handlers = onEvents.map(({ type, handler }) => {
      c.on(type, handler);
      return { type, handler };
    });
    return () => {
      handlers.forEach(({ type, handler }) => c.off(type, handler));
    };
  }, [onEvents, theme]);

  const node: ReactNode = <div ref={el} style={{ width: "100%", height }} />;
  return node;
}
