import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export interface AppCheckin {
  status: "ready" | "ai_disabled" | "no_data" | "unavailable";
  mode?: "ai" | "recorded";
  reason?: string;
  detail?: string;
  attempted_at?: string;
  date?: string;
  slot?: "morning" | "afternoon";
  generated_at?: string;
  timezone?: string;
  lines: string[];
}

// No timer or background refetch. The server owns the durable two-slot quota.
export function useAppCheckin(userId: number | undefined, trigger = false) {
  const query = useQuery({
    queryKey: ["today-checkin", userId],
    queryFn: () => api.post<AppCheckin>("/dashboard/check-in", {}),
    enabled: trigger && userId != null && document.visibilityState === "visible",
    staleTime: Infinity,
    retry: false,
    refetchOnMount: trigger ? "always" : false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchInterval: false,
  });
  const { refetch } = query;
  useEffect(() => {
    if (!trigger || userId == null) return;
    const onVisible = () => { if (document.visibilityState === "visible") void refetch(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [trigger, userId, refetch]);
  return query;
}
