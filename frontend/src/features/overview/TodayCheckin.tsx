import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAppCheckin } from "../../app/useAppCheckin";
import { useUi } from "../../app/stores/ui";
import { Card } from "../../components/kit";
import { localDay } from "../../components/data";

export function TodayCheckin() {
  const { t, i18n } = useTranslation();
  const me = useUi(s => s.me);
  const { data, isFetching, isError } = useAppCheckin(me?.user_id);
  const current = data?.date === localDay(me?.timezone) ? data : undefined;
  return <section data-testid="today-checkin" aria-label={t("todayCheckin.title")}><Card>
    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h2 className="focus-kicker">{t("todayCheckin.title")}</h2>
      {current?.generated_at && <span className="text-[12px] text-muted">{t("todayCheckin." + current.slot)} · {new Date(current.generated_at).toLocaleTimeString(i18n.language, { timeZone: me?.timezone, hour: "2-digit", minute: "2-digit" })}</span>}
    </div>
    {current?.status === "ready" && current.lines.length ? <p className="line-clamp-3 whitespace-pre-line text-[14px] leading-6" data-testid="checkin-lines">{current.lines.slice(0, 3).join("\n")}</p>
      : <p className="text-[13px] text-muted">{t(isFetching ? "todayCheckin.loading" : isError ? "todayCheckin.unavailable" : "todayCheckin." + (current?.status ?? "unavailable"))}{current?.status === "ai_disabled" && <> <Link className="text-link" to="/app/settings?tab=profile">{t("todayCheckin.preferences")} →</Link></>}</p>}
  </Card></section>;
}
