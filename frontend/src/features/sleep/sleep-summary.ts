import type { SleepSessionOut } from "../../app/api";

export function sleepDurations(night: SleepSessionOut) {
  const windowSeconds = (Date.parse(night.end_time) - Date.parse(night.start_time)) / 1000;
  const asleep = night.total_sleep_s;
  const stages = [night.deep_s, night.light_s, night.rem_s];
  const stageTotal = stages.reduce<number>((sum, value) => sum + (value ?? 0), 0);
  // Providers can round stage summaries to whole minutes. Larger discrepancies
  // are not evidence for a derived efficiency or a complete stage distribution.
  const tolerance = 60;
  const inconsistent = !Number.isFinite(windowSeconds) || windowSeconds <= 0
    || [...stages, asleep, night.awake_s].some((value) => value != null && (!Number.isFinite(value) || value < 0))
    || (asleep != null && asleep > windowSeconds)
    || stageTotal + (night.awake_s ?? 0) > windowSeconds + tolerance
    || (asleep != null && asleep + (night.awake_s ?? 0) > windowSeconds + tolerance)
    || (asleep != null && stages.every((value) => value != null) && Math.abs(stageTotal - asleep) > tolerance);
  return {
    windowSeconds: Number.isFinite(windowSeconds) && windowSeconds > 0 ? windowSeconds : null,
    inconsistent,
    efficiency: !inconsistent && asleep != null ? asleep / windowSeconds * 100 : null,
  };
}
