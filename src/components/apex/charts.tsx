"use client";

/**
 * Apex Health — Interactive chart primitives with hover tooltips.
 *
 * The user's core request: "I need to be able to hover on graphs and see data."
 * Every chart in the app should show, at the cursor position:
 *   - which point/bar the cursor is over
 *   - the value(s) at that point
 *   - a label (date, name) for context
 *
 * Components:
 *   <InteractiveBarChart>  — bars with a hover crosshair + tooltip
 *   <InteractiveLineChart> — line(s) with a hover crosshair + tooltip
 *   <InteractiveComboChart> — bars + line(s) on the same axis (e.g. ACWR)
 *   <ChartTooltip>         — the shared tooltip renderer
 *
 * All are pure SVG + a small React state for the hovered index. No deps.
 */

import { type ReactNode, useMemo, useState, type CSSProperties } from "react";

/* ------------------------------------------------------------- Shared tooltip */

export interface TooltipPoint {
  /** Label shown at the top of the tooltip (usually a date). */
  label: string;
  /** One or more series values at this point. */
  values: { name: string; value: string; color: string }[];
}

export function ChartTooltip({
  point,
  x,
  y,
  containerW,
}: {
  point: TooltipPoint | null;
  x: number;
  y: number;
  containerW: number;
}) {
  if (!point) return null;
  // Flip the tooltip to the left side if we'd overflow the right edge.
  const flip = x > containerW - 160;
  const style: CSSProperties = {
    position: "absolute",
    left: flip ? undefined : x + 8,
    right: flip ? containerW - x + 8 : undefined,
    top: Math.max(4, y - 8),
    pointerEvents: "none",
    zIndex: 30,
  };
  return (
    <div
      style={style}
      className="num min-w-[140px] max-w-[200px] rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 shadow-[0_4px_16px_rgba(0,0,0,0.35)]"
    >
      <div className="mb-1 truncate text-[10px] font-semibold text-ink2">{point.label}</div>
      <div className="space-y-0.5">
        {point.values.map((v, i) => (
          <div key={i} className="flex items-center justify-between gap-2 text-[11px]">
            <span className="flex items-center gap-1.5 text-muted">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: v.color }} />
              {v.name}
            </span>
            <span className="font-semibold text-ink">{v.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- Interactive bar chart */

export interface BarSeries {
  name: string;
  color: string;
  /** Values per category; null = gap. */
  values: (number | null)[];
}

export interface BarCategory {
  label: string;
}

export function InteractiveBarChart({
  categories,
  series,
  height = 120,
  yUnit = "",
  formatValue,
  stack = false,
}: {
  categories: BarCategory[];
  series: BarSeries[];
  height?: number;
  yUnit?: string;
  formatValue?: (v: number | null) => string;
  stack?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 600;
  const padL = 6;
  const padR = 6;
  const padT = 8;
  const padB = 20;
  const innerW = W - padL - padR;
  const innerH = height - padT - padB;

  const maxVal = useMemo(() => {
    if (stack) {
      const sums = categories.map((_, i) =>
        series.reduce((s, ser) => s + (ser.values[i] ?? 0), 0),
      );
      return Math.max(...sums, 10);
    }
    return Math.max(
      ...series.flatMap((s) => s.values.map((v) => v ?? 0)),
      10,
    );
  }, [categories, series, stack]);

  const barW = innerW / categories.length;
  const x = (i: number) => padL + i * barW + barW / 2;
  const y = (v: number) => padT + innerH - (v / maxVal) * innerH;

  const fmt = formatValue || ((v: number | null) => (v === null ? "—" : `${v}${yUnit ? " " + yUnit : ""}`));

  const tooltipPoint = (i: number): TooltipPoint => ({
    label: categories[i].label,
    values: series.map((s) => ({
      name: s.name,
      value: fmt(s.values[i] ?? null),
      color: s.color,
    })),
  });

  return (
    <div className="relative w-full" style={{ aspectRatio: `${W} / ${height}` }}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="w-full"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * W;
          const idx = Math.floor((px - padL) / barW);
          setHover(idx >= 0 && idx < categories.length ? idx : null);
        }}
      >
        {/* grid */}
        {[0.25, 0.5, 0.75, 1].map((f, i) => (
          <line
            key={i}
            x1={padL}
            x2={W - padR}
            y1={padT + innerH * (1 - f)}
            y2={padT + innerH * (1 - f)}
            stroke="var(--c-hairline)"
            strokeWidth={0.5}
          />
        ))}
        {/* bars */}
        {categories.map((_, i) => {
          if (stack) {
            let acc = 0;
            return series.map((s, si) => {
              const v = s.values[i] ?? 0;
              const h = (v / maxVal) * innerH;
              const yTop = padT + innerH - h - (acc / maxVal) * innerH;
              acc += v;
              return (
                <rect
                  key={si}
                  x={padL + i * barW + barW * 0.15}
                  y={yTop}
                  width={barW * 0.7}
                  height={Math.max(0, h)}
                  fill={s.color}
                  opacity={hover === null || hover === i ? 1 : 0.5}
                  style={{ transition: "opacity 120ms" }}
                />
              );
            });
          }
          return series.map((s, si) => {
            const v = s.values[i] ?? 0;
            const h = (v / maxVal) * innerH;
            const groupW = barW * 0.7;
            const subW = groupW / series.length;
            return (
              <rect
                key={si}
                x={padL + i * barW + barW * 0.15 + si * subW}
                y={padT + innerH - h}
                width={subW * 0.92}
                height={Math.max(0, h)}
                fill={s.color}
                opacity={hover === null || hover === i ? 1 : 0.5}
                style={{ transition: "opacity 120ms" }}
              />
            );
          });
        })}
        {/* hover crosshair + highlight */}
        {hover !== null && (
          <>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={padT}
              y2={padT + innerH}
              stroke="var(--c-hairline-strong)"
              strokeWidth={0.8}
              strokeDasharray="2 2"
            />
            <rect
              x={padL + hover * barW}
              y={padT}
              width={barW}
              height={innerH}
              fill="var(--c-text)"
              opacity={0.04}
            />
          </>
        )}
      </svg>
      {hover !== null && (
        <ChartTooltip
          point={tooltipPoint(hover)}
          x={x(hover)}
          y={padT}
          containerW={W}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Interactive line chart */

export interface LineSeries {
  name: string;
  color: string;
  values: (number | null)[];
}

export function InteractiveLineChart({
  categories,
  series,
  height = 120,
  yUnit = "",
  formatValue,
  showDots = true,
  baseline = null,
  baselineLabel = "baseline",
}: {
  categories: BarCategory[];
  series: LineSeries[];
  height?: number;
  yUnit?: string;
  formatValue?: (v: number | null) => string;
  showDots?: boolean;
  baseline?: number | null;
  baselineLabel?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 600;
  const padL = 6;
  const padR = 6;
  const padT = 8;
  const padB = 20;
  const innerW = W - padL - padR;
  const innerH = height - padT - padB;

  const allVals = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  if (baseline !== null) allVals.push(baseline);
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);
  const range = maxVal - minVal || 1;
  const yMin = minVal - range * 0.1;
  const yMax = maxVal + range * 0.1;
  const yScale = (v: number) => padT + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const stepX = innerW / Math.max(categories.length - 1, 1);
  const x = (i: number) => padL + i * stepX;

  const fmt = formatValue || ((v: number | null) => (v === null ? "—" : `${v}${yUnit ? " " + yUnit : ""}`));

  const tooltipPoint = (i: number): TooltipPoint => ({
    label: categories[i].label,
    values: series.map((s) => ({
      name: s.name,
      value: fmt(s.values[i] ?? null),
      color: s.color,
    })),
  });

  return (
    <div className="relative w-full" style={{ aspectRatio: `${W} / ${height}` }}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="w-full"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * W;
          const idx = Math.round((px - padL) / stepX);
          setHover(idx >= 0 && idx < categories.length ? idx : null);
        }}
      >
        {/* grid */}
        {[0, 0.5, 1].map((f, i) => (
          <line
            key={i}
            x1={padL}
            x2={W - padR}
            y1={padT + innerH * f}
            y2={padT + innerH * f}
            stroke="var(--c-hairline)"
            strokeWidth={0.5}
          />
        ))}
        {/* baseline */}
        {baseline !== null && (
          <line
            x1={padL}
            x2={W - padR}
            y1={yScale(baseline)}
            y2={yScale(baseline)}
            stroke="var(--c-text-faint)"
            strokeWidth={0.8}
            strokeDasharray="3 3"
          />
        )}
        {/* lines */}
        {series.map((s, si) => {
          const pts = s.values
            .map((v, i) => (v === null ? null : { i, v }))
            .filter((p): p is { i: number; v: number } => p !== null);
          if (pts.length < 2) return null;
          const path = pts
            .map((p, k) => `${k === 0 ? "M" : "L"} ${x(p.i).toFixed(1)} ${yScale(p.v).toFixed(1)}`)
            .join(" ");
          return (
            <g key={si}>
              <path d={path} fill="none" stroke={s.color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
              {showDots &&
                pts.map((p, k) => (
                  <circle
                    key={k}
                    cx={x(p.i)}
                    cy={yScale(p.v)}
                    r={hover === p.i ? 3.5 : 2}
                    fill={s.color}
                    stroke="var(--c-surface)"
                    strokeWidth={1}
                    style={{ transition: "r 120ms" }}
                  />
                ))}
            </g>
          );
        })}
        {/* hover crosshair */}
        {hover !== null && (
          <>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={padT}
              y2={padT + innerH}
              stroke="var(--c-hairline-strong)"
              strokeWidth={0.8}
              strokeDasharray="2 2"
            />
          </>
        )}
      </svg>
      {hover !== null && (
        <ChartTooltip point={tooltipPoint(hover)} x={x(hover)} y={padT} containerW={W} />
      )}
      {/* baseline legend */}
      {baseline !== null && (
        <div className="absolute bottom-0 right-2 text-[9px] text-faint">
          {baselineLabel}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Interactive combo chart (bars + line, e.g. ACWR) */

export function InteractiveComboChart({
  categories,
  bars,
  lines,
  height = 130,
  formatBarValue,
  formatLineValue,
  barUnit = "",
  lineUnit = "",
}: {
  categories: BarCategory[];
  bars: BarSeries;            // a single bar series (e.g. acute load)
  lines: LineSeries[];        // one or more lines (e.g. chronic load, ACWR)
  height?: number;
  formatBarValue?: (v: number | null) => string;
  formatLineValue?: (v: number | null) => string;
  barUnit?: string;
  lineUnit?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 600;
  const padL = 6;
  const padR = 6;
  const padT = 8;
  const padB = 22;
  const innerW = W - padL - padR;
  const innerH = height - padT - padB;

  const barVals = bars.values.filter((v): v is number => v !== null);
  const lineVals = lines.flatMap((l) => l.values.filter((v): v is number => v !== null));
  const maxBar = Math.max(...barVals, 10);
  const minLine = Math.min(...lineVals, 0);
  const maxLine = Math.max(...lineVals, 1);
  const lineRange = maxLine - minLine || 1;

  const barW = innerW / categories.length;
  const x = (i: number) => padL + i * barW + barW / 2;
  const yBar = (v: number) => padT + innerH - (v / maxBar) * innerH;
  const yLine = (v: number) => padT + (1 - (v - minLine) / lineRange) * innerH;

  const fmtBar = formatBarValue || ((v: number | null) => (v === null ? "—" : `${v}${barUnit ? " " + barUnit : ""}`));
  const fmtLine = formatLineValue || ((v: number | null) => (v === null ? "—" : `${v}${lineUnit ? " " + lineUnit : ""}`));

  const tooltipPoint = (i: number): TooltipPoint => ({
    label: categories[i].label,
    values: [
      { name: bars.name, value: fmtBar(bars.values[i] ?? null), color: bars.color },
      ...lines.map((l) => ({
        name: l.name,
        value: fmtLine(l.values[i] ?? null),
        color: l.color,
      })),
    ],
  });

  return (
    <div className="relative w-full" style={{ aspectRatio: `${W} / ${height}` }}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="w-full"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * W;
          const idx = Math.floor((px - padL) / barW);
          setHover(idx >= 0 && idx < categories.length ? idx : null);
        }}
      >
        {/* grid */}
        {[0.25, 0.5, 0.75, 1].map((f, i) => (
          <line
            key={i}
            x1={padL}
            x2={W - padR}
            y1={padT + innerH * (1 - f)}
            y2={padT + innerH * (1 - f)}
            stroke="var(--c-hairline)"
            strokeWidth={0.5}
          />
        ))}
        {/* bars */}
        {categories.map((_, i) => {
          const v = bars.values[i] ?? 0;
          const h = (v / maxBar) * innerH;
          return (
            <rect
              key={i}
              x={padL + i * barW + barW * 0.15}
              y={padT + innerH - h}
              width={barW * 0.7}
              height={Math.max(0, h)}
              fill={bars.color}
              opacity={hover === null || hover === i ? 1 : 0.45}
              style={{ transition: "opacity 120ms" }}
            />
          );
        })}
        {/* lines */}
        {lines.map((l, li) => {
          const pts = l.values
            .map((v, i) => (v === null ? null : { i, v }))
            .filter((p): p is { i: number; v: number } => p !== null);
          if (pts.length < 2) return null;
          const path = pts
            .map((p, k) => `${k === 0 ? "M" : "L"} ${x(p.i).toFixed(1)} ${yLine(p.v).toFixed(1)}`)
            .join(" ");
          return (
            <g key={li}>
              <path d={path} fill="none" stroke={l.color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
              {pts.map((p, k) => (
                <circle
                  key={k}
                  cx={x(p.i)}
                  cy={yLine(p.v)}
                  r={hover === p.i ? 3.5 : 2}
                  fill={l.color}
                  stroke="var(--c-surface)"
                  strokeWidth={1}
                  style={{ transition: "r 120ms" }}
                />
              ))}
            </g>
          );
        })}
        {/* hover crosshair */}
        {hover !== null && (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={padT}
            y2={padT + innerH}
            stroke="var(--c-hairline-strong)"
            strokeWidth={0.8}
            strokeDasharray="2 2"
          />
        )}
      </svg>
      {hover !== null && (
        <ChartTooltip point={tooltipPoint(hover)} x={x(hover)} y={padT} containerW={W} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Legend */

export function ChartLegend({
  items,
  className = "",
}: {
  items: { name: string; color: string }[];
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-center gap-3 ${className}`}>
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-1.5 text-[10px] text-muted">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: it.color }} />
          {it.name}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------- Info tooltip (for static charts) */

/** A small (i) info badge that, on hover, shows an explanation. Use for
 *  chart titles where the user needs context ("what do these bars mean?"). */
export function ChartInfoBadge({ text }: { text: string | ReactNode }) {
  return (
    <span
      className="group relative inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full text-faint transition-colors hover:bg-surface2 hover:text-ink"
      aria-label="chart info"
    >
      <span className="text-[10px] font-bold">i</span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-40 mb-1 w-52 -translate-x-1/2 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[11px] text-muted opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
        {text}
      </span>
    </span>
  );
}
