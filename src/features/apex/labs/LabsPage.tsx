"use client";

/**
 * Apex Health — Labs page (plan §7).
 *
 * The page's job: track blood markers against reference ranges over time,
 * and know when you can donate again.
 *
 * Layout (strictly per plan §7):
 *   Row 1, Status (col-12): four tiles — Next donation (BigStat), Latest
 *     ferritin (value + status chip), Latest haemoglobin (same), Last panel
 *     (date + type).
 *   Row 2, Marker trends (col-12): marker selector (Segmented) +
 *     MarkerTrendChart (custom SVG with ref-range band + donation markers) +
 *     ChartInfoBadge.
 *   Row 3, Panels and entry (col-12 xl:col-8 + col-12 xl:col-4):
 *     Left: panel table newest first with range dots; clicking expands the
 *     panel detail inline (RangeBar per marker + delta vs previous panel +
 *     notes + Delete).
 *     Right: Add panel form (date, type, donation type, six core markers +
 *     "+ add marker", ref ranges pre-filled from last panel, next eligible
 *     date, private notes).
 *   Privacy line under the form: numeric values stored as provided; free-text
 *     notes encrypted at the application layer (mirrors backend behaviour).
 *
 * Data: GET /api/labs (list, seeds demo panels if none), POST /api/labs
 * (create), PATCH /api/labs/[id] (update — used by Delete to clear fields if
 * needed), DELETE /api/labs/[id] (delete).
 *
 * "use client" — fetched via useEffect + fetch. All inline strings use the
 * labs.* / common.* i18n keys; a few extras are inline (TODO i18n).
 */

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useToast } from "@/hooks/use-toast";
import {
  ApexButton,
  Badge,
  BigStat,
  Card,
  CardHeader,
  Empty,
  Eyebrow,
  Hairline,
  Loading,
  PageHeader,
  RangeBar,
  Segmented,
  toneFor,
  rangeTone,
} from "@/components/apex/kit";
import { ChartInfoBadge } from "@/components/apex/charts";
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
import { MarkerTrendChart, type MarkerPoint } from "./MarkerTrendChart";

/* --------------------------------------------------------------- types */

type MarkerKey = string; // one of CORE_MARKERS keys, or an extra-marker key

/* --------------------------------------------------------------- helpers */

/** Returns a CSS colour for a status string (used by range dots in the table). */
function statusDotTone(status: "normal" | "low" | "high" | "borderline" | "unknown") {
  switch (status) {
    case "normal":    return "bg-positive";
    case "low":
    case "high":      return "bg-alert";
    case "borderline":return "bg-warning";
    default:          return "bg-hairline2";
  }
}

function statusLabel(status: "normal" | "low" | "high" | "borderline" | "unknown", t: (p: string) => string) {
  switch (status) {
    case "normal":    return t("labs.status_normal");
    case "low":       return t("labs.status_low");
    case "high":      return t("labs.status_high");
    case "borderline":return t("labs.status_borderline");
    default:          return "—";
  }
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

/* --------------------------------------------------------------- main page */

export function LabsPage() {
  const t = useT();
  const { toast } = useToast();

  const [panels, setPanels] = useState<LabPanel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Currently selected marker key for the trend chart.
  const [markerKey, setMarkerKey] = useState<MarkerKey>("hemoglobin");
  // Expanded panel id for inline detail.
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

  // Panels are returned newest first; for "previous panel" delta we want to
  // look ahead by one in the list.
  const sortedPanels = useMemo(
    () => [...panels].sort((a, b) => (a.panel_date < b.panel_date ? 1 : a.panel_date > b.panel_date ? -1 : b.id - a.id)),
    [panels],
  );

  // The "latest" panel for Row 1 status (newest by date — donations count if
  // they happen to be the newest; the panels list already is newest-first).
  const latestBloodTest = useMemo(
    () => sortedPanels.find((p) => p.panel_type === "blood_test"),
    [sortedPanels],
  );

  // Latest donation panel (any panel with panel_type === 'donation').
  const latestDonation = useMemo(
    () => sortedPanels.find((p) => p.panel_type === "donation"),
    [sortedPanels],
  );

  const lastPanel = sortedPanels[0];

  // Next-donation countdown
  const nextDonationDays = latestDonation?.next_eligible_date
    ? daysUntil(latestDonation.next_eligible_date)
    : null;

  // Latest ferritin + Hb (from the newest blood test that has the value).
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

  // Marker selector options: the six core markers + any extra from the
  // latest panel that has extras.
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
  const trendPoints: MarkerPoint[] = useMemo(() => {
    // chronological order (oldest first)
    const chrono = [...sortedPanels].reverse();
    return chrono.map((p) => {
      const v = markerValue(p, markerKey);
      return {
        date: p.panel_date,
        value: v,
        isDonation: p.panel_type === "donation",
        label: fmtDate(p.panel_date),
      };
    });
  }, [sortedPanels, markerKey]);

  const trendRange = useMemo(() => {
    const fromLatest = latestBloodTest ? markerRange(latestBloodTest, markerKey) : null;
    if (fromLatest) return fromLatest;
    return DEFAULT_RANGES[markerKey] ?? { low: 0, high: 0, unit: "" };
  }, [latestBloodTest, markerKey]);

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
      toast({ title: "Panel added" /* TODO i18n */ });
    } catch (e) {
      toast({
        title: "Could not add panel" /* TODO i18n */,
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
      toast({ title: "Panel deleted" /* TODO i18n */ });
    } catch (e) {
      toast({
        title: "Delete failed" /* TODO i18n */,
        description: e instanceof Error ? e.message : "",
      });
    }
  };

  /* ----- render ----------------------------------------------------------- */

  return (
    <div className="mx-auto max-w-[1240px] space-y-4">
      <PageHeader title={t("nav.labs")} subtitle={t("labs.subtitle")} />

      {loading && panels.length === 0 ? (
        <Loading label="Loading panels…" /* TODO i18n */ />
      ) : error && panels.length === 0 ? (
        <Empty title={error} body="Try reloading the page." /* TODO i18n */ />
      ) : panels.length === 0 ? (
        <Empty title={t("labs.empty_title")} body={t("labs.empty_body")} />
      ) : (
        <>
          {/* ───────────────────────────────────── Row 1 — Status */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {/* Next donation — primary tile */}
            <Card className="bg-surface2">
              <Eyebrow>{t("labs.next_donation")}</Eyebrow>
              {nextDonationDays === null ? (
                <div className="mt-2 text-[13px] text-muted">{t("labs.no_donation")}</div>
              ) : nextDonationDays <= 0 ? (
                <BigStat value={t("labs.eligible_now")} size="md" tone="positive" />
              ) : (
                <BigStat
                  value={nextDonationDays}
                  unit={nextDonationDays === 1 ? "day" : "days"}
                  size="md"
                  tone={nextDonationDays <= 7 ? "warning" : "primary"}
                />
              )}
              {latestDonation?.next_eligible_date && (
                <div className="num mt-1 text-[11px] text-faint">
                  {fmtDate(latestDonation.next_eligible_date)}
                </div>
              )}
            </Card>

            {/* Latest ferritin */}
            <Card className="bg-surface2">
              <Eyebrow>{t("labs.latest_ferritin")}</Eyebrow>
              {latestFerritin ? (
                <>
                  <div className="num mt-2 flex items-baseline gap-2">
                    <BigStat
                      value={Number.isInteger(latestFerritin.value) ? latestFerritin.value : latestFerritin.value.toFixed(1)}
                      unit="ng/mL"
                      tone={toneFor(rangeTone(latestFerritin.value, trendRangeFor(latestFerritin.panel, "ferritin").low, trendRangeFor(latestFerritin.panel, "ferritin").high))}
                    />
                  </div>
                  <div className="mt-1.5">
                    <FerritinChip panel={latestFerritin.panel} value={latestFerritin.value} t={t} />
                  </div>
                </>
              ) : (
                <div className="mt-2 text-[13px] text-muted">{t("labs.no_panel")}</div>
              )}
            </Card>

            {/* Latest haemoglobin */}
            <Card className="bg-surface2">
              <Eyebrow>{t("labs.latest_hb")}</Eyebrow>
              {latestHb ? (
                <>
                  <div className="num mt-2 flex items-baseline gap-2">
                    <BigStat
                      value={Number.isInteger(latestHb.value) ? latestHb.value : latestHb.value.toFixed(1)}
                      unit="g/dL"
                      tone={toneFor(rangeTone(latestHb.value, trendRangeFor(latestHb.panel, "hemoglobin").low, trendRangeFor(latestHb.panel, "hemoglobin").high))}
                    />
                  </div>
                  <div className="mt-1.5">
                    <HbChip panel={latestHb.panel} value={latestHb.value} t={t} />
                  </div>
                </>
              ) : (
                <div className="mt-2 text-[13px] text-muted">{t("labs.no_panel")}</div>
              )}
            </Card>

            {/* Last panel */}
            <Card className="bg-surface2">
              <Eyebrow>{t("labs.last_panel")}</Eyebrow>
              {lastPanel ? (
                <>
                  <div className="num mt-2 text-[18px] font-semibold leading-7 text-ink">
                    {fmtDate(lastPanel.panel_date)}
                  </div>
                  <div className="mt-1.5">
                    <Badge tone={lastPanel.panel_type === "donation" ? "primary" : "neutral"} dot>
                      {lastPanel.panel_type === "donation"
                        ? `${t("labs.donation")}${lastPanel.donation_type ? ` · ${formatDonationType(lastPanel.donation_type)}` : ""}`
                        : t("labs.blood_test")}
                    </Badge>
                  </div>
                </>
              ) : (
                <div className="mt-2 text-[13px] text-muted">{t("labs.no_panel")}</div>
              )}
            </Card>
          </div>

          {/* ───────────────────────────────────── Row 2 — Marker trends */}
          <Card>
            <CardHeader
              eyebrow={t("labs.marker_trend")}
              title={markerLabel(markerKey, latestBloodTest)}
              right={
                <div className="flex items-center gap-2">
                  <ChartInfoBadge text={markerInfoText(markerKey)} />
                </div>
              }
            />
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Segmented<MarkerKey>
                value={markerKey}
                onChange={setMarkerKey}
                options={markerOptions.map((o) => ({ value: o.value, label: o.label }))}
                size="sm"
              />
              <span className="num text-[11px] text-faint">
                {Number.isInteger(trendRange.low) ? trendRange.low : trendRange.low.toFixed(1)}–
                {Number.isInteger(trendRange.high) ? trendRange.high : trendRange.high.toFixed(1)} {trendRange.unit}
              </span>
            </div>
            <div className="mt-3">
              <MarkerTrendChart
                points={trendPoints}
                refLow={trendRange.low}
                refHigh={trendRange.high}
                unit={trendRange.unit}
                height={170}
              />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-[10px] text-faint">
              <LegendDot color="bg-positive" label={t("labs.in_range")} />
              <LegendDot color="bg-alert" label={t("labs.out_range")} />
              <LegendDot color="bg-primary" label="Trend line" /* TODO i18n */ />
              <LegendDot color="bg-hairline2" label="Donation" /* TODO i18n */ />
            </div>
          </Card>

          {/* ───────────────────────────────────── Row 3 — Panels + Add form */}
          <div className="grid grid-cols-12 gap-3">
            {/* Left: panels table */}
            <div className="col-span-12 xl:col-span-8">
              <Card pad={false}>
                <div className="px-4 pt-4">
                  <CardHeader eyebrow={"Panels" /* TODO i18n */} title={"History" /* TODO i18n */} />
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-[12px]">
                    <thead>
                      <tr className="border-b border-hairline bg-surface2/40 text-faint">
                        <th className="eyebrow px-3 py-2 text-left">Date</th>
                        <th className="eyebrow px-3 py-2 text-left">Type</th>
                        {CORE_MARKERS.map((m) => (
                          <th key={m.key} className="eyebrow px-2 py-2 text-center" title={m.label}>
                            {shortLabel(m.key)}
                          </th>
                        ))}
                        <th className="px-2 py-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedPanels.map((p, idx) => {
                        const prev = sortedPanels[idx + 1]; // older panel
                        const expanded = expandedId === p.id;
                        return (
                          <Fragment key={p.id}>
                            <tr
                              className="cursor-pointer border-b border-hairline hover:bg-surface2/40"
                              onClick={() => setExpandedId(expanded ? null : p.id)}
                            >
                              <td className="num px-3 py-2.5 text-ink">{fmtDate(p.panel_date)}</td>
                              <td className="px-3 py-2.5">
                                {p.panel_type === "donation" ? (
                                  <Badge tone="primary" dot>
                                    {t("labs.donation")}
                                  </Badge>
                                ) : (
                                  <Badge tone="neutral">{t("labs.blood_test")}</Badge>
                                )}
                              </td>
                              {CORE_MARKERS.map((m) => {
                                const v = markerValue(p, m.key);
                                const range = markerRange(p, m.key);
                                const status = statusForValue(v, range.low, range.high);
                                return (
                                  <td key={m.key} className="px-2 py-2.5 text-center">
                                    {v === null ? (
                                      <span className="text-faint">—</span>
                                    ) : (
                                      <span className="inline-flex flex-col items-center gap-0.5">
                                        <span
                                          className={`inline-block h-2 w-2 rounded-full ${statusDotTone(status)}`}
                                          title={`${statusLabel(status, t)}`}
                                        />
                                        <span className="num text-[10px] text-muted">
                                          {Number.isInteger(v) ? v : v.toFixed(1)}
                                        </span>
                                      </span>
                                    )}
                                  </td>
                                );
                              })}
                              <td className="px-2 py-2.5 text-right text-faint">
                                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                              </td>
                            </tr>
                            {expanded && (
                              <tr>
                                <td colSpan={CORE_MARKERS.length + 3} className="bg-surface2/40 px-4 py-4">
                                  <PanelDetail panel={p} previous={prev} onDelete={onDelete} t={t} />
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>

            {/* Right: Add panel form */}
            <div className="col-span-12 xl:col-span-4">
              <AddPanelForm
                lastPanel={latestBloodTest ?? lastPanel}
                onSubmit={onCreate}
                t={t}
              />
              {/* Privacy line — mirrors what the code does today */}
              <Card className="mt-3 bg-surface2">
                <Eyebrow>{t("labs.private_notes")}</Eyebrow>
                <p className="mt-1.5 text-[11px] leading-relaxed text-muted">{t("labs.privacy_note")}</p>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- Ferritin / Hb status chip */

function FerritinChip({
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
  const tone = toneFor(rangeTone(value, range.low, range.high));
  return (
    <Badge tone={tone === "positive" ? "positive" : tone === "warning" ? "warning" : tone === "alert" ? "alert" : "neutral"} dot>
      {statusLabel(status, t)}
    </Badge>
  );
}

function HbChip({
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
  const tone = toneFor(rangeTone(value, range.low, range.high));
  return (
    <Badge tone={tone === "positive" ? "positive" : tone === "warning" ? "warning" : tone === "alert" ? "alert" : "neutral"} dot>
      {statusLabel(status, t)}
    </Badge>
  );
}

/** Returns the reference range for a marker on a panel, used by the Row 1 chips. */
function trendRangeFor(panel: LabPanel, key: string) {
  return markerRange(panel, key);
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

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      <span>{label}</span>
    </span>
  );
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
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <Eyebrow>
            {panel.panel_type === "donation"
              ? `${t("labs.donation")}${panel.donation_type ? ` · ${formatDonationType(panel.donation_type)}` : ""}`
              : t("labs.blood_test")}
          </Eyebrow>
          <div className="num mt-0.5 text-[13px] font-semibold text-ink">{fmtDate(panel.panel_date)}</div>
        </div>
        <ApexButton
          variant="secondary"
          size="sm"
          icon={<Trash2 size={12} strokeWidth={2.4} />}
          onClick={() => onDelete(panel.id)}
        >
          {t("labs.private_notes") ? "Delete" /* TODO i18n */ : "Delete"}
        </ApexButton>
      </div>

      {panel.next_eligible_date && (
        <div className="num text-[11px] text-muted">
          Next eligible: <span className="font-semibold text-ink2">{fmtDate(panel.next_eligible_date)}</span>
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
          const tone = toneFor(rangeTone(v, range.low, range.high));
          // Range bars need a non-zero span; fall back to 0–2*value when range is degenerate.
          const barLow = range.low;
          const barHigh = range.high && range.high > range.low ? range.high : (v ?? 0) * 2 || 1;
          return (
            <div key={k} className="rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[12px] font-medium text-ink2">{label}</span>
                <span className="num text-[10px] text-faint">
                  {Number.isInteger(barLow) ? barLow : barLow.toFixed(1)}–{Number.isInteger(barHigh) ? barHigh : barHigh.toFixed(1)} {unit}
                </span>
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="num mono text-[18px] font-bold text-ink">
                  {v === null ? "—" : Number.isInteger(v) ? v : v.toFixed(1)}
                </span>
                <span className="text-[10px] font-medium text-muted">{unit}</span>
                {delta !== null && (
                  <span
                    className={`num ml-auto text-[11px] font-semibold ${
                      delta > 0 ? "text-positiveText" : delta < 0 ? "text-alertText" : "text-muted"
                    }`}
                  >
                    {delta > 0 ? "+" : delta < 0 ? "−" : ""}
                    {Math.abs(delta) < 1 ? Math.abs(delta).toFixed(1) : Math.abs(delta).toFixed(0)} vs prev
                  </span>
                )}
              </div>
              <div className="mt-2">
                <RangeBar value={v} low={barLow} high={barHigh} tone={tone} unit={unit} height={4} />
              </div>
            </div>
          );
        })}
      </div>

      {panel.notes && (
        <>
          <Hairline />
          <div>
            <Eyebrow>{t("labs.private_notes")}</Eyebrow>
            <p className="mt-1 text-[12px] leading-relaxed text-muted">{panel.notes}</p>
          </div>
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
  // Prefill date with today
  const today = new Date().toISOString().slice(0, 10);

  const [panelDate, setPanelDate] = useState(today);
  const [panelType, setPanelType] = useState<"blood_test" | "donation">("blood_test");
  const [donationType, setDonationType] = useState("whole_blood");
  // Pre-fill reference ranges from the user's last panel (defaults otherwise).
  const lastRanges = lastPanel?.reference_ranges ?? DEFAULT_RANGES;
  const [nextEligibleDate, setNextEligibleDate] = useState("");

  // Six core markers — string state (allow empty). Prefill with last values when
  // the form first opens, falling back to empty.
  const initVals = (): Record<string, string> => {
    const out: Record<string, string> = {};
    for (const m of CORE_MARKERS) {
      const v = lastPanel ? markerValue(lastPanel, m.key) : null;
      out[m.key] = v === null ? "" : String(v);
    }
    return out;
  };
  const [vals, setVals] = useState<Record<string, string>>(initVals);
  // Ref-range overrides (string state, prefilled from last panel)
  const [ranges, setRanges] = useState<Record<string, { low: string; high: string }>>(() => {
    const out: Record<string, { low: string; high: string }> = {};
    for (const m of CORE_MARKERS) {
      const r = lastRanges[m.key] ?? DEFAULT_RANGES[m.key];
      out[m.key] = { low: r?.low !== null && r?.low !== undefined ? String(r.low) : "", high: r?.high !== null && r?.high !== undefined ? String(r.high) : "" };
    }
    return out;
  });

  const [extras, setExtras] = useState<ExtraMarkerDraft[]>([]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Re-prefill when lastPanel changes (e.g. after the first ever panel is added).
  useEffect(() => {
    setVals(initVals());
    setRanges(() => {
      const out: Record<string, { low: string; high: string }> = {};
      const lr = lastPanel?.reference_ranges ?? DEFAULT_RANGES;
      for (const m of CORE_MARKERS) {
        const r = lr[m.key] ?? DEFAULT_RANGES[m.key];
        out[m.key] = { low: r?.low !== null && r?.low !== undefined ? String(r.low) : "", high: r?.high !== null && r?.high !== undefined ? String(r.high) : "" };
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

      // Reset just the value fields; keep the ref ranges (they're reusable).
      setVals((s) => Object.fromEntries(Object.keys(s).map((k) => [k, ""])));
      setNotes("");
      setNextEligibleDate("");
      setExtras([]);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader eyebrow={t("labs.add_panel")} title={t("labs.blood_test")} />

      <div className="mt-2 space-y-3">
        {/* Date */}
        <label className="block">
          <span className="text-[11px] font-medium text-muted">{t("labs.panel_date")}</span>
          <input
            type="date"
            value={panelDate}
            onChange={(e) => setPanelDate(e.target.value)}
            className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
          />
        </label>

        {/* Type */}
        <div>
          <span className="text-[11px] font-medium text-muted">{t("labs.panel_type")}</span>
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
          <label className="block">
            <span className="text-[11px] font-medium text-muted">{t("labs.donation_type")}</span>
            <select
              value={donationType}
              onChange={(e) => setDonationType(e.target.value)}
              className="mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
            >
              <option value="whole_blood">Whole blood</option>
              <option value="plasma">Plasma</option>
              <option value="platelets">Platelets</option>
              <option value="double_red_cells">Double red cells</option>
            </select>
          </label>
        )}

        <Hairline />

        {/* Core markers grid */}
        <div className="grid grid-cols-2 gap-2">
          {CORE_MARKERS.map((m: MarkerMeta) => (
            <label key={m.key} className="block">
              <span className="text-[11px] font-medium text-muted">
                {m.label} <span className="text-faint">· {m.unit}</span>
              </span>
              <input
                type="number"
                inputMode="decimal"
                step="any"
                value={vals[m.key]}
                onChange={(e) => setVal(m.key, e.target.value)}
                placeholder="—"
                className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
              />
              <div className="mt-1 grid grid-cols-2 gap-1">
                <input
                  type="number"
                  inputMode="decimal"
                  step="any"
                  value={ranges[m.key].low}
                  onChange={(e) => setRangeLow(m.key, e.target.value)}
                  placeholder="low"
                  className="num rounded-[var(--radius-control)] border border-hairline2 bg-surface2 px-1.5 py-1 text-[11px] text-muted outline-none focus:border-primary"
                  title={t("labs.ref_low")}
                />
                <input
                  type="number"
                  inputMode="decimal"
                  step="any"
                  value={ranges[m.key].high}
                  onChange={(e) => setRangeHigh(m.key, e.target.value)}
                  placeholder="high"
                  className="num rounded-[var(--radius-control)] border border-hairline2 bg-surface2 px-1.5 py-1 text-[11px] text-muted outline-none focus:border-primary"
                  title={t("labs.ref_high")}
                />
              </div>
            </label>
          ))}
        </div>

        {/* Extra markers */}
        {extras.length > 0 && (
          <div className="space-y-2">
            {extras.map((e, i) => (
              <div key={e.key} className="rounded-[var(--radius-control)] border border-hairline2 bg-surface2 p-2">
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={e.label}
                    onChange={(ev) => updateExtra(i, { label: ev.target.value })}
                    placeholder={t("labs.marker_name")}
                    className="num flex-1 rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1 text-[12px] text-ink outline-none focus:border-primary"
                  />
                  <input
                    type="text"
                    value={e.unit}
                    onChange={(ev) => updateExtra(i, { unit: ev.target.value })}
                    placeholder={t("labs.marker_unit")}
                    className="num w-20 rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1 text-[12px] text-ink outline-none focus:border-primary"
                  />
                  <button
                    type="button"
                    onClick={() => removeExtra(i)}
                    className="rounded-[var(--radius-control)] px-1.5 py-1 text-[11px] text-faint hover:bg-surface3 hover:text-alert"
                    aria-label="Remove"
                  >
                    ×
                  </button>
                </div>
                <div className="mt-1 grid grid-cols-3 gap-1">
                  <input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    value={e.value}
                    onChange={(ev) => updateExtra(i, { value: ev.target.value })}
                    placeholder={t("labs.marker_value")}
                    className="num rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1 text-[11px] text-ink outline-none focus:border-primary"
                  />
                  <input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    value={e.ref_low}
                    onChange={(ev) => updateExtra(i, { ref_low: ev.target.value })}
                    placeholder="low"
                    className="num rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1 text-[11px] text-muted outline-none focus:border-primary"
                  />
                  <input
                    type="number"
                    inputMode="decimal"
                    step="any"
                    value={e.ref_high}
                    onChange={(ev) => updateExtra(i, { ref_high: ev.target.value })}
                    placeholder="high"
                    className="num rounded-[var(--radius-control)] border border-hairline bg-surface px-2 py-1 text-[11px] text-muted outline-none focus:border-primary"
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={addExtra}
          className="inline-flex items-center gap-1.5 rounded-[var(--radius-control)] border border-hairline2 bg-surface2 px-2.5 py-1.5 text-[11px] font-medium text-muted hover:bg-surface3 hover:text-ink"
        >
          <Plus size={11} strokeWidth={2.4} />
          {t("labs.add_marker")}
        </button>

        <Hairline />

        {/* Next eligible date */}
        <label className="block">
          <span className="text-[11px] font-medium text-muted">{t("labs.next_eligible")}</span>
          <input
            type="date"
            value={nextEligibleDate}
            onChange={(e) => setNextEligibleDate(e.target.value)}
            className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
          />
        </label>

        {/* Private notes */}
        <label className="block">
          <span className="text-[11px] font-medium text-muted">{t("labs.private_notes")}</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes about this panel…"
            rows={2}
            className="mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[12px] text-ink outline-none focus:border-primary"
          />
        </label>

        <ApexButton onClick={submit} disabled={submitting || !panelDate} className="w-full">
          {submitting ? "Saving…" /* TODO i18n */ : t("labs.add_panel")}
        </ApexButton>
      </div>
    </Card>
  );
}

/* re-export for type-checking */
export type { LabPanel };
