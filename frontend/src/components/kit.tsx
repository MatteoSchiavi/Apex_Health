/**
 * Apex Precision component kit v2 — the ONLY place raw styling vocabulary
 * lives. Pages compose these; nothing in a feature folder invents its own
 * card/badge/button look. Coherence law (owner: "be coherent and do not
 * break the flow of the design").
 *
 * v2 vocabulary (approved mockups): PageHeader, StatPod, ArcGauge, ZoneBar,
 * SportIcon, Sparkline, labeled RangeBar. Hierarchy = tonal layering +
 * hairlines; color = semantic discipline only; numbers = mono + tnum.
 */

import { type CSSProperties, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  TrendingDown,
  TrendingUp,
  Activity,
  Bike,
  Dumbbell,
  Footprints,
  HeartPulse,
  Mountain,
  PersonStanding,
  Rows,
  Waves,
  type LucideIcon,
} from "lucide-react";

/* ------------------------------------------------------------------ Card */

export function Card({
  children,
  className = "",
  pad = true,
  style,
}: {
  children: ReactNode;
  className?: string;
  pad?: boolean;
  style?: CSSProperties;
}) {
  return (
    <div
      className={`rounded-lg border border-hairline bg-surface ${pad ? "p-4" : ""} ${className}`}
      style={style}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  eyebrow,
  title,
  right,
  icon,
}: {
  eyebrow?: string;
  title?: ReactNode;
  right?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        {title && (
          <div className="mt-0.5 flex items-center gap-2 truncate text-[15px] font-semibold text-ink">
            {icon}
            {title}
          </div>
        )}
      </div>
      {(right || icon) && (
        <div className="flex shrink-0 items-center gap-2 text-muted">
          {icon}
          {right}
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------- page header */

export function PageHeader({
  title,
  subtitle,
  actions,
  className = "",
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-end justify-between gap-3 ${className}`}>
      <div className="min-w-0">
        <h1 className="page-title">{title}</h1>
        {subtitle && <div className="mt-1 text-[13px] text-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------- Score / stat */

export function BigStat({
  value,
  unit,
  size = "md",
  className = "",
}: {
  value: ReactNode;
  unit?: ReactNode;
  size?: "md" | "lg" | "xl";
  className?: string;
}) {
  const sizes = {
    md: "text-[24px] leading-[30px] font-bold",
    lg: "text-[32px] leading-[38px] font-bold",
    xl: "text-[44px] leading-[50px] font-bold tracking-[-0.03em]",
  } as const;
  return (
    <div className={`num flex items-baseline gap-1.5 text-ink ${sizes[size]} ${className}`}>
      {value}
      {unit && <span className="text-[12px] font-medium text-muted">{unit}</span>}
    </div>
  );
}

/**
 * StatPod — the mockup's metric pod: label-caps eyebrow, oversized mono-ish
 * numeric readout, inline muted unit, optional sub-line and accent tone.
 */
export function StatPod({
  label,
  value,
  unit,
  sub,
  tone = "ink",
  right,
  className = "",
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  sub?: ReactNode;
  tone?: "ink" | "positive" | "alert" | "warning" | "primary";
  right?: ReactNode;
  className?: string;
}) {
  const toneCls = {
    ink: "text-ink",
    positive: "text-positiveText",
    alert: "text-alertText",
    warning: "text-warningText",
    primary: "text-primaryText",
  }[tone];
  return (
    <div className={`rounded-card border border-hairline bg-surface2 p-3 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="eyebrow truncate">{label}</div>
        {right}
      </div>
      <div className={`num mt-1 flex items-baseline gap-1 text-[22px] font-bold leading-7 ${toneCls}`}>
        {value}
        {unit && <span className="text-[10px] font-medium text-muted">{unit}</span>}
      </div>
      {sub && <div className="num mt-0.5 text-[10px] text-faint">{sub}</div>}
    </div>
  );
}

/** Directional delta chip: green up / red down by semantic direction. */
export function DeltaChip({
  delta,
  unit,
  goodWhen = "up",
  compact = false,
  suffix,
}: {
  delta: number | null | undefined;
  unit?: string;
  goodWhen?: "up" | "down" | "none";
  compact?: boolean;
  suffix?: string;
}) {
  const { t } = useTranslation();
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return null;
  const positive = delta >= 0;
  const good = goodWhen === "none" ? null : positive === (goodWhen === "up");
  const color = good === null ? "muted" : good ? "positive" : "alert";
  const cls = {
    positive: "text-positiveText bg-positiveSoft",
    alert: "text-alertText bg-alertSoft",
    muted: "text-muted bg-hairline",
  }[color];
  const Icon = positive ? TrendingUp : TrendingDown;
  const abs = Math.abs(delta);
  const text = `${positive ? "+" : "−"}${
    unit === "%" ? `${abs.toFixed(1)}%` : Number.isInteger(abs) ? abs : abs.toFixed(1)
  }${unit && unit !== "%" ? ` ${unit}` : ""}`;
  return (
    <span
      className={`num inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-semibold ${cls}`}
    >
      <Icon size={11} strokeWidth={2.4} />
      {text}
      {!compact && (
        <span className="font-normal opacity-80">{suffix ?? t("overview.vs7d", { value: "" })}</span>
      )}
    </span>
  );
}

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "positive" | "alert" | "warning" | "primary";
  children: ReactNode;
}) {
  const tones = {
    neutral: "text-muted bg-hairline",
    positive: "text-positiveText bg-positiveSoft",
    alert: "text-alertText bg-alertSoft",
    warning: "text-warningText bg-warningSoft",
    primary: "text-primaryText bg-primarySoft",
  } as const;
  return (
    <span
      className={`eyebrow inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 !text-[10px] ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/** Score gauge bar: 0-100 with a semantic tone. */
export function ScoreBar({
  value,
  tone = "primary",
}: {
  value: number | null;
  tone?: "primary" | "positive" | "warning" | "alert" | "muted";
}) {
  const colors = {
    primary: "bg-primary",
    positive: "bg-positive",
    warning: "bg-warning",
    alert: "bg-alert",
    muted: "bg-hairline2",
  } as const;
  const v = Math.max(0, Math.min(100, value ?? 0));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-hairline">
      <div
        className={`h-full rounded-full transition-all duration-500 ${colors[tone]}`}
        style={{ width: `${v}%` }}
      />
    </div>
  );
}

export function RangeBar({
  min,
  max,
  value,
  marker,
  markers,
  tone = "positive",
  zones,
}: {
  min: number;
  max: number;
  value?: number;
  /** legacy single-marker prop (value dot) */
  marker?: number;
  markers?: { label: ReactNode; at: number; className?: string }[];
  tone?: "positive" | "primary" | "muted";
  /** Background color zones (e.g. green/amber/red health bands). Each
   * segment is rendered as an absolutely-positioned div behind the fill
   * and the marker dot. */
  zones?: { from: number; to: number; color: string }[];
}) {
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100));
  const fill = { positive: "bg-positive/60", primary: "bg-primary/60", muted: "bg-hairline2" }[tone];
  const dots: { at: number; className?: string }[] =
    markers ?? (marker !== undefined ? [{ at: marker }] : []);
  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-hairline">
      {zones?.map((z, i) => (
        <div
          key={`zone-${i}`}
          className="absolute top-0 h-full"
          style={{
            left: `${pct(z.from)}%`,
            width: `${pct(z.to) - pct(z.from)}%`,
            background: z.color,
          }}
        />
      ))}
      {value !== undefined && (
        <div
          className={`absolute h-full rounded-full ${fill}`}
          style={{ left: 0, width: `${pct(value)}%` }}
        />
      )}
      {dots.map((m, i) => (
        <div
          key={i}
          className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-surface bg-ink ${m.className ?? ""}`}
          style={{ left: `${pct(m.at)}%` }}
        />
      ))}
    </div>
  );
}

/**
 * ArcGauge — the mockup's sleep-score arc: 240° sweep, rounded caps,
 * score readout inside, verdict chip below.
 */
export function ArcGauge({
  value,
  size = 150,
  tone = "var(--c-positive)",
  label,
}: {
  value: number | null;
  size?: number;
  tone?: string;
  label?: ReactNode;
}) {
  const v = Math.max(0, Math.min(100, value ?? 0));
  const stroke = 9;
  const r = (size - stroke) / 2 - 2;
  const cx = size / 2;
  const cy = size / 2;
  // 240° arc centered at top (from -210° to +30°)
  const start = (-210 * Math.PI) / 180;
  const end = (30 * Math.PI) / 180;
  const arc = (a0: number, a1: number) => {
    const x0 = cx + r * Math.cos(a0);
    const y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1);
    const y1 = cy + r * Math.sin(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  const t = start + (end - start) * (v / 100);
  return (
    <div className="relative" style={{ width: size, height: size * 0.92 }}>
      <svg
        width={size}
        height={size * 0.92}
        viewBox={`0 0 ${size} ${size * 0.92}`}
        style={{ overflow: "visible" }}
      >
        <g transform={`translate(0 ${-size * 0.04})`}>
          <path d={arc(start, end)} fill="none" stroke="var(--c-hairline)" strokeWidth={stroke} strokeLinecap="round" />
          <path
            d={arc(start, t)}
            fill="none"
            stroke={tone}
            strokeWidth={stroke}
            strokeLinecap="round"
            style={{ transition: "d 500ms" }}
          />
        </g>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pt-1">
        <div className="num flex items-baseline gap-1">
          <span className="text-[40px] font-bold leading-none tracking-[-0.03em] text-ink">
            {value === null ? "—" : Math.round(v)}
          </span>
          <span className="text-[12px] font-medium text-muted">/100</span>
        </div>
        {label && <div className="mt-1.5">{label}</div>}
      </div>
    </div>
  );
}

/**
 * ZoneBar — segmented proportion strip (sleep stages, HR zones): every
 * segment ≥1%, hairline gaps, legend rendered by the caller.
 */
export function ZoneBar({
  parts,
  height = 8,
  gap = 2,
}: {
  parts: { key: string; value: number; color: string; label?: string }[];
  height?: number;
  gap?: number;
}) {
  const total = parts.reduce((a, p) => a + Math.max(0, p.value), 0);
  if (total <= 0) return <div className="h-2 w-full rounded-full bg-hairline" />;
  return (
    <div className="flex w-full overflow-hidden rounded-full" style={{ height, gap }}>
      {parts.map((p) => (
        <div
          key={p.key}
          title={p.label}
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.max(1, (p.value / total) * 100)}%`, background: p.color }}
        />
      ))}
    </div>
  );
}

/** Inline SVG sparkline — hub-card trend without a chart engine. */
export function Sparkline({
  points,
  width = 220,
  height = 40,
  color = "var(--c-primary)",
  fill = true,
}: {
  points: (number | null)[];
  width?: number;
  height?: number;
  color?: string;
  fill?: boolean;
}) {
  const vals = points.filter((v): v is number => v !== null && Number.isFinite(v));
  if (vals.length < 2) return <div style={{ height }} className="rounded-sm bg-hairline/40" />;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  let d = "";
  let started = false;
  points.forEach((p, i) => {
    if (p === null || !Number.isFinite(p)) {
      started = false;
      return;
    }
    const x = i * step;
    const y = height - 3 - ((p - min) / span) * (height - 6);
    d += `${started ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)} `;
    started = true;
  });
  const area = `${d} L ${width} ${height} L 0 ${height} Z`;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {fill && <path d={area} fill={color} opacity={0.1} />}
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* --------------------------------------------------------- sport icons */

const SPORT_ICONS: Record<string, LucideIcon> = {
  running: Footprints,
  road_cycling: Bike,
  gravel_cycling: Bike,
  mountain_biking: Mountain,
  strength: Dumbbell,
  gym_general: Dumbbell,
  yoga: PersonStanding,
  pilates: PersonStanding,
  swimming: Waves,
  rowing: Rows,
  tennis: PersonStanding,
  cardio: HeartPulse,
  walking: Footprints,
  hiking: Mountain,
};

export function SportIcon({ discipline, size = 15, className = "" }: { discipline: string | null | undefined; size?: number; className?: string }) {
  const Icon = (discipline && SPORT_ICONS[discipline]) || Activity;
  return <Icon size={size} strokeWidth={1.8} className={className} />;
}

export function friendlyDiscipline(name: string | null | undefined, t: (k: string) => string): string {
  if (!name) return t("disc.unknown");
  const key = `disc.${name}`;
  const translated = t(key);
  // i18next returns the key itself when missing — fall back to a humanized name
  if (translated === key) return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return translated;
}

/* --------------------------------------------------------------- Controls */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "sm",
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
}) {
  return (
    <div
      className={`inline-flex items-center rounded-control border border-hairline bg-bg p-0.5 ${
        size === "sm" ? "h-8" : "h-10"
      }`}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`num h-full rounded-[3px] px-2.5 text-[12px] font-medium transition-colors ${
            value === o.value
              ? "bg-surface2 text-ink shadow-[0_1px_0_var(--c-hairline)]"
              : "text-muted hover:text-ink2"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled,
  className = "",
  icon,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger" | "subtle";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
  icon?: ReactNode;
}) {
  const variants = {
    primary: "bg-primary text-white hover:brightness-110",
    ghost: "border border-hairline bg-transparent text-ink2 hover:bg-surface3",
    subtle: "bg-hairline text-ink hover:bg-surface3",
    danger: "border border-alert/40 bg-alertSoft text-alertText hover:brightness-110",
  } as const;
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-8 items-center justify-center gap-2 rounded-control px-3 text-[13px] font-medium transition active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}

export function Input({
  value,
  onChange,
  placeholder,
  type = "text",
  label,
  required,
  min,
  max,
  step,
  autoComplete,
  className = "",
}: {
  value: string | number;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  label?: string;
  required?: boolean;
  min?: number;
  max?: number;
  step?: number;
  autoComplete?: string;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      {label && <div className="eyebrow mb-1">{label}</div>}
      <input
        type={type}
        value={value}
        required={required}
        min={min}
        max={max}
        step={step}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-control border border-hairline bg-surface2 px-2.5 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
      />
    </label>
  );
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  label,
  className = "",
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label?: string;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      {label && <div className="eyebrow mb-1">{label}</div>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="h-9 w-full rounded-control border border-hairline bg-surface2 px-2.5 text-[13px] text-ink focus:border-primary focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex items-center gap-2">
      <span
        className={`relative inline-block rounded-full transition-colors ${
          checked ? "bg-primary" : "bg-hairline2"
        }`}
        style={{ height: 18, width: 32 }}
      >
        <span
          className="absolute top-0.5 rounded-full bg-white transition-all"
          style={{ left: checked ? 16 : 2, height: 14, width: 14 }}
        />
      </span>
      {label && <span className="text-[13px] text-ink2">{label}</span>}
    </button>
  );
}

/* --------------------------------------------------------------- states */

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-hairline2 border-t-primary" />
      <span className="text-[13px]">{label ?? t("common.loading")}</span>
    </div>
  );
}

export function ErrorNote({ message }: { message?: string }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-card border border-hairline bg-alertSoft px-4 py-3 text-[13px] text-alertText">
      {message ?? t("common.error")}
    </div>
  );
}

export function Empty({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-14 text-center">
      <div className="max-w-sm text-[13px] text-muted">{children}</div>
      {action}
    </div>
  );
}

/* ------------------------------------------------------------- formatters */

export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtHours(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m ? `${h}h ${String(m).padStart(2, "0")}m` : `${h}h`;
}

export function fmtClock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${m}m`;
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}
