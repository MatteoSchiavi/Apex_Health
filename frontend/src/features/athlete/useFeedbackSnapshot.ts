import { useCallback, useState } from "react";
import type { AthleteDay } from "./types";

/** Keep mounted feedback editors through sync updates and failed day refreshes. */
export function useFeedbackSnapshot(day: AthleteDay | null, scope: string) {
  const [retained, setRetained] = useState<{ scope: string; day: AthleteDay; active: string[] } | null>(null);
  const setDraftActive = useCallback((id: string, active: boolean) => {
    setRetained(previous => {
      const current = previous?.scope === scope ? previous : null;
      if (active) {
        if (current?.active.includes(id) || (!current && !day)) return previous;
        return { scope, day: current?.day ?? day!, active: [...(current?.active ?? []), id] };
      }
      if (!current?.active.includes(id)) return previous;
      const remaining = current.active.filter(value => value !== id);
      return remaining.length ? { ...current, active: remaining } : null;
    });
  }, [day, scope]);
  return { day: retained?.scope === scope ? retained.day : day, setDraftActive };
}
