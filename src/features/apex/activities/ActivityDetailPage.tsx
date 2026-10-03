"use client";

import { useEffect, useState } from "react";
import { useI18n, useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex/store";
import { Card, PageHeader, SportIcon, Empty, Loading, SourcePill, BackLink, ApexButton } from "@/components/apex/kit";
import { fmtClock, fmtDateLong, fmtDistance, fmtDuration, fmtElevation, fmtSpeed, friendlyDiscipline } from "@/lib/apex/format";
import type { ActivityDetail } from "@/lib/apex/types";

/** Selected recorded summary. Unavailable recordings are never replaced with fixtures. */
export function ActivityDetailPage() {
  const t = useT();
  const { locale } = useI18n();
  const ui = useApexUi();
  const id = ui.selectedActivityId;
  const [result, setResult] = useState<{ id: string; detail?: ActivityDetail; error?: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const it = locale === "it";

  useEffect(() => {
    if (id === null) return;
    const controller = new AbortController();
    fetch(`/api/activities/${encodeURIComponent(id)}`, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok || !body.ok) throw new Error(body.error || "Could not load activity");
        if (!controller.signal.aborted) setResult({ id, detail: body.activity });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setResult({ id, error: error instanceof Error ? error.message : "Could not load activity" });
      });
    return () => controller.abort();
  }, [id, attempt]);

  const current = result?.id === id ? result : null;
  const detail = current?.detail;
  const units = ui.units;
  const distanceUnit = units === "imperial" ? "mi" : "km";
  const metrics = detail ? [
    { label: t("activities.distance"), value: fmtDistance(detail.distance_m, units), unit: distanceUnit },
    { label: t("activities.duration"), value: fmtDuration(detail.duration_s) },
    { label: t("activities.elevation"), value: fmtElevation(detail.elevation_gain_m, units), unit: units === "imperial" ? "ft" : "m" },
    { label: t("activities.avg_power"), value: detail.avg_power, unit: "W" },
    { label: t("activities.avg_hr"), value: detail.avg_hr, unit: "bpm" },
    { label: t("activities.max_hr"), value: detail.max_hr, unit: "bpm" },
    { label: it ? "Velocità media" : "Average speed", value: fmtSpeed(detail.avg_speed_mps, units), unit: units === "imperial" ? "mph" : "km/h" },
    { label: it ? "Calorie" : "Calories", value: detail.calories, unit: "kcal" },
    { label: t("activities.col_load"), value: detail.training_load },
  ] : [];

  return (
    <div className="mx-auto max-w-[1240px]">
      <BackLink onClick={() => ui.setView("activities")}>{t("activities.back_to_list")}</BackLink>
      {id === null ? <Empty title={it ? "Seleziona un’attività" : "Select an activity"} />
        : !current ? <Loading />
        : current.error ? (
          <Card className="mt-6">
            <div role="alert"><Empty title={current.error} /></div>
            <ApexButton variant="secondary" onClick={() => { setResult(null); setAttempt((n) => n + 1); }}>
              {it ? "Riprova" : "Retry"}
            </ApexButton>
          </Card>
        ) : detail ? <>
          <PageHeader className="mt-3" title={detail.title}
            subtitle={`${fmtDateLong(detail.start_time, locale)} · ${fmtClock(detail.start_time, locale)} · ${friendlyDiscipline(detail.discipline, locale)}`}
            actions={<span className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-control)] bg-primarySoft text-primaryText"><SportIcon discipline={detail.discipline} size={18} /></span>} />
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
            {metrics.map((metric) => (
              <div key={metric.label} className="border-b border-hairline pb-4">
                <div className="text-[14px] text-ink2">{metric.label}</div>
                <div className="num mt-1 flex items-baseline gap-1.5 text-ink">
                  <span className="text-[28px] font-semibold">{metric.value ?? "—"}</span>
                  {metric.value != null && metric.value !== "—" && metric.unit && <span className="text-[14px] text-muted">{metric.unit}</span>}
                </div>
              </div>
            ))}
          </div>
          <Card className="mt-6">
            <div className="text-[14px] font-medium text-ink2">{t("activities.sources")}</div>
            <div className="mt-3 flex flex-wrap gap-2">{detail.sources.map((source) => <SourcePill key={source}>{source}</SourcePill>)}</div>
            <p className="mt-3 text-[13px] text-muted">{it ? "Riepilogo registrato. La completezza del riepilogo non indica la disponibilità di GPS o serie temporali." : "Recorded summary. Summary completeness does not indicate GPS or time-series availability."}</p>
          </Card>
          <Card className="mt-4">
            <Empty title={it ? "Registrazioni dettagliate non disponibili" : "Detailed recordings unavailable"}
              body={it ? "GPS, serie temporali, zone cardiache, giri, meteo e attrezzatura non sono stati importati per questa attività." : "GPS, time-series, heart-rate zones, laps, weather and gear have not been imported for this activity."} />
          </Card>
        </> : null}
    </div>
  );
}
