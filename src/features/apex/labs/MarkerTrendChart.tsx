"use client";

/**
 * Apex Health — Labs marker trend chart (plan §7).
 *
 * A custom inline SVG (rather than reusing InteractiveLineChart) because the
 * spec requires:
 *   - the reference range as a SHADED BAND across the chart width
 *   - points coloured in-range (positive) vs out-of-range (alert)
 *   - a hover crosshair + tooltip
 * The shared InteractiveLineChart only supports a single baseline line, not a
 * band, and colours all dots by the series colour. This small chart reuses
 * the Apex visual vocabulary (hairline grid, semantic state colours, mono
 * numerals, ChartTooltip from charts.tsx) so it does not introduce a new
 * visual language.
 *
 * Lives under src/features/apex/labs (off-limits kit/charts untouched).
 */

import { useState } from "react";
import { ChartTooltip, type TooltipPoint } from "@/components/apex/charts";

export interface MarkerPoint {
  date: string;     // ISO YYYY-MM-DD
  value: number | null;
  isDonation?: boolean;
  label?: string;   // short label (e.g. "12 May")
}

interface Props {
  points: MarkerPoint[];
  refLow: number;
  refHigh: number;
  unit: string;
  height?: number;
  baselineLabel?: string;
}

export function MarkerTrendChart({
  points,
  refLow,
  refHigh,
  unit,
  height = 160,
  baselineLabel = "ref range",
}: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 600;
  const padL = 8;
  const padR = 8;
  const padT = 10;
  const padB = 22;
  const innerW = W - padL - padR;
  const innerH = height - padT - padB;

  const finiteVals = points.map((p) => p.value).filter((v): v is number => v !== null && Number.isFinite(v));
  if (finiteVals.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-[var(--radius-card)] border border-dashed border-hairline2 px-6 py-10 text-[12px] text-muted"
        style={{ minHeight: height }}
      >
        Add a panel to see trends
      </div>
    );
  }

  const rawMin = Math.min(...finiteVals, refLow);
  const rawMax = Math.max(...finiteVals, refHigh);
  const range = Math.max(rawMax - rawMin, 1);
  const yMin = rawMin - range * 0.12;
  const yMax = rawMax + range * 0.12;
  const yScale = (v: number) => padT + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const stepX = innerW / Math.max(points.length - 1, 1);
  const x = (i: number) => padL + i * stepX;

  // Build the main line path, skipping nulls (gaps rather than interpolating).
  const present = points
    .map((p, i) => (p.value !== null && Number.isFinite(p.value) ? { i, v: p.value as number } : null))
    .filter((p): p is { i: number; v: number } => p !== null);

  const linePath = present
    .map((p, k) => `${k === 0 ? "M" : "L"} ${x(p.i).toFixed(1)} ${yScale(p.v).toFixed(1)}`)
    .join(" ");

  // Reference-range band as a filled rect from refLow to refHigh (data space).
  const bandY = yScale(refHigh);
  const bandH = Math.max(0, yScale(refLow) - yScale(refHigh));

  // Midpoint baseline.
  const midY = yScale((refLow + refHigh) / 2);

  const inRange = (v: number) => v >= refLow && v <= refHigh;

  const fmt = (v: number | null) =>
    v === null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit ? " " + unit : ""}`;

  const tooltipPoint = (i: number): TooltipPoint => ({
    label: points[i].label ?? points[i].date,
    values: [
      {
        name: "value",
        value: fmt(points[i].value),
        color: points[i].value !== null && inRange(points[i].value) ? "var(--c-positive)" : "var(--c-alert)",
      },
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
          const idx = Math.round((px - padL) / stepX);
          setHover(idx >= 0 && idx < points.length ? idx : null);
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

        {/* reference-range band */}
        <rect x={padL} y={bandY} width={innerW} height={bandH} fill="var(--c-positive)" fillOpacity={0.08} />
        <line x1={padL} x2={W - padR} y1={bandY} y2={bandY} stroke="var(--c-positive)" strokeWidth={0.5} strokeOpacity={0.5} />
        <line x1={padL} x2={W - padR} y1={bandY + bandH} y2={bandY + bandH} stroke="var(--c-positive)" strokeWidth={0.5} strokeOpacity={0.5} />

        {/* midpoint dashed line */}
        <line x1={padL} x2={W - padR} y1={midY} y2={midY} stroke="var(--c-text-faint)" strokeWidth={0.8} strokeDasharray="3 3" />

        {/* main value line */}
        {present.length >= 2 && (
          <path d={linePath} fill="none" stroke="var(--c-primary)" strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
        )}

        {/* donation markers — vertical hairline + dot at the bottom */}
        {points.map((p, i) =>
          p.isDonation ? (
            <g key={`don-${i}`}>
              <line x1={x(i)} x2={x(i)} y1={padT} y2={padT + innerH} stroke="var(--c-hairline-strong)" strokeWidth={0.5} strokeDasharray="2 3" />
              <circle cx={x(i)} cy={padT + innerH} r={2.5} fill="var(--c-alert)" />
            </g>
          ) : null,
        )}

        {/* value dots — positive when in range, alert when out of range */}
        {present.map((p, k) => {
          const colour = inRange(p.v) ? "var(--c-positive)" : "var(--c-alert)";
          return (
            <circle
              key={`dot-${k}`}
              cx={x(p.i)}
              cy={yScale(p.v)}
              r={hover === p.i ? 3.5 : 2.2}
              fill={colour}
              stroke="var(--c-surface)"
              strokeWidth={1}
              style={{ transition: "r 120ms" }}
            />
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

      {/* band legend */}
      <div className="absolute bottom-0 right-2 text-[9px] text-faint">
        {baselineLabel}: {Number.isInteger(refLow) ? refLow : refLow.toFixed(1)}–
        {Number.isInteger(refHigh) ? refHigh : refHigh.toFixed(1)} {unit}
      </div>
    </div>
  );
}
