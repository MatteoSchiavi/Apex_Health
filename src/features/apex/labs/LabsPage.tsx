"use client";

/**
 * Apex Health — Labs page.
 *
 * Re-skinned per ui-language/RULES.md (9 principles):
 *   1. One answer: "Your ferritin is borderline. Next donation in 14 days."
 *   2. One hero: the next-donation countdown.
 *   3. No outlines on cards. No card-in-card.
 *   4. Sentence-case labels, 13px minimum.
 *   5. Numbers stay white; status = dot + word (StatusDot).
 *   6. Accent is not a status colour.
 *   7. Plain words ("Labs", not "LABS").
 *   8. Charts: one line + reference baseline + latest point — via InteractiveLineChart.
 *   9. Lists are rows, not cards (history rows, add-panel rows).
 *
 * Data: GET /api/labs (list, seeds demo panels if none), POST /api/labs
 *       (create), DELETE /api/labs/[id] (delete).
 */

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useToast } from "@/hooks/use-toast";
import {
  ApexButton,
  Card,
  ChartFrame,
  DeltaChip,
  Empty,
  Hairline,
  Loading,
  PageSentence,
  RangeBar,
  Section,
  Segmented,
  StatusDot,
  rangeTone,
  toneFor,
} from "@/components/apex/kit";
import {
  ChartInfoBadge,
  ChartLegend,
  InteractiveLineChart,
} from "@/components/apex/charts";
import { fmtDate } from "@/lib/apex/format";
import type { LabPanel } from "@/lib/apex/types";
import {
  CORE_MARKERS,
  DEFAULT_RANGES,
  MARKER_BY_KEY,
  daysUntil,
  markerRange,
  markerValue,
  panelMarkerKeys,
  statusForValue,
  type MarkerMeta,
} from "@/lib/apex/labsHelpers";

/* --------------------------------------------------------------- types */

type MarkerKey = string; // one of CORE_MARKERS keys, or an extra-marker key

/* --------------------------------------------------------------- helpers */

function statusWord(
  status: "normal" | "low" | "high" | "borderline" | "unknown",
  t: (p: string) => string,
): string {
  switch (status) {
    case "normal":     return t("labs.status_normal");
    case "low":        return t("labs.status_low");
    case "high":       return t("labs.status_high");
    case "borderline": return t("labs.status_borderline");
    default:           return "—";
  }
}

function statusToDot(
  status: "normal" | "low" | "high" | "borderline" | "unknown",
): "ok" | "watch" | "alert" | "neutral" {
  switch (status) {
    case "normal":     return "ok";
    case "borderline": return "watch";
    case "low":
    case "high":        return "alert";
    default:           return "neutral";
  }
}

function rangeToDotTone(
  value: number | null,
  low: number | null,
  high: number | null,
): "ok" | "watch" | "alert" | "neutral" {
  const t = rangeTone(value, low, high);
  if (t === "positive") return "ok";
  if (t === "warning") return "watch";
  if (t === "alert") return "alert";
  return "neutral";
}

/** Marker display label, falling back to the key. */
function markerLabel(key: string, panel: LabPanel | undefined): string {
  if (MARKER_BY_KEY[key]) return MARKER_BY_KEY[key].label;
  const extra = panel?.extra_markers?.find((m) => m.key === key);
  return extra?.label ?? key;
}

function markerUnit(key: string, panel: LabPanel | undefined): string {
  if (MARKER_BY_KEY[key]) return MARKER_BY_KEY[key].unit;
  const extra = panel?.extra_markers?.find((m) => m.key === key);
  return extra?.unit ?? "";
}

function formatDonationType(s: string): string {
  return s
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function shortLabel(key: string): string {
  const map: Record<string, string> = {
    hemoglobin: "Hb",
    hematocrit: "Hct",
    ferritin: "Ferritin",
    iron: "Iron",
    wbc: "WBC",
    plt: "PLT",
  };
  return map[key] ?? key;
}

function markerInfoText(key: string): string {
  const map: Record<string, string> = {
    hemoglobin: "Oxygen-carrying capacity of blood. Drops after donations; low values flag anaemia.",
    hematocrit: "Percentage of blood volume occupied by red cells. Tracked alongside Hb.",
    ferritin: "Stored iron. The single best marker for long-term iron status; takes weeks to recover after donation.",
    iron: "Circulating serum iron. More variable day-to-day than ferritin.",
    wbc: "White blood cell count — immune-system signal. Spikes with infection.",
    plt: "Platelet count — clotting. Often measured pre-donation to confirm eligibility.",
  };
  return map[key] ?? "Marker tracked against its reference range.";
}

/* --------------------------------------------------------------- main page */

export function LabsPage() {
  const t = useT();
  const { toast } = useToast();

  const [panels, setPanels] = useState<LabPanel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [markerKey, setMarkerKey] = useState<MarkerKey>("hemoglobin");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/labs");
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to load labs");
      setPanels((data.panels as LabPanel[]) ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load labs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  /* ----- derived ---------------------------------------------------------- */

  const sortedPanels = useMemo(
    () => [...panels].sort((a, b) => (a.panel_date < b.panel_date ? 1 : a.panel_date > b.panel_date ? -1 : b.id - a.id)),
    [panels],
  );

  const latestBloodTest = useMemo(
    () => sortedPanels.find((p) => p.panel_type === "blood_test"),
    [sortedPanels],
  );

  const latestDonation = useMemo(
    () => sortedPanels.find((p) => p.panel_type === "donation"),
    [sortedPanels],
  );

  const lastPanel = sortedPanels[0];

  const nextDonationDays = latestDonation?.next_eligible_date
    ? daysUntil(latestDonation.next_eligible_date)
    : null;

  const latestFerritin = useMemo(() => {
    for (const p of sortedPanels) {
      const v = markerValue(p, "ferritin");
      if (v !== null) return { value: v, panel: p };
    }
    return null;
  }, [sortedPanels]);

  const latestHb = useMemo(() => {
    for (const p of sortedPanels) {
      const v = markerValue(p, "hemoglobin");
      if (v !== null) return { value: v, panel: p };
    }
    return null;
  }, [sortedPanels]);

  const markerOptions = useMemo(() => {
    const opts: { value: MarkerKey; label: string }[] = CORE_MARKERS.map((m) => ({
      value: m.key,
      label: m.label,
    }));
    const seen = new Set(CORE_MARKERS.map((m) => m.key));
    for (const p of sortedPanels) {
      for (const ex of p.extra_markers ?? []) {
        if (!seen.has(ex.key)) {
          seen.add(ex.key);
          opts.push({ value: ex.key, label: ex.label });
        }
      }
    }
    return opts;
  }, [sortedPanels]);

  // Trend chart data for the currently-selected marker.
  const trendPoints = useMemo(() => {
    const chrono = [...sortedPanels].reverse();
    return chrono.map((p) => {
      const v = markerValue(p, markerKey);
      return { date: p.panel_date, value: v };
    });
  }, [sortedPanels, markerKey]);

  const trendRange = useMemo(() => {
    const fromLatest = latestBloodTest ? markerRange(latestBloodTest, markerKey) : null;
    if (fromLatest) return fromLatest;
    return DEFAULT_RANGES[markerKey] ?? { low: 0, high: 0, unit: "" };
  }, [latestBloodTest, markerKey]);

  // The chart's dashed baseline = midpoint of the reference range.
  const trendBaseline = (trendRange.low + trendRange.high) / 2 || null;

  /* ----- page sentence (principle 1) ----- */
  const pageSentence = useMemo(() => {
    if (panels.length === 0) return "No panels yet. Add a blood test or donation to start tracking markers.";
    const parts: string[] = [];
    if (latestFerritin) {
      const range = markerRange(latestFerritin.panel, "ferritin");
      const dot = rangeToDotTone(latestFerritin.value, range.low, range.high);
      const word = dot === "ok" ? "in range" : dot === "watch" ? "borderline" : dot === "alert" ? "out of range" : "unknown";
      parts.push(`Your ferritin is ${word}.`);
    }
    if (nextDonationDays === null) {
      if (parts.length === 0) parts.push("Add a donation to see the next eligible date.");
    } else if (nextDonationDays <= 0) {
      parts.push("You're eligible to donate now.");
    } else {
      parts.push(`Next donation in ${nextDonationDays} ${nextDonationDays === 1 ? "day" : "days"}.`);
    }
    return parts.join(" ");
  }, [panels, latestFerritin, nextDonationDays]);

  /* ----- actions ---------------------------------------------------------- */

  const onCreate = async (payload: Partial<LabPanel> & { panel_date: string; panel_type: "blood_test" | "donation" }) => {
    try {
      const res = await fetch("/api/labs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to create panel");
      await reload();
      toast({ title: "Panel added" });
    } catch (e) {
      toast({
        title: "Could not add panel",
        description: e instanceof Error ? e.message : "",
      });
    }
  };

  const onDelete = async (id: number) => {
    try {
      const res = await fetch(`/api/labs/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to delete panel");
      setPanels((prev) => prev.filter((p) => p.id !== id));
      if (expandedId === id) setExpandedId(null);
      toast({ title: "Panel deleted" });
    } catch (e) {
      toast({
        title: "Delete failed",
        description: e instanceof Error ? e.message : "",
      });
    }
  };

  /* ----- render ----------------------------------------------------------- */

  return (
    <div className="mx-auto max-w-[1240px] space-y-8 px-6 py-8">
      {/* ===== Title + page sentence (principle 1) ===== */}
      <div>
        <h1 className="page-title">Labs</h1>
        <PageSentence className="mt-2">{pageSentence}</PageSentence>
      </div>

      {loading && panels.length === 0 ? (
        <Loading label="Loading panels…" />
      ) : error && panels.length === 0 ? (
        <Empty title={error} body="Try reloading the page." />
      ) : panels.length === 0 ? (
        <Empty title={t("labs.empty_title")} body={t("labs.empty_body")} />
      ) : (
        <>
          {/* ===== Row 1 — Status tiles (compact, no borders, StatusDots) ===== */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
            {/* Next donation — the hero */}
            <Card>
              <div className="text-[14px] font-medium text-ink2">{t("labs.next_donation")}</div>
              {nextDonationDays === null ? (
                <div className="mt-3 text-[16px] text-ink2">{t("labs.no_donation")}</div>
              ) : nextDonationDays <= 0 ? (
                <>
                  <div className="num mt-2 text-[40px] font-semibold leading-none text-ink">
                    Eligible
                  </div>
                  <div className="mt-2">
                    <StatusDot tone="ok" label={t("labs.eligible_now")} />
                  </div>
                </>
              ) : (
                <>
                  <div className="num mt-2 flex items-baseline gap-1.5 text-ink">
                    <span className="text-[40px] font-semibold leading-none">{nextDonationDays}</span>
                    <span className="text-[16px] font-medium text-ink2">
                      {nextDonationDays === 1 ? "day" : "days"}
                    </span>
                  </div>
                  <div className="mt-2">
                    <StatusDot
                      tone={nextDonationDays <= 7 ? "watch" : "neutral"}
                      label={nextDonationDays <= 7 ? "Soon" : "In range"}
                    />
                  </div>
                </>
              )}
              {latestDonation?.next_eligible_date && (
                <div className="num mt-2 text-[13px] text-ink2">
                  {fmtDate(latestDonation.next_eligible_date)}
                </div>
              )}
            </Card>

            {/* Latest ferritin */}
            <Card>
              <div className="text-[14px] font-medium text-ink2">{t("labs.latest_ferritin")}</div>
              {latestFerritin ? (
                <>
                  <div className="num mt-2 flex items-baseline gap-1.5 text-ink">
                    <span className="text-[40px] font-semibold leading-none">
                      {Number.isInteger(latestFerritin.value)
                        ? latestFerritin.value
                        : latestFerritin.value.toFixed(1)}
                    </span>
                    <span className="text-[16px] font-medium text-ink2">ng/mL</span>
                  </div>
                  <div className="mt-2">
                    <FerritinStatus panel={latestFerritin.panel} value={latestFerritin.value} t={t} />
                  </div>
                </>
              ) : (
                <div className="mt-3 text-[16px] text-ink2">{t("labs.no_panel")}</div>
              )}
            </Card>

            {/* Latest haemoglobin */}
            <Card>
              <div className="text-[14px] font-medium text-ink2">{t("labs.latest_hb")}</div>
              {latestHb ? (
                <>
                  <div className="num mt-2 flex items-baseline gap-1.5 text-ink">
                    <span className="text-[40px] font-semibold leading-none">
                      {Number.isInteger(latestHb.value)
                        ? latestHb.value
                        : latestHb.value.toFixed(1)}
                    </span>
                    <span className="text-[16px] font-medium text-ink2">g/dL</span>
                  </div>
                  <div className="mt-2">
                    <HbStatus panel={latestHb.panel} value={latestHb.value} t={t} />
                  </div>
                </>
              ) : (
                <div className="mt-3 text-[16px] text-ink2">{t("labs.no_panel")}</div>
              )}
            </Card>

            {/* Last panel */}
            <Card>
              <div className="text-[14px] font-medium text-ink2">{t("labs.last_panel")}</div>
              {lastPanel ? (
                <>
                  <div className="num mt-2 text-[28px] font-semibold leading-none text-ink">
                    {fmtDate(lastPanel.panel_date)}
                  </div>
                  <div className="mt-2">
                    <StatusDot
                      tone={lastPanel.panel_type === "donation" ? "neutral" : "ok"}
                      label={
                        lastPanel.panel_type === "donation"
                          ? `Donation${lastPanel.donation_type ? ` · ${formatDonationType(lastPanel.donation_type)}` : ""}`
                          : "Blood test"
                      }
                    />
                  </div>
                </>
              ) : (
                <div className="mt-3 text-[16px] text-ink2">{t("labs.no_panel")}</div>
              )}
            </Card>
          </div>

          {/* ===== Row 2 — Marker trends (InteractiveLineChart) ===== */}
          <Card>
            <Section label="Marker trend">
              <ChartFrame
                title={markerLabel(markerKey, latestBloodTest)}
                info={<ChartInfoBadge text={markerInfoText(markerKey)} />}
              >
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Segmented<MarkerKey>
                    value={markerKey}
                    onChange={setMarkerKey}
                    options={markerOptions.map((o) => ({ value: o.value, label: o.label }))}
                    size="sm"
                  />
                  <span className="num text-[13px] text-ink2">
                    Reference range:{" "}
                    {Number.isInteger(trendRange.low) ? trendRange.low : trendRange.low.toFixed(1)}–
                    {Number.isInteger(trendRange.high) ? trendRange.high : trendRange.high.toFixed(1)}{" "}
                    {trendRange.unit}
                  </span>
                </div>
                {trendPoints.some((p) => p.value !== null) ? (
                  <InteractiveLineChart
                    categories={trendPoints.map((p) => ({ label: p.date.slice(5) }))}
                    series={[
                      {
                        name: markerLabel(markerKey, latestBloodTest),
                        color: "var(--c-accent)",
                        values: trendPoints.map((p) => p.value),
                      },
                    ]}
                    baseline={trendBaseline}
                    baselineLabel="Reference midpoint"
                    yUnit={trendRange.unit}
                    height={180}
                    formatValue={(v) => (v === null ? "—" : Number.isInteger(v) ? `${v}` : v.toFixed(1))}
                  />
                ) : (
                  <div className="py-10 text-center text-[14px] text-ink2">
                    No data yet for this marker.
                  </div>
                )}
                <ChartLegend
                  className="mt-3"
                  items={[
                    { name: markerLabel(markerKey, latestBloodTest), color: "var(--c-accent)" },
                    { name: "Reference midpoint", color: "var(--c-text-3)" },
                  ]}
                />
              </ChartFrame>
            </Section>
          </Card>

          {/* ===== Row 3 — Panels history (rows) + Add panel form ===== */}
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
            {/* Left: panels as rows */}
            <div className="xl:col-span-8">
              <Card pad={false}>
                <div className="p-6 pb-3">
                  <div className="text-[14px] font-medium text-ink2">History</div>
                </div>
                <div className="px-7">
                  <div className="divide-y divide-[var(--c-divider)]">
                    {sortedPanels.map((p, idx) => {
                      const prev = sortedPanels[idx + 1];
                      const expanded = expandedId === p.id;
                      return (
                        <Fragment key={p.id}>
                          <button
                            type="button"
                            onClick={() => setExpandedId(expanded ? null : p.id)}
                            className="flex w-full items-center gap-4 py-3 text-left transition-colors hover:bg-surface2"
                          >
                            <div className="num shrink-0 text-[14px] font-medium text-ink">
                              {fmtDate(p.panel_date)}
                            </div>
                            <div className="shrink-0">
                              <StatusDot
                                tone={p.panel_type === "donation" ? "neutral" : "ok"}
                                label={
                                  p.panel_type === "donation"
                                    ? `Donation${p.donation_type ? ` · ${formatDonationType(p.donation_type)}` : ""}`
                                    : "Blood test"
                                }
                              />
                            </div>
                            {/* Compact marker dots */}
                            <div className="hidden min-w-0 flex-1 items-center gap-2 sm:flex">
                              {CORE_MARKERS.slice(0, 6).map((m) => {
                                const v = markerValue(p, m.key);
                                const range = markerRange(p, m.key);
                                const status = statusForValue(v, range.low, range.high);
                                const dotCls =
                                  status === "normal"
                                    ? "var(--c-ok)"
                                    : status === "borderline"
                                    ? "var(--c-watch)"
                                    : status === "low" || status === "high"
                                    ? "var(--c-alert)"
                                    : "var(--c-divider-strong)";
                                return (
                                  <span
                                    key={m.key}
                                    title={`${m.label}: ${v === null ? "—" : v} ${m.unit}`}
                                    className="inline-block h-2 w-2 rounded-full"
                                    style={{ background: dotCls }}
                                  />
                                );
                              })}
                            </div>
                            <div className="ml-auto shrink-0 text-faint">
                              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            </div>
                          </button>
                          {expanded && (
                            <div className="pb-4">
                              <PanelDetail panel={p} previous={prev} onDelete={onDelete} t={t} />
                            </div>
                          )}
                        </Fragment>
                      );
                    })}
                  </div>
                </div>
              </Card>
            </div>

            {/* Right: Add panel form */}
            <div className="xl:col-span-4 space-y-6">
              <AddPanelForm lastPanel={latestBloodTest ?? lastPanel} onSubmit={onCreate} t={t} />
              <Card>
                <Section label={t("labs.private_notes")}>
                  <p className="text-[14px] leading-relaxed text-ink2">{t("labs.privacy_note")}</p>
                </Section>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- Ferritin / Hb status */

function FerritinStatus({
  panel,
  value,
  t,
}: {
  panel: LabPanel;
  value: number;
  t: (p: string) => string;
}) {
  const range = markerRange(panel, "ferritin");
  const status = statusForValue(value, range.low, range.high);
  return <StatusDot tone={statusToDot(status)} label={statusWord(status, t)} />;
}

function HbStatus({
  panel,
  value,
  t,
}: {
  panel: LabPanel;
  value: number;
  t: (p: string) => string;
}) {
  const range = markerRange(panel, "hemoglobin");
  const status = statusForValue(value, range.low, range.high);
  return <StatusDot tone={statusToDot(status)} label={statusWord(status, t)} />;
}

/* --------------------------------------------------------------- Panel detail (expanded) */

function PanelDetail({
  panel,
  previous,
  onDelete,
  t,
}: {
  panel: LabPanel;
  previous: LabPanel | undefined;
  onDelete: (id: number) => void;
  t: (p: string) => string;
}) {
  const keys = panelMarkerKeys(panel);
  return (
    <div className="space-y-4 pb-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <StatusDot
            tone={panel.panel_type === "donation" ? "neutral" : "ok"}
            label={
              panel.panel_type === "donation"
                ? `Donation${panel.donation_type ? ` · ${formatDonationType(panel.donation_type)}` : ""}`
                : "Blood test"
            }
          />
          <div className="num mt-1 text-[14px] font-medium text-ink">{fmtDate(panel.panel_date)}</div>
        </div>
        <ApexButton
          variant="secondary"
          size="sm"
          icon={<Trash2 size={12} strokeWidth={2.4} />}
          onClick={() => onDelete(panel.id)}
        >
          Delete
        </ApexButton>
      </div>

      {panel.next_eligible_date && (
        <div className="num text-[13px] text-ink2">
          Next eligible: <span className="font-medium text-ink">{fmtDate(panel.next_eligible_date)}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-2">
        {keys.map((k) => {
          const v = markerValue(panel, k);
          const range = markerRange(panel, k);
          const prevV = previous ? markerValue(previous, k) : null;
          const delta = v !== null && prevV !== null ? v - prevV : null;
          const label = markerLabel(k, panel);
          const unit = markerUnit(k, panel);
          const dotTone = rangeToDotTone(v, range.low, range.high);
          const barLow = range.low;
          const barHigh = range.high && range.high > range.low ? range.high : (v ?? 0) * 2 || 1;
          return (
            <div key={k}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[14px] font-medium text-ink2">{label}</span>
                <span className="num text-[13px] text-ink2">
                  {Number.isInteger(barLow) ? barLow : barLow.toFixed(1)}–
                  {Number.isInteger(barHigh) ? barHigh : barHigh.toFixed(1)} {unit}
                </span>
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="num text-[20px] font-semibold text-ink">
                  {v === null ? "—" : Number.isInteger(v) ? v : v.toFixed(1)}
                </span>
                <span className="text-[13px] text-ink2">{unit}</span>
                <div className="ml-auto">
                  <StatusDot
                    tone={dotTone}
                    label={
                      v === null
                        ? "—"
                        : dotTone === "ok"
                        ? "In range"
                        : dotTone === "watch"
                        ? "Borderline"
                        : "Out of range"
                    }
                  />
                </div>
              </div>
              <div className="mt-2">
                <RangeBar
                  value={v}
                  low={barLow}
                  high={barHigh}
                  tone={toneFor(rangeTone(v, range.low, range.high))}
                  unit={unit}
                  height={4}
                />
              </div>
              {delta !== null && (
                <div className="mt-2">
                  <DeltaChip
                    delta={delta}
                    goodWhen="up"
                    compact
                    suffix="vs prev"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {panel.notes && (
        <>
          <Hairline />
          <Section label={t("labs.private_notes")}>
            <p className="text-[14px] leading-relaxed text-ink2">{panel.notes}</p>
          </Section>
        </>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- Add panel form */

interface ExtraMarkerDraft {
  key: string;
  label: string;
  value: string;
  unit: string;
  ref_low: string;
  ref_high: string;
}

function AddPanelForm({
  lastPanel,
  onSubmit,
  t,
}: {
  lastPanel: LabPanel | undefined;
  onSubmit: (payload: Partial<LabPanel> & { panel_date: string; panel_type: "blood_test" | "donation" }) => void;
  t: (p: string) => string;
}) {
  const today = new Date().toISOString().slice(0, 10);

  const [panelDate, setPanelDate] = useState(today);
  const [panelType, setPanelType] = useState<"blood_test" | "donation">("blood_test");
  const [donationType, setDonationType] = useState("whole_blood");
  const lastRanges = lastPanel?.reference_ranges ?? DEFAULT_RANGES;
  const [nextEligibleDate, setNextEligibleDate] = useState("");

  const initVals = (): Record<string, string> => {
    const out: Record<string, string> = {};
    for (const m of CORE_MARKERS) {
      const v = lastPanel ? markerValue(lastPanel, m.key) : null;
      out[m.key] = v === null ? "" : String(v);
    }
    return out;
  };
  const [vals, setVals] = useState<Record<string, string>>(initVals);
  const [ranges, setRanges] = useState<Record<string, { low: string; high: string }>>(() => {
    const out: Record<string, { low: string; high: string }> = {};
    for (const m of CORE_MARKERS) {
      const r = lastRanges[m.key] ?? DEFAULT_RANGES[m.key];
      out[m.key] = {
        low: r?.low !== null && r?.low !== undefined ? String(r.low) : "",
        high: r?.high !== null && r?.high !== undefined ? String(r.high) : "",
      };
    }
    return out;
  });

  const [extras, setExtras] = useState<ExtraMarkerDraft[]>([]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setVals(initVals());
    setRanges(() => {
      const out: Record<string, { low: string; high: string }> = {};
      const lr = lastPanel?.reference_ranges ?? DEFAULT_RANGES;
      for (const m of CORE_MARKERS) {
        const r = lr[m.key] ?? DEFAULT_RANGES[m.key];
        out[m.key] = {
          low: r?.low !== null && r?.low !== undefined ? String(r.low) : "",
          high: r?.high !== null && r?.high !== undefined ? String(r.high) : "",
        };
      }
      return out;
    });
  }, [lastPanel?.id]);

  const setVal = (k: string, v: string) => setVals((s) => ({ ...s, [k]: v }));
  const setRangeLow = (k: string, v: string) => setRanges((s) => ({ ...s, [k]: { ...s[k], low: v } }));
  const setRangeHigh = (k: string, v: string) => setRanges((s) => ({ ...s, [k]: { ...s[k], high: v } }));

  const addExtra = () =>
    setExtras((s) => [
      ...s,
      { key: `extra_${Date.now()}`, label: "", value: "", unit: "", ref_low: "", ref_high: "" },
    ]);

  const updateExtra = (i: number, patch: Partial<ExtraMarkerDraft>) =>
    setExtras((s) => s.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  const removeExtra = (i: number) => setExtras((s) => s.filter((_, j) => j !== i));

  const submit = async () => {
    if (!panelDate) return;
    setSubmitting(true);
    try {
      const num = (s: string): number | null => {
        if (!s.trim()) return null;
        const n = Number(s);
        return Number.isFinite(n) ? n : null;
      };
      const referenceRanges: Record<string, { low: number | null; high: number | null; unit: string }> = {};
      for (const m of CORE_MARKERS) {
        referenceRanges[m.key] = {
          low: num(ranges[m.key].low),
          high: num(ranges[m.key].high),
          unit: m.unit,
        };
      }
      const extraMarkers = extras
        .filter((e) => e.label.trim())
        .map((e) => ({
          key: e.key,
          label: e.label.trim(),
          value: num(e.value),
          unit: e.unit.trim() || "—",
          ref_low: num(e.ref_low),
          ref_high: num(e.ref_high),
        }));

      await onSubmit({
        panel_date: panelDate,
        panel_type: panelType,
        donation_type: panelType === "donation" ? donationType : null,
        hemoglobin: num(vals.hemoglobin),
        hematocrit: num(vals.hematocrit),
        ferritin: num(vals.ferritin),
        iron: num(vals.iron),
        wbc: num(vals.wbc),
        plt: num(vals.plt),
        next_eligible_date: nextEligibleDate || null,
        notes: notes.trim() || null,
        extra_markers: extraMarkers,
        reference_ranges: referenceRanges,
      });

      setVals((s) => Object.fromEntries(Object.keys(s).map((k) => [k, ""])));
      setNotes("");
      setNextEligibleDate("");
      setExtras([]);
    } finally {
      setSubmitting(false);
    }
  };

  // Shared input styling. Inputs keep their hairline (RULES: outlines only on
  // inputs + focus) but the surrounding form has no bordered tiles.
  const inputCls =
    "num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary transition-colors";
  const labelCls = "block text-[13px] font-medium text-ink2";

  return (
    <Card>
      <Section label={t("labs.add_panel")}>
        <div className="space-y-4">
          {/* Date */}
          <label className={labelCls}>
            {t("labs.panel_date")}
            <input
              type="date"
              value={panelDate}
              onChange={(e) => setPanelDate(e.target.value)}
              className={`${inputCls} mt-1`}
            />
          </label>

          {/* Type */}
          <div>
            <div className={labelCls}>{t("labs.panel_type")}</div>
            <div className="mt-1">
              <Segmented<"blood_test" | "donation">
                value={panelType}
                onChange={setPanelType}
                options={[
                  { value: "blood_test", label: t("labs.blood_test") },
                  { value: "donation", label: t("labs.donation") },
                ]}
                size="sm"
              />
            </div>
          </div>

          {/* Donation type (when relevant) */}
          {panelType === "donation" && (
            <label className={labelCls}>
              {t("labs.donation_type")}
              <select
                value={donationType}
                onChange={(e) => setDonationType(e.target.value)}
                className={`${inputCls} mt-1`}
              >
                <option value="whole_blood">Whole blood</option>
                <option value="plasma">Plasma</option>
                <option value="platelets">Platelets</option>
                <option value="double_red_cells">Double red cells</option>
              </select>
            </label>
          )}

          <Hairline />

          {/* Core markers grid (no bordered tiles) */}
          <div>
            <div className={labelCls}>Markers</div>
            <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {CORE_MARKERS.map((m: MarkerMeta) => (
                <label key={m.key} className="block">
                  <span className="text-[13px] font-medium text-ink2">
                    {m.label} <span className="text-faint">· {m.unit}</span>
                  </span>
                  <input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    value={vals[m.key]}
                    onChange={(e) => setVal(m.key, e.target.value)}
                    placeholder="—"
                    className={`${inputCls} mt-1`}
                  />
                  <div className="mt-1 grid grid-cols-2 gap-1">
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      value={ranges[m.key].low}
                      onChange={(e) => setRangeLow(m.key, e.target.value)}
                      placeholder="low"
                      className={`${inputCls} !text-ink2`}
                      title={t("labs.ref_low")}
                    />
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      value={ranges[m.key].high}
                      onChange={(e) => setRangeHigh(m.key, e.target.value)}
                      placeholder="high"
                      className={`${inputCls} !text-ink2`}
                      title={t("labs.ref_high")}
                    />
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Extra markers (no bordered tiles) */}
          {extras.length > 0 && (
            <div className="space-y-3">
              {extras.map((e, i) => (
                <div key={e.key} className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <input
                      type="text"
                      value={e.label}
                      onChange={(ev) => updateExtra(i, { label: ev.target.value })}
                      placeholder={t("labs.marker_name")}
                      className={`${inputCls} flex-1`}
                    />
                    <input
                      type="text"
                      value={e.unit}
                      onChange={(ev) => updateExtra(i, { unit: ev.target.value })}
                      placeholder={t("labs.marker_unit")}
                      className={`${inputCls} w-20`}
                    />
                    <button
                      type="button"
                      onClick={() => removeExtra(i)}
                      className="rounded-[var(--radius-control)] px-1.5 py-1 text-[13px] text-faint hover:bg-surface2 hover:text-alert"
                      aria-label="Remove"
                    >
                      ×
                    </button>
                  </div>
                  <div className="grid grid-cols-3 gap-1">
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      value={e.value}
                      onChange={(ev) => updateExtra(i, { value: ev.target.value })}
                      placeholder={t("labs.marker_value")}
                      className={inputCls}
                    />
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      value={e.ref_low}
                      onChange={(ev) => updateExtra(i, { ref_low: ev.target.value })}
                      placeholder="low"
                      className={`${inputCls} !text-ink2`}
                    />
                    <input
                      type="number"
                      inputMode="decimal"
                      step="any"
                      value={e.ref_high}
                      onChange={(ev) => updateExtra(i, { ref_high: ev.target.value })}
                      placeholder="high"
                      className={`${inputCls} !text-ink2`}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={addExtra}
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-control)] px-2 py-1 text-[13px] font-medium text-ink2 hover:bg-surface2 hover:text-ink"
          >
            <Plus size={13} strokeWidth={2.4} />
            {t("labs.add_marker")}
          </button>

          <Hairline />

          {/* Next eligible date */}
          <label className={labelCls}>
            {t("labs.next_eligible")}
            <input
              type="date"
              value={nextEligibleDate}
              onChange={(e) => setNextEligibleDate(e.target.value)}
              className={`${inputCls} mt-1`}
            />
          </label>

          {/* Private notes */}
          <label className={labelCls}>
            {t("labs.private_notes")}
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes about this panel…"
              rows={2}
              className={`${inputCls} mt-1 !py-2`}
            />
          </label>

          <ApexButton onClick={submit} disabled={submitting || !panelDate} className="w-full">
            {submitting ? "Saving…" : t("labs.add_panel")}
          </ApexButton>
        </div>
      </Section>
    </Card>
  );
}

/* re-export for type-checking */
export type { LabPanel };
