import { useTranslation } from "react-i18next";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import type { MetricTrend } from "../app/api";
import { fmtNum } from "./kit";

/** A personal observed band, never a population or clinical threshold. */
export function PersonalRange({ trend, compact = false }: { trend: MetricTrend; compact?: boolean }) {
  const { t } = useTranslation();
  const ref = trend.reference_range;
  const latest = [...trend.points].reverse().find((p) => p.value != null);
  if (!latest || latest.value == null) return null;
  if (!ref || ref.state !== "available" || !ref.empirical_range) {
    return <span className="text-[12px] text-muted">{t("metricView.range_warming", { count: ref?.sample_count ?? 0, required: ref?.required_samples ?? 14 })}</span>;
  }
  const [low, high] = ref.empirical_range;
  if (![low, high, latest.value].every(Number.isFinite) || high < low) return null;
  const state = latest.value < low ? "below" : latest.value > high ? "above" : "within";
  const tone = state === "within" ? "text-positiveText" : "text-warningText";
  const position = state === "below" ? 16 : state === "above" ? 84 : high === low ? 50 : 34 + (latest.value - low) / (high - low) * 32;
  const label = t("metricView.range_" + state);
  return <div className={compact ? "w-full max-w-44" : "max-w-sm"}>
    <div className={`mb-2 text-[12px] ${tone}`}>{label}</div>
    <div role="img" aria-label={`${label} · ${fmtNum(low, 1)}–${fmtNum(high, 1)} ${trend.unit}`} className="relative flex h-1.5 gap-0.5">
      <span className="flex-1 bg-warningText/25" />
      <span className="flex-1 bg-positiveText/35" />
      <span className="flex-1 bg-warningText/25" />
      <span className={`absolute -top-1 h-3.5 w-0.5 ${state === "within" ? "bg-positiveText" : "bg-warningText"}`} style={{ left: `${position}%` }} />
    </div>
    {!compact && <>
      <div className="mt-3 flex justify-between text-[11px] text-muted"><span>{t("metricView.below")}</span><span>{t("metricView.personal_range")}</span><span>{t("metricView.above")}</span></div>
      <p className="mt-2 text-[12px] text-muted">{t("metricView.range_note", { low: fmtNum(low, 1), high: fmtNum(high, 1), unit: trend.unit, count: ref.sample_count })}</p>
    </>}
  </div>;
}

/** Arrows communicate a recorded change; only supported directions get color. */
export function MetricDirection({ metric, points }: { metric: string; points: MetricTrend["points"] }) {
  const { t } = useTranslation();
  const values = points.filter((p): p is { date: string; value: number } => p.value != null && Number.isFinite(p.value));
  if (values.length < 2) return null;
  const delta = values.at(-1)!.value - values.at(-2)!.value;
  const state = delta > 0 ? "up" : delta < 0 ? "down" : "steady";
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
  // Weight, HRV, oxygen, sleep stages and heuristic scores are not "more is better".
  const tone = metric === "vo2max" && delta !== 0 ? delta > 0 ? "text-positiveText" : "text-warningText" : "text-muted";
  return <span className={`inline-flex items-center gap-1 text-[12px] ${tone}`}><Icon size={13} aria-hidden="true" />{t("metricView." + state)}</span>;
}
