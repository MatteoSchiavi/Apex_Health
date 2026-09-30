"use client";

/**
 * Apex Health — shared component kit (the ONLY place raw visual vocabulary lives).
 * Pages compose these; nothing in a feature folder invents its own card/badge look.
 *
 * Coherence law: typography = Geist + JetBrains Mono; hierarchy = tonal layering
 * + 1px hairlines; color = semantic discipline (blue/positive/alert/warning);
 * numbers = mono + tnum; eyebrows = label-caps.
 */

import Link from "next/link";
import { type CSSProperties, type ReactNode, forwardRef } from "react";
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
  type LucideProps,
} from "lucide-react";

/* ------------------------------------------------------------------ Card */

export function Card({
  children,
  className = "",
  pad = true,
  style,
  onClick,
}: {
  children: ReactNode;
  className?: string;
  pad?: boolean;
  style?: CSSProperties;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`rounded-[var(--radius-card)] border border-hairline bg-surface ${pad ? "p-4" : ""} ${className}`}
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
  className = "",
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  right?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mb-3 flex items-start justify-between gap-3 ${className}`}>
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

/* ------------------------------------------------------------- Big stat */

export function BigStat({
  value,
  unit,
  size = "md",
  className = "",
  tone = "ink",
}: {
  value: ReactNode;
  unit?: ReactNode;
  size?: "md" | "lg" | "xl";
  className?: string;
  tone?: "ink" | "primary" | "positive" | "alert" | "warning" | "muted";
}) {
  const sizes = {
    md: "text-[24px] leading-[30px] font-bold",
    lg: "text-[32px] leading-[38px] font-bold",
    xl: "text-[44px] leading-[50px] font-bold tracking-[-0.03em]",
  } as const;
  const toneCls = {
    ink: "text-ink",
    primary: "text-primaryText",
    positive: "text-positiveText",
    alert: "text-alertText",
    warning: "text-warningText",
    muted: "text-muted",
  }[tone];
  return (
    <div className={`num flex items-baseline gap-1.5 ${toneCls} ${sizes[size]} ${className}`}>
      {value}
      {unit && <span className="text-[12px] font-medium text-muted">{unit}</span>}
    </div>
  );
}

/**
 * StatPod — label-caps eyebrow, oversized numeric readout, optional sub-line.
 */
export function StatPod({
  label,
  value,
  unit,
  sub,
  tone = "ink",
  right,
  className = "",
  onClick,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  sub?: ReactNode;
  tone?: "ink" | "primary" | "positive" | "alert" | "warning";
  right?: ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  const toneCls = {
    ink: "text-ink",
    positive: "text-positiveText",
    alert: "text-alertText",
    warning: "text-warningText",
    primary: "text-primaryText",
  }[tone];
  return (
    <div
      onClick={onClick}
      className={`rounded-[var(--radius-card)] border border-hairline bg-surface2 p-3 ${onClick ? "cursor-pointer hover:border-hairline2" : ""} ${className}`}
    >
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

/** Directional delta chip — green/red by semantic direction. */
export function DeltaChip({
  delta,
  unit,
  goodWhen = "up",
  compact = false,
  suffix,
  showSuffix = true,
}: {
  delta: number | null | undefined;
  unit?: string;
  goodWhen?: "up" | "down" | "none";
  compact?: boolean;
  suffix?: string;
  showSuffix?: boolean;
}) {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return null;
  const positive = delta >= 0;
  const good = goodWhen === "none" ? null : positive === (goodWhen === "up");
  const color = good === null ? "muted" : good ? "positive" : "alert";
  const cls = {
    positive: "text-positiveText bg-positiveSoft",
    alert: "text-alertText bg-alertSoft",
    muted: "text-muted bg-surface3",
  }[color];
  const Icon = positive ? TrendingUp : TrendingDown;
  const abs = Math.abs(delta);
  const text = `${positive ? "+" : "−"}${
    unit === "%" ? `${abs.toFixed(1)}%` : Number.isInteger(abs) ? abs : abs.toFixed(1)
  }${unit && unit !== "%" ? ` ${unit}` : ""}`;
  return (
    <span
      className={`num inline-flex items-center gap-1 rounded-[var(--radius-control)] px-1.5 py-0.5 text-[11px] font-semibold ${cls}`}
    >
      <Icon size={11} strokeWidth={2.4} />
      {text}
      {!compact && showSuffix && suffix && (
        <span className="font-normal opacity-80">{suffix}</span>
      )}
    </span>
  );
}

export function Badge({
  tone = "neutral",
  children,
  className = "",
  dot = false,
}: {
  tone?: "neutral" | "positive" | "alert" | "warning" | "primary";
  children: ReactNode;
  className?: string;
  dot?: boolean;
}) {
  const tones = {
    neutral: "text-muted bg-surface3",
    positive: "text-positiveText bg-positiveSoft",
    alert: "text-alertText bg-alertSoft",
    warning: "text-warningText bg-warningSoft",
    primary: "text-primaryText bg-primarySoft",
  } as const;
  const dotCls = {
    neutral: "bg-muted",
    positive: "bg-positive",
    alert: "bg-alert",
    warning: "bg-warning",
    primary: "bg-primary",
  }[tone];
  return (
    <span
      className={`eyebrow inline-flex items-center gap-1.5 rounded-[var(--radius-control)] px-1.5 py-0.5 !text-[10px] ${tones[tone]} ${className}`}
    >
      {dot && <span className={`inline-block h-1.5 w-1.5 rounded-full ${dotCls}`} />}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------- Score bar */

export function ScoreBar({
  value,
  tone = "primary",
  height = 6,
}: {
  value: number | null;
  tone?: "primary" | "positive" | "warning" | "alert" | "muted";
  height?: number;
}) {
  const colors = {
    primary: "bg-primary",
    positive: "bg-positive",
    warning: "bg-warning",
    alert: "bg-alert",
    muted: "bg-hairline2",
  } as const;
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div
      className="num w-full overflow-hidden rounded-full bg-surface3"
      style={{ height }}
      aria-label={`Score ${value ?? 0} / 100`}
    >
      <div
        className={colors[tone]}
        style={{ width: `${pct}%`, height: "100%", transition: "width 600ms cubic-bezier(0.16,1,0.3,1)" }}
      />
    </div>
  );
}

/* ------------------------------------------------------------- Range bar (low/high) */

export function RangeBar({
  value,
  low,
  high,
  tone = "primary",
  unit,
  height = 4,
}: {
  value: number | null;
  low: number;
  high: number;
  tone?: "primary" | "positive" | "warning" | "alert" | "muted";
  unit?: string;
  height?: number;
}) {
  if (value === null) {
    return <div className="num w-full rounded-full bg-surface3" style={{ height }} />;
  }
  const colors = { primary: "bg-primary", positive: "bg-positive", warning: "bg-warning", alert: "bg-alert", muted: "bg-hairline2" };
  const span = high - low;
  const pct = span <= 0 ? 0 : Math.max(0, Math.min(100, ((value - low) / span) * 100));
  return (
    <div className="num w-full" aria-label={`${value}${unit ? " " + unit : ""} (range ${low}–${high})`}>
      <div className="relative w-full overflow-hidden rounded-full bg-surface3" style={{ height }}>
        <div
          className={colors[tone]}
          style={{ width: `${pct}%`, height: "100%", transition: "width 600ms cubic-bezier(0.16,1,0.3,1)" }}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- Zone bar (HR zones) */

export function ZoneBar({
  segments,
  className = "",
  height = 10,
}: {
  segments: { label: string; value: number; color: string }[];
  className?: string;
  height?: number;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div className={`num flex w-full overflow-hidden rounded-[var(--radius-control)] ${className}`} style={{ height }} aria-hidden>
      {segments.map((s, i) => (
        <div
          key={i}
          style={{ width: `${(s.value / total) * 100}%`, background: s.color, height: "100%" }}
          title={`${s.label}: ${s.value}`}
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------- Sport icon */

const sportIconMap: Record<string, LucideIcon> = {
  cycling: Bike,
  running: Footprints,
  swimming: Waves,
  strength: Dumbbell,
  rowing: Rows,
  hiking: Mountain,
  walking: PersonStanding,
  rest: HeartPulse,
};

export function SportIcon({
  discipline,
  size = 14,
  ...props
}: { discipline: string | null; size?: number } & Omit<LucideProps, "ref">) {
  const Icon = sportIconMap[discipline ?? "rest"] ?? Activity;
  return <Icon size={size} {...props} />;
}

/* ------------------------------------------------------------- Eyebrow label */

export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`eyebrow ${className}`}>{children}</div>;
}

/* ------------------------------------------------------------- Section header */

export function SectionHeader({
  eyebrow,
  title,
  right,
  className = "",
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mb-4 flex items-end justify-between gap-3 ${className}`}>
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        {title && <div className="mt-1 text-[18px] font-semibold tracking-[-0.015em] text-ink">{title}</div>}
      </div>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </div>
  );
}

/* ------------------------------------------------------------- Empty / loading / error */

export function Empty({
  title,
  body,
  action,
  className = "",
}: {
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] border border-dashed border-hairline2 px-6 py-10 text-center ${className}`}>
      <div className="text-[14px] font-semibold text-ink2">{title}</div>
      {body && <div className="max-w-md text-[12px] text-muted">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…", className = "" }: { label?: string; className?: string }) {
  return (
    <div className={`flex items-center gap-3 text-[12px] text-muted ${className}`}>
      <span className="relative flex h-3 w-3">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-40" />
        <span className="relative inline-flex h-3 w-3 rounded-full bg-primary/40" />
      </span>
      {label}
    </div>
  );
}

export function ErrorNote({
  message,
  onRetry,
  className = "",
}: {
  message: ReactNode;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div className={`flex items-center gap-3 rounded-[var(--radius-card)] border border-alert/40 bg-alertSoft px-3 py-2 text-[12px] text-alertText ${className}`}>
      <span className="font-medium">{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="ml-auto rounded-[var(--radius-control)] border border-alert/40 px-2 py-0.5 text-[11px] font-semibold hover:bg-alertSoft"
        >
          Retry
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Source pill */

export function SourcePill({ children }: { children: ReactNode }) {
  return (
    <span className="num inline-flex items-center gap-1 rounded-[var(--radius-control)] bg-surface3 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.06em] text-muted">
      {children}
    </span>
  );
}

/* ------------------------------------------------------------- Back link */

export function BackLink({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 text-[12px] font-medium text-muted transition-colors hover:text-ink"
    >
      <span aria-hidden>←</span>
      {children}
    </button>
  );
}

/* ------------------------------------------------------------- Segmented control */

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className = "",
  size = "md",
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <div
      className={`inline-flex items-center rounded-[var(--radius-control)] border border-hairline bg-surface p-0.5 ${className}`}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`num flex items-center gap-1.5 rounded-[calc(var(--radius-control)-1px)] ${
            size === "sm" ? "h-6 px-2 text-[11px]" : "h-7 px-2.5 text-[12px]"
          } font-medium transition-colors ${
            value === opt.value ? "bg-surface2 text-ink shadow-[0_1px_0_var(--c-hairline)]" : "text-muted hover:text-ink2"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------- Primary / secondary buttons */

export interface ApexButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  icon?: ReactNode;
  iconRight?: ReactNode;
}

export const ApexButton = forwardRef<HTMLButtonElement, ApexButtonProps>(function ApexButton(
  { variant = "primary", size = "md", icon, iconRight, className = "", children, ...props },
  ref
) {
  const sizes = {
    sm: "h-7 px-2.5 text-[11px]",
    md: "h-9 px-3.5 text-[13px]",
    lg: "h-11 px-5 text-[14px]",
  } as const;
  const variants = {
    primary: "bg-primary text-white hover:bg-primary/90 border border-transparent",
    secondary:
      "bg-surface2 text-ink hover:bg-surface3 border border-hairline",
    ghost: "bg-transparent text-muted hover:text-ink hover:bg-surface2 border border-transparent",
    danger: "bg-alert text-white hover:bg-alert/90 border border-transparent",
  } as const;
  return (
    <button
      ref={ref}
      className={`num inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-control)] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${sizes[size]} ${variants[variant]} ${className}`}
      {...props}
    >
      {icon}
      {children}
      {iconRight}
    </button>
  );
});

export function LinkButton({
  href,
  onClick,
  children,
  variant = "primary",
  size = "md",
  className = "",
}: {
  href?: string;
  onClick?: () => void;
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizes = {
    sm: "h-7 px-2.5 text-[11px]",
    md: "h-9 px-3.5 text-[13px]",
    lg: "h-11 px-5 text-[14px]",
  } as const;
  const variants = {
    primary: "bg-primary text-white hover:bg-primary/90 border border-transparent",
    secondary: "bg-surface2 text-ink hover:bg-surface3 border border-hairline",
    ghost: "bg-transparent text-muted hover:text-ink hover:bg-surface2 border border-transparent",
  } as const;
  const cls = `num inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-control)] font-semibold transition-colors ${sizes[size]} ${variants[variant]} ${className}`;
  if (href) {
    return (
      <Link href={href} className={cls}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className={cls}>
      {children}
    </button>
  );
}

/* ------------------------------------------------------------- Sparkline (mini SVG) */

export function Sparkline({
  data,
  color = "var(--c-primary)",
  height = 28,
  width = 100,
  className = "",
}: {
  data: (number | null)[];
  color?: string;
  height?: number;
  width?: number;
  className?: string;
}) {
  const points = data.filter((v): v is number => v !== null && Number.isFinite(v));
  if (points.length < 2) return <div style={{ height, width }} className={className} />;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const stepX = width / (points.length - 1);
  const path = points
    .map((v, i) => {
      const x = i * stepX;
      const y = height - 4 - ((v - min) / range) * (height - 8);
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const lastX = (points.length - 1) * stepX;
  const lastY = height - 4 - ((points.at(-1)! - min) / range) * (height - 8);
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden
    >
      <path d={`${path} L${width},${height} L0,${height} Z`} fill={color} fillOpacity={0.08} stroke="none" />
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastX} cy={lastY} r={2} fill={color} />
    </svg>
  );
}

/* ------------------------------------------------------------- Hairline divider */

export function Hairline({ className = "" }: { className?: string }) {
  return <div className={`h-px w-full bg-hairline ${className}`} />;
}
