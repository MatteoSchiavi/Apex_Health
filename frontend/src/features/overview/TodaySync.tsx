import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../app/api";
import { Button } from "../../components/kit";
import { invalidateSyncedData } from "../lab/syncHealth";

export function TodaySync() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [job, setJob] = useState<string>();
  const [message, setMessage] = useState("");
  const sync = useMutation({
    mutationFn: () => api.post<{job_id: string}>("/settings/integrations/garmin/sync", {}),
    onSuccess: result => { setJob(result.job_id); setMessage("design.sync_queued"); },
  });
  const status = useQuery({
    queryKey: ["today-sync", job],
    queryFn: () => api.get<{ completed: boolean; state: string; result?: {status?: string} }>(`/settings/integrations/garmin/sync/${job}`),
    enabled: !!job,
    retry: false,
    refetchInterval: query => query.state.data?.completed || query.state.status === "error" ? false : 2000,
  });
  useEffect(() => {
    if (status.data?.completed) {
      setMessage(status.data.result?.status === "ok" ? "design.sync_done" : "design.sync_partial");
      if (status.data.state !== "SUCCESS") setMessage("design.sync_failed");
      invalidateSyncedData(qc);
      setJob(undefined);
    } else if (status.isError) { setJob(undefined); setMessage("design.sync_status_failed"); }
  }, [status.data, status.isError, qc]);
  return <div className="flex flex-wrap items-center gap-3">
    <Button variant="ghost" disabled={sync.isPending || !!job} onClick={() => sync.mutate()}>{t(sync.isPending || job ? "common.loading" : "settings.sync_now")}</Button>
    {(message || sync.isError) && <span role="status" className="text-[12px] text-muted">{t(sync.isError ? "design.sync_failed" : message)} <Link className="text-link" to="/app/settings?tab=data-health">{t("lab.data_health")} →</Link></span>}
  </div>;
}
