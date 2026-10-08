import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../app/api";
import { Card, CardHeader, ErrorNote, Loading, fmtDuration } from "../../components/kit";

interface Calendar {
  weekly_streak: number; week_active_days: number;
  days: { date: string; count: number; duration_s: number; intensity: number; future: boolean }[];
}
export function ActivityCalendar({ date }: { date: string }) {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ["activity-calendar", date], queryFn: () => api.get<Calendar>(`/dashboard/activity-calendar?end=${date}`) });
  return <Card>
    <CardHeader title={t("completion.activity_year")} right={query.data && <span className="text-[13px]">{t("completion.weekly_streak", { count: query.data.weekly_streak })}</span>} />
    {query.isLoading ? <Loading /> : query.isError ? <ErrorNote /> : query.data && <>
      <p className="mb-4 text-[13px] text-muted">{t(query.data.week_active_days ? "completion.week_complete" : "completion.week_pending")}</p>
      <div className="overflow-x-auto pb-2">
        <div className="grid min-w-[680px] grid-flow-col gap-[3px]" style={{ gridTemplateRows: "repeat(7, 12px)", gridTemplateColumns: "repeat(52, minmax(10px, 1fr))" }} role="group" aria-label={t("completion.activity_year")}>
          {query.data.days.map(day => {
            const label = `${day.date} · ${t("completion.sessions", { count: day.count })} · ${fmtDuration(day.duration_s)}`;
            return day.future ? <span key={day.date} className="border border-hairline opacity-30" aria-hidden="true" /> : <Link key={day.date} to={`/app/activities?date=${day.date}`} aria-label={label} title={label}
              className="block rounded-[2px] border border-hairline focus:outline focus:outline-2 focus:outline-ink"
              style={{ background: day.count ? `color-mix(in srgb, var(--c-primary) ${Math.round(25 + 75 * day.intensity)}%, var(--c-surface-2))` : "var(--c-surface-2)" }} />;
          })}
        </div>
      </div>
      <p className="mt-3 text-[12px] text-muted">{t("completion.intensity_note")}</p>
    </>}
  </Card>;
}
