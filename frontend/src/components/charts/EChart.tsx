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
  MarkPointComponent,
  MarkLineComponent,
  MarkAreaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useUi } from "../../app/stores/ui";

echarts.use([
  LineChart,
  BarChart,
  CustomChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkPointComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer,
]);

export type ChartOption = echarts.EChartsCoreOption;

export function useChartTheme() {
  const theme = useUi((s) => s.theme);
  const ink = theme === "light" ? "#242420" : "#f2f1ed";
  const muted = theme === "light" ? "#696960" : "#aaa9a5";
  const hairline =
    theme === "light" ? "rgba(15,23,42,0.10)" : "rgba(255,255,255,0.08)";
  const surface = theme === "light" ? "#fffefa" : "#242424";
  return {
    theme,
    ink,
    muted,
    hairline,
    surface,
    primary: theme === "light" ? "#c9511e" : "#ed7435",
    positive: theme === "light" ? "#347858" : "#76b994",
    alert: theme === "light" ? "#b73f3f" : "#e07878",
    warning: theme === "light" ? "#a26b12" : "#d6a755",
    stage: {
      awake: theme === "light" ? "#d5d3ca" : "#c9c7bf",
      rem: theme === "light" ? "#aaa89c" : "#a2a097",
      core: "#74766e",
      deep: theme === "light" ? "#353b34" : "#4b4b46",
    },
    font: '12px "Geist", sans-serif',
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
