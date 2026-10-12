import { useEffect, useRef } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";

export interface SyncFeed {
  provider: string; feed: string; state: string;
  last_attempt_at: string | null; last_success_at: string | null; latest_measurement_at: string | null;
  stale_after_hours: number; error_class: string | null;
  retry_state: "unknown" | "scheduled" | "reconnect_required" | "idle";
  has_checkpoint: boolean; failed_attempts: number;
  credentials_state: "unknown" | "configured" | "reconnect_required" | "not_required";
}
export interface SyncAccount {
  provider: string;
  state: "syncing" | "successful" | "partial" | "awaiting_new_data" | "delayed" | "auth_required" | "failed" | "connected" | "unknown";
  last_attempt_at: string | null; last_success_at: string | null; latest_measurement_at: string | null;
  has_successful_sync: boolean; data_freshness: "fresh" | "stale" | "not_measured";
  stale_after_hours: number; error_class: string | null; failed_attempts: number;
  credentials_state: SyncFeed["credentials_state"]; streams_failed: number; unprocessed: number;
}
// Accounts are additive: older servers may return only feeds.
export interface SyncHealth { feeds?: SyncFeed[]; accounts?: SyncAccount[] }

export function invalidateSyncedData(qc: QueryClient) {
  for (const key of ["sync-health", "lab", "devices", "overview", "sleep", "sleep-stages", "activities", "activity", "activity-calendar", "streams", "metric", "athlete-day", "endurance", "gym-plan", "setup-sleep-baseline"]) {
    void qc.invalidateQueries({ queryKey: [key] });
  }
}

export function useSyncHealth() {
  const uid = useUi(s => s.me?.user_id);
  const qc = useQueryClient();
  const previous = useRef(new Map<string, SyncAccount["state"]>());
  const query = useQuery({
    queryKey: ["lab", uid, "/lab/sync-health"],
    queryFn: () => api.get<SyncHealth>("/lab/sync-health"),
    staleTime: 30000,
    refetchInterval: query => query.state.data?.accounts?.some(account => account.state === "syncing") ? 2000 : 30000,
  });
  useEffect(() => {
    const accounts = query.data?.accounts ?? [];
    if (accounts.some(account => previous.current.get(account.provider) === "syncing" && account.state !== "syncing" && account.state !== "unknown" && account.state !== "connected")) invalidateSyncedData(qc);
    previous.current = new Map(accounts.map(account => [account.provider, account.state]));
  }, [query.data, qc]);
  return query;
}
