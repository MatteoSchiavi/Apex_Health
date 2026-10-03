/** Both load windows use weekly units, matching the Python feature engine. */
export function trainingLoadSummary(acute7: number, chronic28: number) {
  const chronicWeekly = chronic28 / 4;
  return {
    acute: Math.round(acute7 * 10) / 10,
    chronic: Math.round(chronicWeekly * 10) / 10,
    acwr: chronicWeekly > 0 ? Math.round((acute7 / chronicWeekly) * 100) / 100 : null,
  };
}

/** Higher strain reduces readiness; absent recovery cannot produce a score. */
export function readinessFromRecovery(recovery: number | null, strain: number | null): number | null {
  if (recovery === null || !Number.isFinite(recovery)) return null;
  const penalty = strain !== null && Number.isFinite(strain)
    ? Math.max(-15, Math.min(15, (strain - 50) * 0.4))
    : 0;
  return Math.max(0, Math.min(100, Math.round(recovery - penalty)));
}
