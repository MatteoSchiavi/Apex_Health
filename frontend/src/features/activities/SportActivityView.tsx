import { useTranslation } from "react-i18next";
import type { ActivityDetail } from "../../app/api";
import { Card, CardHeader, StatPod, fmtDuration, fmtNum } from "../../components/kit";
import { useUnits } from "../../components/data";

export function sportKind(a: ActivityDetail) {
  if (a.presentation) return a.presentation.kind;
  if (["strength", "gym_general"].includes(a.discipline ?? "")) return "strength";
  if (a.discipline === "running") return "running";
  if (["road_cycling", "mountain_biking", "gravel_cycling"].includes(a.discipline ?? "")) return "cycling";
  if (a.discipline === "sailing") return "sailing";
  if (["skiing", "snowboard"].includes(a.discipline ?? "")) return "skiing";
  if (a.discipline === "hiit") return "hiit";
  return "other";
}

export function paceText(minutes: number | null) {
  if (minutes == null || !Number.isFinite(minutes) || minutes <= 0) return "—";
  const seconds = Math.round(minutes * 60);
  return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}

export function useSportUnits(kind: string) {
  const units = useUnits();
  const sailing = kind === "sailing";
  const metres = units.distanceUnit === "mi" ? 1609.344 : 1000;
  return {
    ...units,
    distance: (m: number | null | undefined) => m == null ? null : sailing ? m / 1852 : units.distance(m),
    distanceUnit: sailing ? "nm" : units.distanceUnit,
    speed: (mps: number | null | undefined) => mps == null ? null : sailing ? mps * 3600 / 1852 : units.speed(mps * 3.6),
    speedUnit: sailing ? "kn" : units.speedUnit,
    pace: (mps: number | null | undefined) => mps == null || mps <= 0 ? null : metres / mps / 60,
    paceUnit: "min/" + units.distanceUnit,
  };
}

export function SportMetrics({ activity: a }: { activity: ActivityDetail }) {
  const { t } = useTranslation();
  const kind = sportKind(a);
  const units = useSportUnits(kind);
  const p = a.presentation;
  const average = p?.avg_speed_m_s ?? (a.distance_m != null && a.duration_s > 0 ? a.distance_m / a.duration_s : null);
  const movement = !["strength", "hiit"].includes(kind);
  const water = ["sailing", "kitesurf", "windsurf", "surf", "wakeboard"].includes(a.discipline ?? "");
  return <Card>
    <CardHeader title={t("design.session_metrics")} />
    <div className="grid grid-cols-2 gap-x-6">
      {movement && !water && <StatPod label={t("activities.elevation")} value={fmtNum(units.elevation(a.elevation_gain_m))} unit={units.elevationUnit} />}
      <StatPod label={t("activities.max_hr")} value={fmtNum(a.max_hr)} unit="bpm" />
      {kind === "running" && <StatPod label={t("sportView.pace")} value={paceText(units.pace(average))} unit={units.paceUnit} />}
      {kind === "running" && p?.avg_cadence != null && <StatPod label={t("activities.cadence")} value={fmtNum(p.avg_cadence)} unit="spm" />}
      {movement && kind !== "running" && <StatPod label={t("activities.speed")} value={fmtNum(units.speed(average), 1)} unit={units.speedUnit} />}
      {(kind === "skiing" || kind === "sailing") && <StatPod label={t("sportView.max_speed")} value={fmtNum(units.speed(p?.max_speed_m_s), 1)} unit={units.speedUnit} />}
      {kind === "skiing" && <StatPod label={t("sportView.slopes")} value={fmtNum(p?.slope_count)} />}
      {kind === "cycling" && <>
        <StatPod label={t("activities.avg_power")} value={fmtNum(a.avg_power)} unit="W" />
        <StatPod label={t("activities.np")} value={fmtNum(a.np_power)} unit="W" />
        <StatPod label={t("activities.cadence")} value={fmtNum(p?.avg_cadence)} unit="rpm" />
      </>}
      <StatPod label={t("activities.calories")} value={fmtNum(a.calories)} unit="kcal" />
    </div>
    {!!a.gear.length && <p className="mt-5 border-t border-hairline pt-4 text-[13px] text-muted">{t("activities.gear")}: {a.gear.map(g => g.name).join(", ")}</p>}
  </Card>;
}

export function RecordedZones({ activity }: { activity: ActivityDetail }) {
  const { t } = useTranslation();
  const zones = activity.presentation?.zones ?? [];
  if (!zones.length) return null;
  return <Card>
    <CardHeader title={t("sportView.zones")} />
    <dl>{zones.map((zone, i) => <div key={i} className="flex justify-between gap-4 border-t border-hairline py-3 text-[13px]">
      <dt>{t("sportView.zone_metric_" + zone.metric)} · {zone.name}
        {(zone.lower != null || zone.upper != null) && <span className="ml-2 text-muted">{fmtNum(zone.lower)}–{fmtNum(zone.upper)} {zone.metric === "hr" ? "bpm" : "W"}</span>}
      </dt><dd className="num">{fmtDuration(zone.duration_s)}</dd>
    </div>)}</dl>
  </Card>;
}
