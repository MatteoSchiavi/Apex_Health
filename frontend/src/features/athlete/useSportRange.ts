import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { isCalendarDay, localDay, shiftDay } from "../../components/data";

function validRange(start: string, end: string) {
  return isCalendarDay(start) && isCalendarDay(end) && start <= end
    && (Date.parse(end) - Date.parse(start)) / 86400000 < 730;
}

/** Applied dates belong to the route; unfinished date edits stay local. */
export function useSportRange(timezone?: string) {
  const [params, setParams] = useSearchParams();
  const requestedStart = params.get("start") ?? "";
  const requestedEnd = params.get("end") ?? "";
  const validRequested = validRange(requestedStart, requestedEnd);
  const today = localDay(timezone);
  const range = validRequested
    ? { start: requestedStart, end: requestedEnd }
    : { start: shiftDay(today, -83), end: today };
  const [start, setStart] = useState(range.start);
  const [end, setEnd] = useState(range.end);
  useEffect(() => { setStart(range.start); setEnd(range.end); }, [range.start, range.end]);
  function applyRange() {
    if (!validRange(start, end)) return;
    setParams(previous => {
      const next = new URLSearchParams(previous);
      next.set("start", start);
      next.set("end", end);
      return next;
    });
  }
  return { start, setStart, end, setEnd, range, applyRange, validRange: validRange(start, end),
    invalidRangeLink: !!(requestedStart || requestedEnd) && !validRequested };
}
