"use client";

/**
 * Apex Health — Overview / Home dashboard.
 *
 * Route purpose: answer "How am I doing right now?" by synthesizing the most
 * relevant information from the current day — readiness, recovery, sleep,
 * load, HRV, resting HR, recent activity, alerts, training context — into a
 * single calm, monochrome surface.
 *
 * Top portion is IMMEDIATELY understandable (readiness hero + synthesis
 * diagnosis + ACWR). Lower portion provides deeper supporting information
 * (biomarkers, activities, last night, parasympathetic tone).
 *
 * Layout: 12-column grid on lg+, single column on mobile.
 * Visual law: monochrome base + 3 semantic colors, Geist + JetBrains Mono,
 * 4px controls / 8px cards, 1px hairlines, tabular figures, label-caps eyebrows.
 */

import { useState } from "react";
import { Sparkles, Download, ChevronRight } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { overview } from "@/lib/apex/data";
import {
  Card,
  CardHeader,
  PageHeader,
  BigStat,
  StatPod,
  DeltaChip,
  Badge,
  ScoreBar,
  RangeBar,
  SportIcon,
  Eyebrow,
  Empty,
  Sparkline,
  Hairline,
  ApexButton,
} from "@/components/apex/kit";
import { RecoveryScanModal } from "@/components/apex/RecoveryScanModal";
import {
  fmtNum,
  fmtHours,
  fmtDuration,
  fmtClock,
  fmtDistance,
  fmtDelta,
  fmtDate,
  friendlyDiscipline,
} from "@/lib/apex/format";

/** Deterministic sparkline generator (same shape as the Welcome preview). */
function buildSpark(seed: number, count: number): number[] {
  const out: number[] = [];
  let s = seed;
  for (let i = 0; i < count; i++) {
    s = (s * 9301 + 49297) % 233280;
    const r = s / 233280;
    out.push(40 + Math.sin(i / 2) * 18 + r * 12);
  }
  return out;
}

export function OverviewPage() {
  const t = useT();
  const ui = useApexUi();
  const [scanOpen, setScanOpen] = useState(false);

  // Telemetry state — live if any device in integration_status is active.
  const anyLive = overview.integration_status.some((d) => d.status === "active");
  const devicesLabel =
    overview.integration_status.length > 0
      ? overview.integration_status.map((d) => d.provider).join(" · ")
      : t("overview.no_devices");

  // Readiness hero readouts.
  const readinessValue = overview.readiness.value ?? 0;
  const readinessFloor = Math.max(0, readinessValue - 14);
  const readinessCap = Math.min(100, readinessValue + 8);
  const readinessAvg7 = Math.round(readinessValue - (overview.readiness.delta_7d ?? 0) / 2);

  // Sleep stages (last night) — used for the 4 small bars.
  const stages = overview.sleep?.stages;
  const stageDeep = stages?.deep_s ?? 0;
  const stageLight = stages?.light_s ?? 0;
  const stageRem = stages?.rem_s ?? 0;
  const stageAwake = stages?.awake_s ?? 0;
  const stageTotal = stageDeep + stageLight + stageRem + stageAwake || 1;

  // ACWR optimal band: 0.80–1.30 within visible range 0.5–2.0.
  const acwrValue = overview.acwr ?? 0;
  const acwrViewLow = 0.5;
  const acwrViewHigh = 2.0;
  const acwrOptLow = 0.8;
  const acwrOptHigh = 1.3;
  const acwrPos = ((acwrValue - acwrViewLow) / (acwrViewHigh - acwrViewLow)) * 100;
  const acwrOptLeft = ((acwrOptLow - acwrViewLow) / (acwrViewHigh - acwrViewLow)) * 100;
  const acwrOptWidth = ((acwrOptHigh - acwrOptLow) / (acwrViewHigh - acwrViewLow)) * 100;

  // Biomarker trend — synthesized from overview deltas.
  const isAllNormal =
    overview.alerts.every((a) => a.severity !== "alert") &&
    (overview.spo2_avg ?? 0) >= 95 &&
    (overview.resting_hr ?? 0) > 0;

  // Synthesis paragraph from alerts — join messages with semicolons into prose,
  // marking warning severity with the warning tone inline.
  const warningAlerts = overview.alerts.filter((a) => a.severity === "warning");
  const infoAlerts = overview.alerts.filter((a) => a.severity === "info");

  // Sparkline series (14 points each).
  const fitnessSpark = buildSpark(64, 14);
  const hrvSpark = buildSpark(48, 14);

  return (
    <div className="mx-auto max-w-[1240px] px-5 py-6 lg:px-8 lg:py-8">
      <PageHeader
        title={t("overview.title")}
        subtitle={t("welcome.preview_overview")}
        actions={
          <div className="flex items-center gap-2">
            <ApexButton
              variant="ghost"
              size="sm"
              onClick={() => window.print()}
              icon={<Download size={13} />}
            >
              <span className="hidden sm:inline">{t("activities.export")}</span>
            </ApexButton>
            <ApexButton
              variant="secondary"
              size="sm"
              onClick={() => setScanOpen(true)}
              icon={<Sparkles size={13} />}
            >
              Recovery Scan
            </ApexButton>
            <ApexButton
              variant="primary"
              size="sm"
              onClick={() => ui.setView("biometrics")}
              iconRight={<span aria-hidden>→</span>}
            >
              {t("nav.biometrics")}
            </ApexButton>
          </div>
        }
      />
      <RecoveryScanModal open={scanOpen} onOpenChange={setScanOpen} />

      {/* --------------------------- 1. Status strip (full width) */}
      <Card pad={false} className="mt-4 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2 text-[11px]">
          <div className="flex items-center gap-2">
            <span className="relative flex h-1.5 w-1.5">
              {anyLive && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive opacity-60" />
              )}
              <span
                className={`relative inline-flex h-1.5 w-1.5 rounded-full ${
                  anyLive ? "bg-positive" : "bg-faint"
                }`}
              />
            </span>
            <span className="eyebrow !text-[10px]">
              {anyLive ? t("overview.live") : t("overview.paused")}
            </span>
            <span className="text-faint" aria-hidden>·</span>
            <span className="num text-muted">{devicesLabel}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={anyLive ? "positive" : "neutral"} dot>
              {t("overview.validated")}
            </Badge>
            <span className="text-faint" aria-hidden>·</span>
            <span className="num tracking-[0.06em] text-faint">
              {fmtDate(overview.date, ui.locale)} · {t("overview.epoch")}
            </span>
          </div>
        </div>
      </Card>

      {/* --------------------------- Main grid */}
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* ---------------- 2. Readiness hero (8 cols) */}
        <Card className="lg:col-span-8">
          <CardHeader
            eyebrow={t("overview.adaptive_readiness")}
            right={
              <DeltaChip
                delta={overview.readiness.delta_7d}
                goodWhen="up"
                suffix={t("overview.vs7d")}
              />
            }
          />
          <BigStat
            size="xl"
            value={readinessValue}
            unit="/100"
            tone="ink"
          />
          <div className="mt-3">
            <ScoreBar value={readinessValue} tone="primary" height={6} />
          </div>
          <div className="num mt-2 flex justify-between text-[10px] text-faint">
            <span>
              {t("overview.floor")} <span className="text-muted">{readinessFloor}</span>
            </span>
            <span>
              {t("overview.avg7")} <span className="text-muted">{readinessAvg7}</span>
            </span>
            <span>
              {t("overview.cap")} <span className="text-muted">{readinessCap}</span>
            </span>
          </div>

          <Hairline className="my-4" />

          <div className="grid grid-cols-2 gap-3">
            <StatPod
              label={t("overview.system_readiness")}
              value={overview.recovery.value ?? 0}
              unit="/100"
              right={
                <DeltaChip
                  delta={overview.recovery.delta_7d}
                  goodWhen="up"
                  compact
                  suffix={t("overview.vs7d")}
                  showSuffix={false}
                />
              }
            />
            <StatPod
              label={t("overview.sleep_score")}
              value={overview.sleep_score.value ?? 0}
              unit="/100"
              right={
                <DeltaChip
                  delta={overview.sleep_score.delta_7d}
                  goodWhen="up"
                  compact
                  suffix={t("overview.vs7d")}
                  showSuffix={false}
                />
              }
            />
          </div>
        </Card>

        {/* ---------------- 3. Synthesis Diagnosis (4 cols) */}
        <Card className="lg:col-span-4">
          <CardHeader eyebrow={t("overview.synthesis")} />
          <p className="text-[13px] leading-[1.6] text-ink2">
            {infoAlerts.length > 0 ? (
              infoAlerts.map((a, i) => (
                <span key={i}>
                  {i > 0 && " "}
                  {a.message}
                  {i < infoAlerts.length - 1 && "."}
                </span>
              ))
            ) : (
              <span className="text-muted">{t("common.no_data")}</span>
            )}
            {warningAlerts.length > 0 && (
              <span className="mt-2 block rounded-[var(--radius-control)] bg-warningSoft px-2 py-1 text-[12px] font-medium text-warningText">
                {warningAlerts.map((a) => a.message).join(" ")}
              </span>
            )}
          </p>

          <Hairline className="my-3" />

          <div className="eyebrow mb-2">{t("overview.open_alerts")}</div>
          {overview.alerts.length === 0 ? (
            <div className="text-[12px] text-muted">{t("common.no_data")}</div>
          ) : (
            <ul className="flex flex-col gap-2">
              {overview.alerts.map((a, i) => (
                <li key={i} className="flex items-start gap-2">
                  <Badge
                    tone={
                      a.severity === "alert"
                        ? "alert"
                        : a.severity === "warning"
                        ? "warning"
                        : "neutral"
                    }
                    dot
                  >
                    {a.type.toUpperCase()}
                  </Badge>
                  <span className="flex-1 text-[12px] leading-[1.5] text-ink2">
                    {a.message}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* ---------------- 4. ACWR / Load block (8 cols) */}
        <Card className="lg:col-span-8">
          <CardHeader
            eyebrow={t("overview.acwr_title")}
            right={
              <span className="num text-[10px] text-faint">
                {t("overview.optimal_window")}: {fmtNum(acwrOptLow, 2)}–{fmtNum(acwrOptHigh, 2)}
              </span>
            }
          />
          <div className="flex items-baseline gap-3">
            <BigStat value={fmtNum(acwrValue, 2)} unit="ratio" size="lg" tone="ink" />
            <span className="num text-[11px] text-muted">
              {acwrValue >= acwrOptLow && acwrValue <= acwrOptHigh
                ? t("overview.optimal")
                : acwrValue > acwrOptHigh
                ? t("overview.constrained")
                : t("overview.good")}
            </span>
          </div>

          {/* ACWR range bar with optimal band overlay */}
          <div className="num mt-4">
            <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface3">
              {/* Optimal band */}
              <div
                className="absolute inset-y-0 bg-positiveSoft"
                style={{ left: `${acwrOptLeft}%`, width: `${acwrOptWidth}%` }}
              />
              {/* Value marker */}
              <div
                className="absolute top-1/2 h-3.5 w-[3px] -translate-y-1/2 rounded-full bg-primary"
                style={{ left: `${Math.max(0, Math.min(100, acwrPos))}%` }}
              />
            </div>
            <div className="mt-1.5 flex justify-between text-[9px] text-faint">
              <span>0.5</span>
              <span>1.0</span>
              <span>1.5</span>
              <span>2.0</span>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-3">
            <StatPod
              label={t("overview.acute_load")}
              value={fmtNum(overview.acute_load, 0)}
              unit="TSS"
              sub={t("overview.range28")}
            />
            <StatPod
              label={t("overview.chronic_load")}
              value={fmtNum(overview.chronic_load, 0)}
              unit="TSS"
              sub={t("overview.range28")}
            />
            <StatPod
              label={t("overview.fitness")}
              value={fmtNum(overview.training_load_7d, 0)}
              unit="TSS"
              sub={t("overview.avg7")}
              tone="primary"
            />
          </div>

          {/* Fitness ramp sparkline */}
          <div className="mt-4 rounded-[var(--radius-card)] border border-hairline bg-surface2 p-3">
            <div className="flex items-center justify-between">
              <span className="eyebrow">{t("overview.fitness")}</span>
              <span className="num text-[10px] text-faint">{t("overview.range28")}</span>
            </div>
            <div className="mt-2 flex h-8 items-end">
              <Sparkline
                data={fitnessSpark}
                color="var(--c-primary)"
                width={460}
                height={32}
                className="w-full"
              />
            </div>
          </div>

          <div className="mt-3 text-[12px] text-muted">{t("overview.no_overreach")}</div>
        </Card>

        {/* ---------------- 5. Measured Biomarkers (4 cols) */}
        <Card className="lg:col-span-4">
          <CardHeader
            eyebrow={t("overview.biomarkers")}
            right={
              isAllNormal ? (
                <Badge tone="positive" dot>
                  {t("overview.all_normal")}
                </Badge>
              ) : null
            }
          />
          <div className="flex flex-col gap-2">
            <StatPod
              label={t("overview.resting_hr")}
              value={fmtNum(overview.resting_hr, 0)}
              unit="bpm"
              right={
                <DeltaChip
                  delta={overview.resting_hr_delta_7d}
                  goodWhen="down"
                  compact
                  unit="bpm"
                  suffix={t("overview.vs7d")}
                  showSuffix={false}
                />
              }
            />
            <StatPod
              label={t("overview.spo2")}
              value={fmtNum(overview.spo2_avg, 1)}
              unit="%"
              right={
                <DeltaChip
                  delta={overview.spo2_delta_7d}
                  goodWhen="up"
                  compact
                  unit="%"
                  suffix={t("overview.vs7d")}
                  showSuffix={false}
                />
              }
            />
            <StatPod
              label={t("overview.respiration")}
              value={fmtNum(overview.respiration_avg, 1)}
              unit="brpm"
            />
            <StatPod
              label={t("overview.hrv_ms")}
              value={fmtNum(overview.hrv_ms, 0)}
              unit="ms"
              right={
                <DeltaChip
                  delta={(overview.hrv_ms ?? 0) - (overview.hrv_baseline_ms ?? 0)}
                  goodWhen="up"
                  compact
                  unit="ms"
                  suffix={t("overview.vs_baseline")}
                  showSuffix={false}
                />
              }
              sub={`${t("overview.baseline7")}: ${fmtNum(overview.hrv_baseline_ms, 0)} ms`}
            />
            <StatPod
              label={t("overview.skin_temp")}
              value={fmtNum(0.1, 1)}
              unit="°C"
              sub={`${t("overview.vs_avg")}`}
            />
          </div>
        </Card>

        {/* ---------------- 6. Calibrated Activities (4 cols) */}
        <Card className="lg:col-span-4">
          <CardHeader eyebrow={t("overview.calibrated")} />
          {overview.activities.length === 0 ? (
            <Empty title={t("overview.no_activities")} />
          ) : (
            <ul className="flex flex-col gap-2">
              {overview.activities.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => {
                      ui.selectActivity(a.id);
                      ui.setView("activity-detail");
                    }}
                    className="group flex w-full items-start gap-2.5 rounded-[var(--radius-card)] border border-hairline bg-surface2 p-2.5 text-left transition-colors hover:border-hairline2"
                  >
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-surface3 text-muted transition-colors group-hover:bg-primarySoft group-hover:text-primaryText">
                      <SportIcon discipline={a.discipline} size={14} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div
                        className="text-[12px] font-semibold leading-tight text-ink"
                        style={{
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {a.title}
                      </div>
                      <div className="num mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted">
                        <span>{friendlyDiscipline(a.discipline, ui.locale)}</span>
                        <span aria-hidden className="text-faint">·</span>
                        <span>{fmtClock(a.start_time, ui.locale)}</span>
                        <span aria-hidden className="text-faint">·</span>
                        <span>{fmtDuration(a.duration_s)}</span>
                        {a.distance_m !== null && (
                          <>
                            <span aria-hidden className="text-faint">·</span>
                            <span>{fmtDistance(a.distance_m, "metric", 1)} km</span>
                          </>
                        )}
                        {a.training_load !== null && (
                          <>
                            <span aria-hidden className="text-faint">·</span>
                            <span className="font-semibold text-primaryText">
                              {a.training_load} TSS
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <ChevronRight
                      size={12}
                      className="mt-1 shrink-0 text-faint transition-colors group-hover:text-ink"
                    />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* ---------------- 7. Last Night (4 cols) */}
        <Card className="lg:col-span-4">
          <CardHeader
            eyebrow={t("overview.last_night")}
            right={
              overview.sleep ? (
                <DeltaChip
                  delta={overview.sleep_score.delta_7d}
                  goodWhen="up"
                  compact
                  suffix={t("overview.vs7d")}
                  showSuffix={false}
                />
              ) : null
            }
          />
          {overview.sleep ? (
            <button
              type="button"
              onClick={() => {
                ui.selectSleepDate(overview.date);
                ui.setView("sleep-night");
              }}
              className="group block w-full text-left"
            >
              {/* Sleep score hero + total hours as secondary */}
              <div className="flex items-end justify-between gap-3">
                <div>
                  <div className="eyebrow !text-[9px]">{t("overview.sleep_score")}</div>
                  <BigStat
                    size="xl"
                    value={fmtNum(overview.sleep?.sleep_score ?? 0, 0)}
                    unit="/100"
                    tone={
                      (overview.sleep?.sleep_score ?? 0) >= 85
                        ? "positive"
                        : (overview.sleep?.sleep_score ?? 0) >= 70
                        ? "ink"
                        : "warning"
                    }
                  />
                </div>
                <div className="text-right">
                  <div className="eyebrow !text-[9px]">{t("sleep.total")}</div>
                  <div className="num text-[20px] font-bold text-ink">
                    {fmtHours((overview.sleep_hours ?? 0) * 3600)}
                  </div>
                </div>
              </div>

              {/* 4 small stage bars */}
              <div className="mt-3 flex flex-col gap-1.5">
                <StageRow
                  label={t("overview.deep")}
                  seconds={stageDeep}
                  total={stageTotal}
                  color="var(--c-stage-deep)"
                />
                <StageRow
                  label={t("overview.rem")}
                  seconds={stageRem}
                  total={stageTotal}
                  color="var(--c-stage-rem)"
                />
                <StageRow
                  label={t("overview.light")}
                  seconds={stageLight}
                  total={stageTotal}
                  color="var(--c-stage-core)"
                />
                <StageRow
                  label={t("overview.awake")}
                  seconds={stageAwake}
                  total={stageTotal}
                  color="var(--c-stage-awake)"
                />
              </div>

              <Hairline className="my-3" />

              <div className="num flex items-center justify-between text-[11px] text-muted">
                <span>
                  {t("sleep.bedtime")} {fmtClock(overview.sleep?.start_time, ui.locale)}
                </span>
                <span aria-hidden className="text-faint">→</span>
                <span>
                  {t("sleep.wake")} {fmtClock(overview.sleep?.end_time, ui.locale)}
                </span>
              </div>
            </button>
          ) : (
            <Empty title={t("sleep.empty")} />
          )}
        </Card>

        {/* ---------------- 8. Parasympathetic Tone (4 cols) */}
        <Card className="lg:col-span-4">
          <CardHeader eyebrow={t("overview.parasympathetic")} />
          <BigStat
            value={fmtNum(overview.hrv_ms, 0)}
            unit="ms"
            size="lg"
            tone="ink"
          />
          <div className="mt-3 flex h-8 items-end">
            <Sparkline
              data={hrvSpark}
              color="var(--c-positive)"
              width={460}
              height={32}
              className="w-full"
            />
          </div>

          <Hairline className="my-3" />

          {/* Parasympathetic sub-stats — stack vertically to avoid eyebrow truncation */}
          <div className="flex flex-col gap-2">
            <ParasympRow
              label={t("overview.overnight_peak")}
              value={fmtNum(Math.round((overview.hrv_ms ?? 0) * 1.15), 0)}
              unit="ms"
              tone="positive"
              hint={`+${fmtNum(Math.round((overview.hrv_ms ?? 0) * 1.15 - (overview.hrv_baseline_ms ?? 0)), 0)} ms ${t("overview.vs_baseline")}`}
            />
            <ParasympRow
              label={t("overview.baseline7")}
              value={fmtNum(overview.hrv_baseline_ms, 0)}
              unit="ms"
              tone="muted"
              hint={`${t("overview.rolling")} 7d`}
            />
            <ParasympRow
              label={t("overview.norm30")}
              value={fmtNum(overview.hrv_norm_30d, 0)}
              unit="ms"
              tone="muted"
              hint={`${t("overview.avg7")} 30d`}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}

/** A single sleep-stage row — small horizontal bar + label + duration. */
function StageRow({
  label,
  seconds,
  total,
  color,
}: {
  label: string;
  seconds: number;
  total: number;
  color: string;
}) {
  const pct = total > 0 ? (seconds / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="num w-12 shrink-0 text-[10px] text-muted">{label}</span>
      <div className="num h-1.5 flex-1 overflow-hidden rounded-full bg-surface3" title={`${label}: ${fmtHours(seconds)}`}>
        <div
          style={{ width: `${pct}%`, background: color, height: "100%", transition: "width 600ms cubic-bezier(0.16,1,0.3,1)" }}
        />
      </div>
      <span className="num w-12 shrink-0 text-right text-[10px] text-muted">
        {fmtHours(seconds)}
      </span>
    </div>
  );
}

/** Parasympathetic row — label on left, value on right, hint below. */
function ParasympRow({
  label,
  value,
  unit,
  tone,
  hint,
}: {
  label: string;
  value: string;
  unit: string;
  tone: "positive" | "muted" | "primary";
  hint?: string;
}) {
  const valTone = {
    positive: "text-positiveText",
    muted: "text-ink",
    primary: "text-primaryText",
  }[tone];
  const dot = {
    positive: "bg-positive",
    muted: "bg-hairline2",
    primary: "bg-primary",
  }[tone];
  return (
    <div className="flex items-start justify-between gap-3 rounded-[var(--radius-card)] border border-hairline bg-surface2 px-3 py-2">
      <div className="flex min-w-0 flex-1 items-start gap-2">
        <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
        <div className="min-w-0 flex-1">
          <div className="eyebrow !text-[10px] break-words leading-tight">{label}</div>
          {hint && <div className="num mt-0.5 text-[9px] text-faint">{hint}</div>}
        </div>
      </div>
      <div className={`num flex shrink-0 items-baseline gap-0.5 text-[18px] font-bold ${valTone}`}>
        {value}
        <span className="text-[10px] font-medium text-muted">{unit}</span>
      </div>
    </div>
  );
}
