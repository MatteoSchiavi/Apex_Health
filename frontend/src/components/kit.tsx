/**
 * Apex Precision component kit — the ONLY place raw styling vocabulary
 * lives. Pages compose these; nothing in a feature folder invents its own
 * card/badge/button look. Coherence law (owner: "be coherent and do not
 * break the flow of the design").
 */

import { type CSSProperties, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { TrendingDown, TrendingUp } from "lucide-react";

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
          <div className="mt-0.5 truncate text-[15px] font-semibold text-ink">{title}</div>
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

/** Directional delta chip: green up / red down by semantic direction. */
export function DeltaChip({
  delta,
  unit,
  goodWhen = "up",
  compact = false,
}: {
  delta: number | null | undefined;
  unit?: string;
  goodWhen?: "up" | "down" | "none";
  compact?: boolean;
}) {
  const { t } = useTranslation();
  if (delta === null || delta === undefined) return null;
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
      {!compact && <span className="font-normal opacity-80">{t("overview.vs7d", { value: "" })}</span>}
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
      className={`eyebrow inline-flex items-center rounded-sm px-1.5 py-0.5 !text-[10px] ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/** Score gauge bar: 0-100 with a floor/cap context stripe. */
export function ScoreBar({ value, tone = "primary" }: { value: number | null; tone?: "primary" | "positive" | "warning" | "alert" | "muted" }) {
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

/** Horizontal range bar with a value marker (biomarker context strip). */
export function RangeBar({ min, max, value, marker }: { min: number; max: number; value?: number; marker?: number }) {
  const pct = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <div className="relative h-1.5 w-full rounded-full bg-hairline">
      {value !== undefined && (
        <div
          className="absolute h-full rounded-full bg-positive/60"
          style={{ left: `${Math.max(0, pct(value))}%`, right: 0 }}
        />
      )}
      {marker !== undefined && (
        <div
          className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-surface bg-ink"
          style={{ left: `${Math.min(100, Math.max(0, pct(marker)))}%` }}
        />
      )}
    </div>
  );
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
      className={`inline-flex items-center rounded-control border border-hairline bg-surface ${
        size === "sm" ? "h-7" : "h-9"
      }`}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`num h-full rounded-[5px] px-2.5 text-[12px] font-medium transition-colors ${
            value === o.value
              ? "bg-surface3 text-ink"
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
    danger: "bg-alertSoft text-alertText hover:brightness-110",
  } as const;
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-9 items-center justify-center gap-2 rounded-control px-3.5 text-[13px] font-medium transition active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
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
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2"
    >
      <span
        className={`relative inline-block h-4.5 w-8 rounded-full transition-colors ${
          checked ? "bg-primary" : "bg-hairline2"
        }`}
        style={{ height: 18, width: 32 }}
      >
        <span
          className="absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-all"
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

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      <div className="text-[13px] text-muted">{children}</div>
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
  return m ? `${h}${"h"} ${String(m).padStart(2, "0")}m` : `${h}h`;
}
