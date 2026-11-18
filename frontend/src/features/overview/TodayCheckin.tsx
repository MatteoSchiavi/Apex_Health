import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../app/api";
import type { AppCheckin } from "../../app/useAppCheckin";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAppCheckin } from "../../app/useAppCheckin";
import { useUi } from "../../app/stores/ui";
import { Button, Card } from "../../components/kit";
import { localDay } from "../../components/data";

export function TodayCheckin() {
  const { t, i18n } = useTranslation();
  const me = useUi(s => s.me);
  const { data, isFetching, isError } = useAppCheckin(me?.user_id);
  const qc = useQueryClient();
  const refresh = useMutation({
    mutationFn: (_userId: number) => api.get<AppCheckin>("/dashboard/check-in"),
    onSuccess: (next, userId) => {
      if (useUi.getState().me?.user_id === userId) qc.setQueryData(["today-checkin", userId], next);
    },
  });
  const current = data?.date === localDay(me?.timezone) ? data : undefined;
  const reasons = ["ai_disabled", "not_generated", "pending", "interrupted", "configuration", "provider_configuration", "provider_auth", "provider_request", "provider_rate_limit", "provider_timeout", "provider", "internal", "budget", "consent", "grounding", "output_limit", "updated"];
  const reason = reasons.includes(current?.reason ?? "") ? current!.reason! : "provider";
  const label = ["ai_disabled", "pending", "budget", "not_generated"].includes(reason) ? "recorded_"+reason : "recorded";
  return <section data-testid="today-checkin" aria-label={t("todayCheckin.title")}><Card>
    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h2 className="focus-kicker">{t("todayCheckin.title")}</h2>
      {current?.mode === "recorded" && current.lines.length > 0 && <span className="text-[12px] text-muted">{t("todayCheckin."+label)}</span>}
      {current?.mode !== "recorded" && current?.status === "ready" && current?.generated_at && <span className="text-[12px] text-muted">{t("todayCheckin." + current.slot)} · {new Date(current.generated_at).toLocaleTimeString(i18n.language, { timeZone: me?.timezone, hour: "2-digit", minute: "2-digit" })}</span>}
    </div>
    {current?.lines.length ? <div className="text-[14px] leading-6" data-testid="checkin-lines">{current.lines.slice(0, 3).map((line, index) => <p key={index} className="truncate" title={line}>{line}</p>)}</div>
      : <p className="text-[13px] text-muted">{t(isFetching ? "todayCheckin.loading" : isError ? "todayCheckin.unavailable" : "todayCheckin." + (current?.status ?? "unavailable"))}{current?.status === "ai_disabled" && <> <Link className="text-link" to="/app/settings?tab=profile">{t("todayCheckin.preferences")} →</Link></>}</p>}
    {current?.mode === "recorded" && current.lines.length > 0 && <details className="mt-3 text-[12px] text-muted">
      <summary className="min-h-6 cursor-pointer">{t("todayCheckin.why_recorded")}</summary>
      <p className="mt-2">{t("todayCheckin.reasons."+reason)}</p>
      {current.attempted_at && <p className="mt-2">{t("todayCheckin.attempted", {time:new Date(current.attempted_at).toLocaleString(i18n.language,{timeZone:me?.timezone})})}</p>}
      {current.detail && <p className="mt-2">{t("todayCheckin.diagnostic",{code:current.detail})}</p>}
      <p className="mt-2">{t("todayCheckin.saved_only")}</p>
      <Button className="mt-2" variant="ghost" disabled={refresh.isPending || me?.user_id == null} onClick={() => {if(me) refresh.mutate(me.user_id);}}>{t("todayCheckin.check_saved")}</Button>
      {refresh.isError && <p role="status" className="mt-2">{t("todayCheckin.read_error")}</p>}
    </details>}
  </Card></section>;
}
