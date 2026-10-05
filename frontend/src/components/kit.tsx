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
    <div className={`panel ${pad ? "p-6" : ""} ${className}`} style={style}>
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
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        {title && (
          <div className="mt-0.5 flex items-center gap-2 text-[17px] font-medium text-ink">
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
    <div
      className={`mb-3 flex flex-wrap items-end justify-between gap-6 ${className}`}
    >
      <div className="min-w-0">
        <h1 className="page-title">{title}</h1>
        {subtitle && (
          <div className="mt-3 max-w-xl text-[14px] text-muted">{subtitle}</div>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Score / stat */

/**
 * Flat metric readout. Values use tabular figures and neutral text.
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
  // Values stay neutral; status belongs to a labeled indicator.
  void tone;
  return (
    <div className={"stat-pod " + className}>
      <div className="flex items-center justify-between gap-2">
        <div className="eyebrow">{label}</div>
        {right}
      </div>
      <div className="stat-value num mt-2">
        {value}
        {unit && (
          <span className="ml-1.5 text-[13px] font-normal tracking-normal text-muted">
            {unit}
          </span>
        )}
      </div>
      {sub && <div className="mt-1 text-[12px] text-muted">{sub}</div>}
    </div>
  );
}

/** Directional delta chip: green up / red down by semantic direction. */
export function DeltaChip({
  delta,
  unit,
  goodWhen = "none",
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
  if (delta === null || delta === undefined || !Number.isFinite(delta))
    return null;
  const positive = delta >= 0;
  const good = goodWhen === "none" ? null : positive === (goodWhen === "up");
  const color = good === null ? "muted" : good ? "positive" : "alert";
  const cls = {
    positive: "text-positiveText bg-positiveSoft",
    alert: "text-alertText bg-alertSoft",
    muted: "text-muted",
  }[color];
  const Icon = positive ? TrendingUp : TrendingDown;
  const abs = Math.abs(delta);
  const text = `${positive ? "+" : "−"}${
    unit === "%"
      ? `${abs.toFixed(1)}%`
      : Number.isInteger(abs)
        ? abs
        : abs.toFixed(1)
  }${unit && unit !== "%" ? ` ${unit}` : ""}`;
  return (
    <span
      className={`num inline-flex items-center gap-1 px-1 py-0.5 text-[12px] font-medium ${cls}`}
    >
      <Icon size={11} strokeWidth={2.4} />
      {text}
      {!compact && (
        <span className="font-normal">
          {suffix ?? t("overview.vs7d", { value: "" })}
        </span>
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
    neutral: "text-muted",
    positive: "text-positiveText",
    alert: "text-alertText",
    warning: "text-warningText",
    primary: "text-ink2",
  };
  return <span className={"status " + tones[tone]}>{children}</span>;
}

/**
 * Proportion strip with exact shares and no invented minimum segments.
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
  if (total <= 0)
    return <div className="h-2 w-full rounded-full bg-hairline" />;
  return (
    <div
      className="flex w-full overflow-hidden rounded-full"
      style={{ height, gap }}
    >
      {parts.map((p) => (
        <div
          key={p.key}
          title={p.label}
          className="h-full rounded-full transition-all"
          style={{
            width: `${(Math.max(0, p.value) / total) * 100}%`,
            background: p.color,
          }}
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
  fill = false,
}: {
  points: (number | null)[];
  width?: number;
  height?: number;
  color?: string;
  fill?: boolean;
}) {
  const vals = points.filter(
    (v): v is number => v !== null && Number.isFinite(v),
  );
  if (vals.length < 2)
    return <div style={{ height }} className="rounded-sm bg-hairline/40" />;
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
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      {fill && <path d={area} fill={color} opacity={0.1} />}
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
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

export function SportIcon({
  discipline,
  size = 15,
  className = "",
}: {
  discipline: string | null | undefined;
  size?: number;
  className?: string;
}) {
  const Icon = (discipline && SPORT_ICONS[discipline]) || Activity;
  return <Icon size={size} strokeWidth={1.8} className={className} />;
}

export function friendlyDiscipline(
  name: string | null | undefined,
  t: (k: string) => string,
): string {
  if (!name) return t("disc.unknown");
  const key = `disc.${name}`;
  const translated = t(key);
  // i18next returns the key itself when missing — fall back to a humanized name
  if (translated === key)
    return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return translated;
}

/* --------------------------------------------------------------- Controls */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "sm",
  disabled = false,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  disabled?: boolean;
}) {
  return (
    <div
      className={`inline-flex items-center rounded-control bg-surface2 p-1 max-w-full overflow-x-auto ${
        size === "sm" ? "h-10" : "h-11"
      }`}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={disabled}
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`num h-full shrink-0 rounded-control px-3 text-[12px] font-medium transition-colors ${
            value === o.value
              ? "bg-surface text-ink"
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
    primary: "bg-ink text-canvas hover:opacity-85",
    ghost: "border border-hairline bg-transparent text-ink2 hover:bg-surface3",
    subtle: "bg-hairline text-ink hover:bg-surface3",
    danger:
      "border border-alert/40 bg-alertSoft text-alertText hover:brightness-110",
  } as const;
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-control px-3 text-[13px] font-medium transition active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
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
  minLength,
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
  minLength?: number;
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
        minLength={minLength}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 w-full rounded-control border border-hairline bg-transparent px-3 text-[13px] text-ink placeholder:text-faint focus:border-primary focus:outline-none"
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
        className="h-11 w-full rounded-control border border-hairline bg-surface px-3 text-[13px] text-ink focus:border-primary focus:outline-none"
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

/* --------------------------------------------------------------- states */

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-3 py-16 text-muted"
    >
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-hairline2 border-t-primary" />
      <span className="text-[13px]">{label ?? t("common.loading")}</span>
    </div>
  );
}

export function ErrorNote({ message }: { message?: string }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="rounded-control bg-alertSoft px-4 py-3 text-[13px] text-alertText"
    >
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
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
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
  if (h > 0)
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtHours(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const totalMinutes = Math.round(seconds / 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return `${h}:${String(m).padStart(2, "0")} h`;
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
