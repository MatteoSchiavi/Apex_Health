import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../app/api";
import { Button, Input } from "../../components/kit";

export function GarminPersonalConnectForm({ onDone }: { onDone: (enqueued: boolean) => void }) {
  const { t } = useTranslation();
  const [key, setKey] = useState("");
  const connect = useMutation({
    mutationFn: async () => {
      const result = await api.post<{ connected: boolean; backfill_enqueued: boolean }>(
        "/settings/integrations/garmin/personal/connect", { api_key: key.trim() },
      );
      if (!result.connected) throw new Error("Connection was not confirmed");
      return result;
    },
    onSuccess: result => { setKey(""); onDone(result.backfill_enqueued); },
  });
  const status = connect.error instanceof ApiError ? connect.error.status : null;
  const errorKey = status === 429 ? "rate_limit" : status === 409 ? "busy"
    : status === 403 ? "owner_only" : status === 400 || status === 401 || status === 422 ? "invalid_key" : "unavailable";
  return <form className="border-b border-hairline py-5" onSubmit={(event: FormEvent) => {
    event.preventDefault();
    if (key.trim() && !connect.isPending) connect.mutate();
  }}>
    <h3 className="text-[14px] font-medium">{t("garminPersonal.title")}</h3>
    <p className="mt-2 max-w-2xl text-[13px] text-muted">{t("garminPersonal.intro")}</p>
    <p className="mt-2 max-w-2xl text-[12px] text-muted">{t("garminPersonal.coverage_window")}</p>
    <ol className="my-4 list-decimal space-y-2 pl-5 text-[13px]">
      <li><a className="text-link" href="https://connect.garmin.com/app/settings/personalApiToken" target="_blank" rel="noopener noreferrer">{t("garminPersonal.create_key")} ↗</a></li>
      <li>{t("garminPersonal.copy_key")}</li>
    </ol>
    <fieldset disabled={connect.isPending} className="space-y-3">
      <Input label={t("garminPersonal.key")} type="password" autoComplete="off" value={key} onChange={setKey} required />
      <p className="max-w-2xl text-[12px] text-muted">{t("garminPersonal.storage")}</p>
      <Button type="submit" disabled={connect.isPending || !key.trim()}>{t(connect.isPending ? "garminPersonal.verifying" : "garminPersonal.verify_connect")}</Button>
    </fieldset>
    {connect.isError && <p role="alert" className="mt-3 text-[13px] text-alertText">{t("garminPersonal." + errorKey)}</p>}
    <details className="mt-4 text-[12px] text-muted"><summary className="cursor-pointer">{t("garminPersonal.coverage_title")}</summary><p className="mt-2 max-w-2xl">{t("garminPersonal.coverage")}</p></details>
  </form>;
}
