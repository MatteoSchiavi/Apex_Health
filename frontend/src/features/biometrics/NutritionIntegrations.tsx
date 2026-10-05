import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { localDay } from "../../components/data";
import { Button, Card, CardHeader, Empty, ErrorNote, Loading, fmtNum } from "../../components/kit";

interface FitbitStatus {
  configured: boolean;
  connected: boolean;
  provider: "fitbit";
}
interface FitbitDay {
  date: string;
  summary: Record<"calories" | "carbs" | "fat" | "fiber" | "protein" | "sodium" | "water", number | null>;
  foods: { name: string | null; amount: number | null; unit: string | null; calories: number | null }[];
}

export function NutritionIntegrations() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useUi((s) => s.me?.user_id);
  const timezone = useUi((s) => s.me?.timezone);
  const [day, setDay] = useState(() => localDay(timezone));
  const status = useQuery({
    queryKey: ["fitbit-nutrition-status", uid],
    queryFn: () => api.get<FitbitStatus>("/nutrition/fitbit/status"),
  });
  const diary = useQuery({
    queryKey: ["fitbit-nutrition-day", uid, day],
    queryFn: () => api.get<FitbitDay>(`/nutrition/fitbit/day/${day}`),
    enabled: status.data?.connected === true && /^\d{4}-\d{2}-\d{2}$/.test(day),
  });
  const connect = useMutation({
    mutationFn: async () => {
      const { authorize_url } = await api.post<{ authorize_url: string }>("/nutrition/fitbit/authorize");
      const url = new URL(authorize_url);
      if (url.origin !== "https://www.fitbit.com") throw new Error("Unexpected Fitbit authorization URL");
      return url.href;
    },
    onSuccess: (url) => window.location.assign(url),
  });
  const disconnect = useMutation({
    mutationFn: () => api.delete("/nutrition/fitbit"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fitbit-nutrition-status", uid] });
      qc.removeQueries({ queryKey: ["fitbit-nutrition-day", uid] });
    },
  });

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader title={t("nutrition.fitbit_title")} />
        <p className="text-[13px] text-muted">{t("nutrition.fitbit_intro")}</p>
        {status.isLoading ? <Loading /> : status.isError ? <ErrorNote /> : !status.data?.configured && !status.data?.connected ? (
          <p className="mt-4 text-[13px] text-muted">{t("nutrition.fitbit_unconfigured")}</p>
        ) : status.data.connected ? (
          <div className="mt-5 flex flex-wrap items-center gap-4">
            <span className="text-[13px]">{t("nutrition.fitbit_connected")}</span>
            <a href="https://www.fitbit.com/food" target="_blank" rel="noopener noreferrer" className="text-link text-[13px]">
              {t("nutrition.open_fitbit")}
            </a>
            <Button variant="ghost" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
              {t("nutrition.disconnect_fitbit")}
            </Button>
          </div>
        ) : (
          <div className="mt-5 flex flex-wrap items-center gap-4">
            <Button disabled={connect.isPending} onClick={() => connect.mutate()}>{t("nutrition.connect_fitbit")}</Button>
            <a href="https://www.fitbit.com/food" target="_blank" rel="noopener noreferrer" className="text-link text-[13px]">{t("nutrition.open_fitbit")}</a>
          </div>
        )}
        {connect.isError && <p role="alert" className="mt-3 text-[13px] text-red-600">{connect.error.message}</p>}
        {disconnect.isError && <p role="alert" className="mt-3 text-[13px] text-red-600">{disconnect.error.message}</p>}
      </Card>
      {status.data?.connected && (
        <Card>
          <CardHeader title={t("nutrition.diary_title")} />
          <label className="mb-5 flex max-w-xs flex-col gap-2 text-[12px] text-muted">
            {t("nutrition.diary_date")}
            <input type="date" value={day} onChange={(event) => setDay(event.target.value)} className="border border-hairline bg-transparent px-3 py-2.5 text-[13px] text-ink" />
          </label>
          {diary.isLoading ? <Loading /> : diary.isError ? (
            <p role="alert" className="text-[13px] text-red-600">{diary.error.message}</p>
          ) : diary.data ? (
            <>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
                {(["calories", "protein", "carbs", "fat", "water"] as const).map((key) => (
                  <div key={key} className="border-t border-hairline pt-3">
                    <p className="text-[12px] text-muted">{t(`nutrition.${key}`)}</p>
                    <p className="num mt-1 text-[22px]">{fmtNum(diary.data.summary[key], 0)}</p>
                    <p className="text-[11px] text-muted">{key === "calories" ? "kcal" : key === "water" ? "ml" : "g"}</p>
                  </div>
                ))}
              </div>
              <h3 className="mt-6 text-[13px] font-medium">{t("nutrition.foods_logged")}</h3>
              {!diary.data.foods.length ? <Empty>{t("nutrition.no_foods")}</Empty> : (
                <ul className="mt-2 divide-y divide-hairline">
                  {diary.data.foods.map((food, index) => (
                    <li key={index} className="flex justify-between gap-4 py-3 text-[13px]">
                      <span>{food.name ?? t("nutrition.unnamed_food")}{food.amount != null ? ` · ${food.amount} ${food.unit ?? ""}` : ""}</span>
                      <span className="num whitespace-nowrap">{food.calories != null ? `${fmtNum(food.calories, 0)} kcal` : "—"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : null}
        </Card>
      )}
    </div>
  );
}
