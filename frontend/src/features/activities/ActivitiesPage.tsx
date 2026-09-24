/**
 * Activities list — the telemetry log (mockup: "Calibrated Activities").
 * Sport icons, friendly discipline names, source chips, headline stats
 * strip and range filter. Cards surface distance/HR/load/cals like the
 * approved overview pod, at log density.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { api, type ActivityListItem } from "../../app/api";
import {
  Badge,
  Card,
  Empty,
  ErrorNote,
  Loading,
  PageHeader,
  Segmented,
  SportIcon,
  StatPod,
  fmtDuration,
  fmtHours,
  fmtNum,
  friendlyDiscipline,
} from "../../components/kit";

type Range = "30d" | "90d" | "12m";

function rangeStart(r: Range): string {
  const d = new Date();
  if (r === "30d") d.setDate(d.getDate() - 30);
  else if (r === "90d") d.setDate(d.getDate() - 90);
  else d.setMonth(d.getMonth() - 12);
  return d.toISOString().slice(0, 10);
}

export default function ActivitiesPage() {
  const { t } = useTranslation();
  const [range, setRange] = useState<Range>("90d");
  const [disc, setDisc] = useState<string>("all");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["activities", range],
    queryFn: () =>
      api.get<{ items: ActivityListItem[]; total: number }>(
        `/activities?limit=100&start=${rangeStart(range)}`,
      ),
  });

  const items = data?.items ?? [];
  const disciplines = useMemo(() => {
    const set = new Map<string, number>();
    for (const a of items) if (a.discipline) set.set(a.discipline, (set.get(a.discipline) ?? 0) + 1);
    return [...set.entries()].sort((a, b) => b[1] - a[1]);
  }, [items]);
  const filtered = disc === "all" ? items : items.filter((a) => a.discipline === disc);

  const totalTime = items.reduce((acc, a) => acc + a.duration_s, 0);
  const totalKm = items.reduce((acc, a) => acc + (a.distance_m ?? 0), 0) / 1000;
  const totalLoad = items.reduce((acc, a) => acc + (a.training_load ?? 0), 0);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("activities.title")}
        subtitle={t("activities.subtitle")}
        actions={
          <Segmented
            value={range}
            onChange={setRange}
            options={[
              { value: "30d", label: t("activities.30d") },
              { value: "90d", label: t("activities.90d") },
              { value: "12m", label: t("activities.12m") },
            ]}
          />
        }
      />

      {isLoading && <Loading />}
      {isError && <ErrorNote />}

      {items.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatPod label={t("activities.sessions")} value={String(data?.total ?? items.length)} sub={t("activities.in_range")} />
            <StatPod label={t("activities.time_total")} value={fmtHours(totalTime)} />
            <StatPod label={t("activities.distance_total")} value={`${fmtNum(totalKm, 0)}`} unit="km" />
            <StatPod label={t("activities.load_total")} value={fmtNum(totalLoad, 0)} unit="TSS" tone="positive" />
          </div>

          {disciplines.length > 1 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <FilterChip active={disc === "all"} onClick={() => setDisc("all")} label={`${t("activities.all")} (${items.length})`} />
              {disciplines.map(([dname, count]) => (
                <FilterChip
                  key={dname}
                  active={disc === dname}
                  onClick={() => setDisc(dname)}
                  label={`${friendlyDiscipline(dname, t)} (${count})`}
                />
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((a) => (
              <Link key={a.id} to={`/app/activities/${a.id}`} className="group">
                <Card className="h-full transition-colors group-hover:bg-surface2" pad={false}>
                  <div className="p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-control bg-primarySoft text-primaryText">
                          <SportIcon discipline={a.discipline} size={14} />
                        </span>
                        <div className="min-w-0">
                          <div className="truncate text-[13px] font-semibold text-ink">
                            {friendlyDiscipline(a.discipline, t)}
                          </div>
                          <div className="num truncate text-[10px] text-faint">
                            {new Date(a.start_time).toLocaleDateString(undefined, {
                              weekday: "short",
                              day: "numeric",
                              month: "short",
                            })}{" "}
                            ·{" "}
                            {new Date(a.start_time).toLocaleTimeString(undefined, {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </div>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {a.sources.map((s) => (
                          <Badge key={s} tone="neutral">{s.toUpperCase()}</Badge>
                        ))}
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-4 gap-2 border-t border-hairline pt-3">
                      <Mini label={t("activities.distance")} value={fmtNum(a.distance_m ? a.distance_m / 1000 : null, 1)} unit="km" />
                      <Mini label={t("activities.avg_hr")} value={fmtNum(a.avg_hr)} unit="bpm" />
                      <Mini label={t("activities.avg_power")} value={fmtNum(a.avg_power, 0)} unit="W" />
                      <Mini label={t("activities.tss")} value={fmtNum(a.training_load, 0)} unit="" accent />
                    </div>
                    <div className="mt-2.5 flex items-center justify-between">
                      <span className="num text-[11px] font-semibold text-ink2">{fmtDuration(a.duration_s)}</span>
                      <ArrowRight size={12} className="text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-primaryText" />
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </>
      )}

      {data && items.length === 0 && (
        <Card>
          <Empty>{t("activities.empty")}</Empty>
        </Card>
      )}
    </div>
  );
}

function FilterChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-control border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        active
          ? "border-hairline bg-surface2 text-ink"
          : "border-transparent bg-surface text-muted hover:text-ink2"
      }`}
    >
      {label}
    </button>
  );
}

function Mini({ label, value, unit, accent = false }: { label: string; value: string; unit?: string; accent?: boolean }) {
  return (
    <div>
      <div className="eyebrow truncate">{label}</div>
      <div className={`num mt-0.5 text-[13px] font-semibold ${accent ? "text-positiveText" : "text-ink"}`}>
        {value}
        {unit && <span className="ml-0.5 text-[9px] font-normal text-muted">{unit}</span>}
      </div>
    </div>
  );
}
