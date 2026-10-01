"use client";

/**
 * Apex Health — Gear page (plan §6).
 *
 * The page's job: answer "what needs servicing, and how much have I used it?"
 *
 * Layout:
 *   Header: title + subtitle + "Add gear" button (top-right, always visible —
 *     this is the user's specific complaint: "gear page has no button to add
 *     gear").
 *   Row 1, Summary (col-12): three counters — Due now / Due soon / OK. The
 *     first two are tappable filters (clicking "Due now" filters the list to
 *     those items).
 *   Row 2, Gear cards (col-12 md:col-6 xl:col-4): sorted by usage_pct desc,
 *     active items first. Each card shows the binding interval (hours OR km)
 *     as a RangeBar with the binding-tone, an ETA estimate (from
 *     last_service_at pace), last-service line, and three buttons: Log service,
 *     History, and a chevron that expands an inline detail expander with
 *     interval editors, default-for chips, deactivate switch, and Delete.
 *   Empty state: dashed card with a prominent Add gear button.
 *
 * Modals (bottom sheets):
 *   - Add gear (Sheet) — name, type (Segmented), interval hours, interval km,
 *     default-for discipline chips.
 *   - Log service (Sheet) — preset chips + free-text service type, date
 *     (defaults to now), notes. On save → POST /api/gear/[id]/service →
 *     bar resets → toast.
 *   - History (Sheet) — service timeline from /api/gear/[id]/history.
 *
 * All data fetched from /api/gear (GET list, POST create),
 * /api/gear/[id] (PATCH update, DELETE), /api/gear/[id]/service (POST),
 * /api/gear/[id]/history (GET). No new visual vocabulary — composes from the
 * shared kit (Card, PageHeader, StatPod, Badge, RangeBar, ApexButton, Segmented,
 * Empty, Loading, Hairline, Eyebrow, ConfirmPopover, InfoButton).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, History as HistoryIcon, Plus, Wrench, Trash2 } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { useToast } from "@/hooks/use-toast";
import {
  ApexButton,
  Badge,
  Card,
  CardHeader,
  ConfirmPopover,
  Empty,
  Eyebrow,
  Hairline,
  InfoButton,
  Loading,
  PageHeader,
  RangeBar,
} from "@/components/apex/kit";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  GEAR_TYPES,
  SERVICE_PRESETS,
  bindingMetric,
  gearStateTone,
  GEAR_TYPE_ICON,
  type GearTone,
} from "@/lib/apex/gearHelpers";
import { Waves } from "lucide-react";
import { DISCIPLINES, DISCIPLINE_COLORS, disciplineLabel } from "@/lib/apex/disciplines";
import { fmtDate } from "@/lib/apex/format";
import type { Gear, GearServiceLog } from "@/lib/apex/types";

/* ----------------------------------------------------------- types */

type GearRow = Gear;

interface HistoryResponse {
  ok: boolean;
  error?: string;
  service_logs: GearServiceLog[];
  monthly_usage: { month: string; hours: number; km: number }[];
  linked_activities: unknown[];
}

type Filter = "all" | "due_now" | "due_soon" | "ok";

/* ----------------------------------------------------------- ETA helper */

/**
 * Estimate weeks to service from the user's own usage pace since the last
 * service. The plan said "from your usage over the last four weeks" but the
 * activity_gear_links table doesn't exist yet, so we derive the rate from
 * hours_since_service / weeks_since_last_service (or the km equivalent). If
 * `last_service_at` is null, the interval is null, the usage is 0, or the
 * computed rate is non-positive, return null (omit the ETA line).
 */
function etaWeeks(g: GearRow): number | null {
  if (!g.last_service_at) return null;
  const last = new Date(g.last_service_at).getTime();
  if (!Number.isFinite(last)) return null;
  const weeksSince = (Date.now() - last) / (7 * 24 * 3600 * 1000);
  if (weeksSince <= 0.1) return null;

  // Pick the binding metric.
  const metric = bindingMetric(
    g.hours_since_service,
    g.km_since_service,
    g.service_interval_hours,
    g.service_interval_km,
  );
  if (!metric) return null;

  if (metric === "hours") {
    if (!g.service_interval_hours) return null;
    if (g.hours_since_service <= 0) return null;
    const rate = g.hours_since_service / weeksSince; // hours/week
    if (!(rate > 0)) return null;
    const remaining = g.service_interval_hours - g.hours_since_service;
    return remaining / rate;
  }
  // metric === 'km'
  if (!g.service_interval_km) return null;
  if (g.km_since_service <= 0) return null;
  const rate = g.km_since_service / weeksSince; // km/week
  if (!(rate > 0)) return null;
  const remaining = g.service_interval_km - g.km_since_service;
  return remaining / rate;
}

function fmtEta(weeks: number | null): string | null {
  if (weeks === null || !Number.isFinite(weeks)) return null;
  if (weeks <= 0) return "due now";
  if (weeks < 1.5) return "about 1 week at your current pace";
  if (weeks > 52) return "more than a year at your current pace";
  const rounded = Math.round(weeks);
  return `about ${rounded} weeks at your current pace`;
}

/* ----------------------------------------------------------- shared bits */

const TONE_BADGE: Record<GearTone, "alert" | "warning" | "positive" | "neutral"> = {
  alert: "alert",
  warning: "warning",
  positive: "positive",
  muted: "neutral",
};

const TONE_RANGE: Record<GearTone, "alert" | "warning" | "positive" | "muted"> = {
  alert: "alert",
  warning: "warning",
  positive: "positive",
  muted: "muted",
};

/* ----------------------------------------------------------- Page */

export function GearPage() {
  const t = useT();
  const ui = useApexUi();
  const { toast } = useToast();

  const [gear, setGear] = useState<GearRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  // Modal state
  const [addOpen, setAddOpen] = useState(false);
  const [logFor, setLogFor] = useState<GearRow | null>(null);
  const [historyFor, setHistoryFor] = useState<GearRow | null>(null);

  // Expanded inline detail (one card at a time)
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // -- fetch list -------------------------------------------------------------

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/gear");
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to load gear");
      setGear((data.gear as GearRow[]) ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load gear");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // -- derived ----------------------------------------------------------------

  const counts = useMemo(() => {
    let dueNow = 0;
    let dueSoon = 0;
    let ok = 0;
    for (const g of gear) {
      if (!g.active) continue;
      if (g.usage_pct >= 100) dueNow += 1;
      else if (g.usage_pct >= 80) dueSoon += 1;
      else ok += 1;
    }
    return { dueNow, dueSoon, ok };
  }, [gear]);

  const visible = useMemo(() => {
    if (filter === "all") return gear;
    return gear.filter((g) => {
      if (filter === "due_now") return g.active && g.usage_pct >= 100;
      if (filter === "due_soon") return g.active && g.usage_pct >= 80 && g.usage_pct < 100;
      // ok
      return g.active && g.usage_pct < 80;
    });
  }, [gear, filter]);

  // -- actions ----------------------------------------------------------------

  const onLogService = async (
    g: GearRow,
    payload: { service_type: string; performed_at: string; notes: string },
  ) => {
    try {
      const res = await fetch(`/api/gear/${g.id}/service`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to log service");
      const updated: GearRow = data.gear;
      setGear((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      toast({
        title: t("gear.log_service") + " ✓",
        description: `${updated.name} · ${payload.service_type}`,
      });
      setLogFor(null);
    } catch (e) {
      toast({
        title: "Could not log service",
        description: e instanceof Error ? e.message : "",
      });
    }
  };

  const onUpdateGear = async (id: number, patch: Record<string, unknown>) => {
    try {
      const res = await fetch(`/api/gear/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to update gear");
      const updated: GearRow = data.gear;
      setGear((prev) => {
        const next = prev.map((x) => (x.id === updated.id ? updated : x));
        // Keep active-first + usage_pct desc ordering stable.
        next.sort((a, b) => {
          if (a.active !== b.active) return a.active ? -1 : 1;
          return b.usage_pct - a.usage_pct;
        });
        return next;
      });
      return updated;
    } catch (e) {
      toast({
        title: "Update failed",
        description: e instanceof Error ? e.message : "",
      });
      return null;
    }
  };

  const onDeleteGear = async (id: number) => {
    try {
      const res = await fetch(`/api/gear/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to delete gear");
      setGear((prev) => prev.filter((x) => x.id !== id));
      toast({ title: "Gear deleted" });
    } catch (e) {
      toast({
        title: "Delete failed",
        description: e instanceof Error ? e.message : "",
      });
    }
  };

  // -- render -----------------------------------------------------------------

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("nav.gear")}
        subtitle={t("gear.subtitle")}
        actions={
          <ApexButton
            variant="primary"
            size="md"
            icon={<Plus size={14} strokeWidth={2.4} />}
            onClick={() => setAddOpen(true)}
          >
            {t("gear.add_gear")}
          </ApexButton>
        }
      />

      {/* Row 1 — summary counters (tappable filters for due_now / due_soon) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SummaryCounter
          label={t("gear.summary_due_now")}
          value={counts.dueNow}
          tone="alert"
          active={filter === "due_now"}
          onClick={() => setFilter(filter === "due_now" ? "all" : "due_now")}
        />
        <SummaryCounter
          label={t("gear.summary_due_soon")}
          value={counts.dueSoon}
          tone="warning"
          active={filter === "due_soon"}
          onClick={() => setFilter(filter === "due_soon" ? "all" : "due_soon")}
        />
        <SummaryCounter
          label={t("gear.summary_ok")}
          value={counts.ok}
          tone="positive"
          active={filter === "ok"}
          onClick={() => setFilter(filter === "ok" ? "all" : "ok")}
        />
      </div>

      {/* Active filter banner */}
      {filter !== "all" && (
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <span>
            Filter:{" "}
            <span className="font-semibold text-ink2">
              {filter === "due_now"
                ? t("gear.summary_due_now")
                : filter === "due_soon"
                  ? t("gear.summary_due_soon")
                  : t("gear.summary_ok")}
            </span>
          </span>
          <button
            type="button"
            onClick={() => setFilter("all")}
            className="rounded-[var(--radius-control)] border border-hairline bg-surface2 px-2 py-0.5 text-[11px] font-semibold text-muted transition-colors hover:text-ink"
          >
            Clear
          </button>
        </div>
      )}

      {/* Row 2 — gear cards */}
      {loading ? (
        <Card>
          <Loading label="Loading gear…" />
        </Card>
      ) : error ? (
        <Card>
          <div className="text-[13px] text-alertText">{error}</div>
          <ApexButton variant="secondary" size="sm" className="mt-3" onClick={reload}>
            Retry
          </ApexButton>
        </Card>
      ) : gear.length === 0 ? (
        <Empty
          title={t("gear.empty_title")}
          body={t("gear.empty_body")}
          action={
            <ApexButton
              variant="primary"
              size="md"
              icon={<Plus size={14} strokeWidth={2.4} />}
              onClick={() => setAddOpen(true)}
            >
              {t("gear.add_first")}
            </ApexButton>
          }
        />
      ) : visible.length === 0 ? (
        <Empty title={t("gear.empty_title")} body="No gear matches this filter." />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((g) => (
            <GearCard
              key={g.id}
              g={g}
              t={t}
              expanded={expandedId === g.id}
              onToggleExpand={() =>
                setExpandedId((prev) => (prev === g.id ? null : g.id))
              }
              onLog={() => setLogFor(g)}
              onHistory={() => setHistoryFor(g)}
              onUpdate={(patch) => onUpdateGear(g.id, patch)}
              onDelete={() => onDeleteGear(g.id)}
              onSelect={() => ui.selectGear(g.id)}
            />
          ))}
        </div>
      )}

      {/* Add gear sheet */}
      <AddGearSheet
        open={addOpen}
        onOpenChange={setAddOpen}
        t={t}
        onCreated={(g) => {
          setGear((prev) => {
            const next = [...prev, g];
            next.sort((a, b) => {
              if (a.active !== b.active) return a.active ? -1 : 1;
              return b.usage_pct - a.usage_pct;
            });
            return next;
          });
          setAddOpen(false);
          toast({ title: "Gear added", description: g.name });
        }}
      />

      {/* Log service sheet */}
      <LogServiceSheet
        open={!!logFor}
        onOpenChange={(o) => !o && setLogFor(null)}
        t={t}
        gear={logFor}
        onSave={onLogService}
      />

      {/* History sheet */}
      <HistorySheet
        open={!!historyFor}
        onOpenChange={(o) => !o && setHistoryFor(null)}
        t={t}
        gear={historyFor}
      />
    </div>
  );
}

/* ----------------------------------------------------------- Summary counter */

function SummaryCounter({
  label,
  value,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: number;
  tone: GearTone;
  active: boolean;
  onClick: () => void;
}) {
  const toneCls: Record<GearTone, string> = {
    alert: "text-alertText",
    warning: "text-warningText",
    positive: "text-positiveText",
    muted: "text-muted",
  };
  const dotCls: Record<GearTone, string> = {
    alert: "bg-alert",
    warning: "bg-warning",
    positive: "bg-positive",
    muted: "bg-hairline2",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className={`num flex items-center justify-between rounded-[var(--radius-card)] border bg-surface px-4 py-3 text-left transition-colors ${
        active ? "border-primary" : "border-hairline hover:border-hairline2"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${dotCls[tone]}`} aria-hidden />
        <span className="eyebrow">{label}</span>
      </div>
      <div className={`text-[24px] font-bold tabular-nums ${toneCls[tone]}`}>{value}</div>
    </button>
  );
}

/* ----------------------------------------------------------- Gear card */

function GearCard({
  g,
  t,
  expanded,
  onToggleExpand,
  onLog,
  onHistory,
  onUpdate,
  onDelete,
  onSelect,
}: {
  g: GearRow;
  t: (p: string, vars?: Record<string, string | number>) => string;
  expanded: boolean;
  onToggleExpand: () => void;
  onLog: () => void;
  onHistory: () => void;
  onUpdate: (patch: Record<string, unknown>) => Promise<GearRow | null>;
  onDelete: () => void;
  onSelect: () => void;
}) {
  const tone = gearStateTone(g.usage_pct);
  const metric = bindingMetric(
    g.hours_since_service,
    g.km_since_service,
    g.service_interval_hours,
    g.service_interval_km,
  );
  const TypeIcon = GEAR_TYPE_ICON[g.gear_type] ?? Waves;

  // Numeric readout for the binding interval.
  let barValue: number | null = null;
  let barLow = 0;
  let barHigh = 1;
  let barUnit: string | undefined;
  let usageLabel = "";
  if (metric === "hours" && g.service_interval_hours) {
    barHigh = g.service_interval_hours;
    barValue = g.hours_since_service;
    barUnit = "h";
    usageLabel = t("gear.usage", {
      hours: g.hours_since_service.toFixed(1),
      interval: g.service_interval_hours,
      pct: Math.round(g.usage_pct),
    });
  } else if (metric === "km" && g.service_interval_km) {
    barHigh = g.service_interval_km;
    barValue = g.km_since_service;
    barUnit = "km";
    usageLabel = t("gear.usage_km", {
      km: g.km_since_service.toFixed(0),
      interval: g.service_interval_km,
      pct: Math.round(g.usage_pct),
    });
  } else {
    // No interval set — show a faint muted bar.
    barValue = null;
    usageLabel = `${g.usage_pct.toFixed(0)}%`;
  }

  const etaText = fmtEta(etaWeeks(g));

  return (
    <Card pad className={`flex flex-col gap-3 ${g.active ? "" : "opacity-60"}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 items-center gap-2.5 text-left"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-surface2 text-ink2">
            <TypeIcon size={16} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-[14px] font-semibold text-ink">{g.name}</div>
            <div className="truncate text-[11px] text-muted">
              {t(`gear.type_options.${g.gear_type}`) || g.gear_type}
              {g.brand ? ` · ${g.brand}` : ""}
            </div>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge tone={TONE_BADGE[tone]} dot>
            {Math.round(g.usage_pct)}%
          </Badge>
          {!g.active && <Badge tone="neutral">Inactive</Badge>}
        </div>
      </div>

      {/* Binding interval bar */}
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <div className="num text-[13px] font-semibold text-ink2">{usageLabel}</div>
          <div className="eyebrow text-faint">
            {metric === "hours" ? "Hours" : metric === "km" ? "Distance" : ""}
          </div>
        </div>
        <div className="mt-2">
          <RangeBar
            value={barValue}
            low={barLow}
            high={barHigh}
            tone={TONE_RANGE[tone]}
            unit={barUnit}
            height={6}
          />
        </div>
        {etaText && (
          <div className="mt-2 text-[11px] text-muted">{etaText}</div>
        )}
      </div>

      <Hairline />

      {/* Last service */}
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="eyebrow">{t("gear.last_service")}</span>
        <span className="num text-muted">
          {g.last_service_type ? (
            <>
              <span className="text-ink2">
                {t(`gear.service_presets.${g.last_service_type}`) || g.last_service_type}
              </span>
              {g.last_service_at ? ` · ${fmtDate(g.last_service_at)}` : ""}
            </>
          ) : (
            "—"
          )}
        </span>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <ApexButton
          variant={tone === "alert" ? "primary" : "secondary"}
          size="sm"
          icon={<Wrench size={12} strokeWidth={2.4} />}
          onClick={onLog}
          className="flex-1"
        >
          {t("gear.log_service")}
        </ApexButton>
        <ApexButton
          variant="ghost"
          size="sm"
          icon={<HistoryIcon size={12} strokeWidth={2.4} />}
          onClick={onHistory}
        >
          {t("gear.history")}
        </ApexButton>
        <ApexButton
          variant="ghost"
          size="sm"
          onClick={onToggleExpand}
          aria-label={expanded ? "Collapse" : "Expand"}
          icon={
            expanded ? <ChevronUp size={14} strokeWidth={2.4} /> : <ChevronDown size={14} strokeWidth={2.4} />
          }
        />
      </div>

      {/* Inline detail expander */}
      {expanded && (
        <GearDetailExpander g={g} t={t} onUpdate={onUpdate} onDelete={onDelete} />
      )}
    </Card>
  );
}

/* ----------------------------------------------------------- Detail expander */

function GearDetailExpander({
  g,
  t,
  onUpdate,
  onDelete,
}: {
  g: GearRow;
  t: (p: string, vars?: Record<string, string | number>) => string;
  onUpdate: (patch: Record<string, unknown>) => Promise<GearRow | null>;
  onDelete: () => void;
}) {
  const [hours, setHours] = useState<string>(
    g.service_interval_hours ? String(g.service_interval_hours) : "",
  );
  const [km, setKm] = useState<string>(
    g.service_interval_km ? String(g.service_interval_km) : "",
  );
  const [defaults, setDefaults] = useState<string[]>(g.default_for ?? []);
  const [active, setActive] = useState<boolean>(g.active);
  const [saving, setSaving] = useState(false);

  const toggleDefault = (d: string) => {
    setDefaults((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const handleSave = async () => {
    setSaving(true);
    const patch: Record<string, unknown> = {
      service_interval_hours: hours.trim() === "" ? null : Number(hours),
      service_interval_km: km.trim() === "" ? null : Number(km),
      default_for: defaults,
      active,
    };
    await onUpdate(patch);
    setSaving(false);
  };

  const handleActiveToggle = async (next: boolean) => {
    setActive(next);
    await onUpdate({ active: next });
  };

  return (
    <div className="mt-2 space-y-4 rounded-[var(--radius-card)] border border-hairline2 bg-surface2 p-4">
      {/* Intervals */}
      <div>
        <div className="eyebrow mb-2">Intervals</div>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[11px] font-medium text-muted">{t("gear.interval_hours")}</span>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={hours}
              onChange={(e) => setHours(e.target.value)}
              placeholder="—"
              className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-medium text-muted">{t("gear.interval_km")}</span>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={km}
              onChange={(e) => setKm(e.target.value)}
              placeholder="—"
              className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
            />
          </label>
        </div>
      </div>

      {/* Default for disciplines */}
      <div>
        <div className="eyebrow mb-2">{t("gear.default_for")}</div>
        <div className="flex flex-wrap gap-1.5">
          {DISCIPLINES.map((d) => {
            const on = defaults.includes(d);
            return (
              <button
                key={d}
                type="button"
                onClick={() => toggleDefault(d)}
                className={`num inline-flex items-center gap-1.5 rounded-[var(--radius-control)] border px-2 py-1 text-[11px] font-medium transition-colors ${
                  on
                    ? "border-primary bg-primarySoft text-primaryText"
                    : "border-hairline bg-surface text-muted hover:text-ink2"
                }`}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ background: DISCIPLINE_COLORS[d] ?? "var(--c-hairline2)" }}
                  aria-hidden
                />
                {disciplineLabel(d)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Active + delete */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-medium text-ink2">{t("gear.active")}</span>
          <Switch checked={active} onCheckedChange={handleActiveToggle} aria-label={t("gear.active")} />
          {!active && <span className="text-[11px] text-muted">({t("gear.deactivate")})</span>}
        </div>
        <div className="flex items-center gap-2">
          <ApexButton
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save"}
          </ApexButton>
          <ConfirmPopover
            message={`Delete ${g.name}? This also removes its service log.`}
            onConfirm={onDelete}
            onCancel={() => {}}
            confirmLabel="Delete"
            cancelLabel="Cancel"
          >
            <ApexButton variant="ghost" size="sm" icon={<Trash2 size={12} strokeWidth={2.4} />}>
              Delete
            </ApexButton>
          </ConfirmPopover>
        </div>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- Add gear sheet */

function AddGearSheet({
  open,
  onOpenChange,
  t,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
  onCreated: (g: GearRow) => void;
}) {
  const [name, setName] = useState("");
  const [gearType, setGearType] = useState<string>(GEAR_TYPES[0]);
  const [hours, setHours] = useState("");
  const [km, setKm] = useState("");
  const [defaults, setDefaults] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setGearType(GEAR_TYPES[0]);
      setHours("");
      setKm("");
      setDefaults([]);
      setErr(null);
    }
  }, [open]);

  const toggleDefault = (d: string) => {
    setDefaults((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const handleSave = async () => {
    setSaving(true);
    setErr(null);
    try {
      const res = await fetch("/api/gear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          gear_type: gearType,
          service_interval_hours: hours.trim() === "" ? null : Number(hours),
          service_interval_km: km.trim() === "" ? null : Number(km),
          default_for: defaults,
        }),
      });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "Failed to add gear");
      onCreated(data.gear as GearRow);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to add gear");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[88vh] gap-0 overflow-y-auto p-0">
        <SheetHeader className="border-b border-hairline">
          <SheetTitle className="text-[15px] font-semibold text-ink">{t("gear.add_gear")}</SheetTitle>
          <SheetDescription className="text-[12px] text-muted">
            {t("gear.empty_body")}
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-4 p-4">
          {/* Name */}
          <div>
            <label className="eyebrow block">{t("gear.name")}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Specialized Turbo Kenevo"
              className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[14px] text-ink outline-none focus:border-primary"
            />
          </div>

          {/* Type */}
          <div>
            <label className="eyebrow block">{t("gear.gear_type")}</label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {GEAR_TYPES.map((gt) => {
                const Icon = GEAR_TYPE_ICON[gt] ?? Waves;
                const on = gt === gearType;
                return (
                  <button
                    key={gt}
                    type="button"
                    onClick={() => setGearType(gt)}
                    className={`inline-flex items-center gap-1.5 rounded-[var(--radius-control)] border px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                      on
                        ? "border-primary bg-primarySoft text-primaryText"
                        : "border-hairline bg-surface2 text-muted hover:text-ink2"
                    }`}
                  >
                    <Icon size={14} />
                    {t(`gear.type_options.${gt}`)}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Intervals */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="eyebrow block">{t("gear.interval_hours")}</label>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={hours}
                onChange={(e) => setHours(e.target.value)}
                placeholder="—"
                className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[14px] text-ink outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="eyebrow block">{t("gear.interval_km")}</label>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={km}
                onChange={(e) => setKm(e.target.value)}
                placeholder="—"
                className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[14px] text-ink outline-none focus:border-primary"
              />
            </div>
          </div>

          {/* Default for */}
          <div>
            <div className="flex items-center gap-1.5">
              <label className="eyebrow">{t("gear.default_for")}</label>
              <InfoButton title={t("gear.default_for")}>
                <div>
                  Pick the disciplines this gear is your default for. Used to estimate service pace.
                </div>
              </InfoButton>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {DISCIPLINES.map((d) => {
                const on = defaults.includes(d);
                return (
                  <button
                    key={d}
                    type="button"
                    onClick={() => toggleDefault(d)}
                    className={`num inline-flex items-center gap-1.5 rounded-[var(--radius-control)] border px-2 py-1 text-[11px] font-medium transition-colors ${
                      on
                        ? "border-primary bg-primarySoft text-primaryText"
                        : "border-hairline bg-surface2 text-muted hover:text-ink2"
                    }`}
                  >
                    <span
                      className="inline-block h-1.5 w-1.5 rounded-full"
                      style={{ background: DISCIPLINE_COLORS[d] ?? "var(--c-hairline2)" }}
                      aria-hidden
                    />
                    {disciplineLabel(d)}
                  </button>
                );
              })}
            </div>
          </div>

          {err && <div className="text-[12px] text-alertText">{err}</div>}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-hairline p-4">
          <ApexButton variant="ghost" size="md" onClick={() => onOpenChange(false)}>
            Cancel
          </ApexButton>
          <ApexButton
            variant="primary"
            size="md"
            onClick={handleSave}
            disabled={saving || !name.trim()}
          >
            {saving ? "Adding…" : t("gear.add_gear")}
          </ApexButton>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ----------------------------------------------------------- Log service sheet */

function LogServiceSheet({
  open,
  onOpenChange,
  t,
  gear,
  onSave,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
  gear: GearRow | null;
  onSave: (
    g: GearRow,
    payload: { service_type: string; performed_at: string; notes: string },
  ) => Promise<void>;
}) {
  const [serviceType, setServiceType] = useState("");
  const [performedAt, setPerformedAt] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setServiceType("");
      setPerformedAt(new Date().toISOString().slice(0, 10));
      setNotes("");
      setErr(null);
    }
  }, [open]);

  const pickPreset = (preset: string) => {
    setServiceType(t(`gear.service_presets.${preset}`));
  };

  const handleSave = async () => {
    if (!gear) return;
    if (!serviceType.trim()) {
      setErr("Service type is required");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const iso = performedAt
        ? new Date(performedAt + "T00:00:00").toISOString()
        : new Date().toISOString();
      await onSave(gear, {
        service_type: serviceType.trim(),
        performed_at: iso,
        notes: notes.trim(),
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to log service");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[88vh] gap-0 overflow-y-auto p-0">
        <SheetHeader className="border-b border-hairline">
          <SheetTitle className="text-[15px] font-semibold text-ink">
            {t("gear.log_service")}
            {gear ? ` · ${gear.name}` : ""}
          </SheetTitle>
          <SheetDescription className="text-[12px] text-muted">
            Records a service and resets the usage counters to zero.
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-4 p-4">
          {/* Service type presets */}
          <div>
            <label className="eyebrow block">{t("gear.service_type")}</label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {SERVICE_PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => pickPreset(p)}
                  className="rounded-[var(--radius-control)] border border-hairline bg-surface2 px-2.5 py-1.5 text-[12px] font-medium text-muted transition-colors hover:text-ink2"
                >
                  {t(`gear.service_presets.${p}`)}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={serviceType}
              onChange={(e) => setServiceType(e.target.value)}
              placeholder="Or type your own…"
              className="num mt-2 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[14px] text-ink outline-none focus:border-primary"
            />
          </div>

          {/* Date */}
          <div>
            <label className="eyebrow block">{t("gear.service_date")}</label>
            <input
              type="date"
              value={performedAt}
              onChange={(e) => setPerformedAt(e.target.value)}
              className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[14px] text-ink outline-none focus:border-primary"
            />
          </div>

          {/* Notes */}
          <div>
            <label className="eyebrow block">{t("gear.service_notes")}</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Optional notes…"
              className="mt-1 w-full resize-none rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-primary"
            />
          </div>

          {err && <div className="text-[12px] text-alertText">{err}</div>}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-hairline p-4">
          <ApexButton variant="ghost" size="md" onClick={() => onOpenChange(false)}>
            Cancel
          </ApexButton>
          <ApexButton
            variant="primary"
            size="md"
            onClick={handleSave}
            disabled={saving || !serviceType.trim()}
          >
            {saving ? "Saving…" : t("gear.log_service")}
          </ApexButton>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ----------------------------------------------------------- History sheet */

function HistorySheet({
  open,
  onOpenChange,
  t,
  gear,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
  gear: GearRow | null;
}) {
  const [logs, setLogs] = useState<GearServiceLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !gear) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    (async () => {
      try {
        const res = await fetch(`/api/gear/${gear.id}/history`);
        const data: HistoryResponse = await res.json();
        if (cancelled) return;
        if (!data?.ok) throw new Error(data?.error || "Failed to load history");
        setLogs(data.service_logs);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load history");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, gear]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[88vh] gap-0 overflow-y-auto p-0">
        <SheetHeader className="border-b border-hairline">
          <SheetTitle className="text-[15px] font-semibold text-ink">
            {t("gear.history")}
            {gear ? ` · ${gear.name}` : ""}
          </SheetTitle>
          <SheetDescription className="text-[12px] text-muted">
            Service timeline for this gear.
          </SheetDescription>
        </SheetHeader>
        <div className="p-4">
          {loading ? (
            <Loading label="Loading history…" />
          ) : err ? (
            <div className="text-[12px] text-alertText">{err}</div>
          ) : logs.length === 0 ? (
            <Empty title={t("gear.no_services")} />
          ) : (
            <ol className="space-y-3">
              {logs.map((l) => (
                <li key={l.id} className="relative pl-5">
                  {/* timeline dot */}
                  <span
                    className="absolute left-0 top-1.5 inline-block h-2 w-2 rounded-full bg-primary"
                    aria-hidden
                  />
                  {/* vertical line */}
                  <span
                    className="absolute left-[3px] top-3 h-full w-px bg-hairline"
                    aria-hidden
                  />
                  <div className="text-[13px] font-semibold text-ink">
                    {t(`gear.service_presets.${l.service_type}`) || l.service_type}
                  </div>
                  <div className="num text-[11px] text-muted">
                    {fmtDate(l.performed_at)}
                  </div>
                  {l.notes && (
                    <div className="mt-1 text-[12px] text-muted">{l.notes}</div>
                  )}
                </li>
              ))}
            </ol>
          )}
          {logs.length > 0 && (
            <>
              <Hairline className="my-4" />
              <div className="flex items-center gap-1.5">
                <Eyebrow>Monthly usage</Eyebrow>
                <InfoButton title="Monthly usage">
                  <div>
                    Plan §6 calls for monthly hours/km bars derived from activity-gear
                    links. That linkage table isn&apos;t built yet, so the bar chart is
                    deferred.
                  </div>
                </InfoButton>
              </div>
              <div className="mt-2 text-[12px] text-muted">{t("gear.no_linked_activities")}</div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
