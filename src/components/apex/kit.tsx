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
import { type CSSProperties, type ReactNode, forwardRef, useState } from "react";
import {
  TrendingDown,
  TrendingUp,
  Activity,
  Bike,
  Dumbbell,
  Footprints,
  HeartPulse,
  Info,
  Mountain,
  PersonStanding,
  Rows,
  Sailboat,
  Ship,
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
      className={`rounded-[var(--radius-card)] border border-hairline bg-surface ${pad ? "p-6" : ""} ${className}`}
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
    md: "text-[28px] leading-[34px] font-bold tracking-[-0.02em]",
    lg: "text-[40px] leading-[46px] font-bold tracking-[-0.02em]",
    xl: "text-[56px] leading-[62px] font-bold tracking-[-0.03em]",
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
  sailing: Sailboat,
  boating: Ship,
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

/** Skeleton placeholder for loading state. Subtle pulse, preserves page geometry. */
export function Skeleton({
  className = "",
  width = "100%",
  height = 16,
  rounded = "var(--radius-control)",
}: {
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: string;
}) {
  return (
    <div
      className={`animate-pulse bg-surface3 ${className}`}
      style={{ width, height, borderRadius: rounded }}
      aria-hidden
    />
  );
}

/** Skeleton block that mimics a card with a header + 3 rows. */
export function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div className={`rounded-[var(--radius-card)] border border-hairline bg-surface p-4 ${className}`}>
      <Skeleton width={120} height={12} />
      <div className="mt-3 space-y-2">
        <Skeleton width="100%" height={20} />
        <Skeleton width="80%" height={20} />
        <Skeleton width="60%" height={20} />
      </div>
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

/* ------------------------------------------------------------- Stepper (plan §2 live session) */

export function Stepper({
  value,
  onChange,
  step = 1,
  min = 0,
  max = 9999,
  suffix,
  className = "",
}: {
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
  suffix?: string;
  className?: string;
}) {
  const clamp = (v: number) => Math.max(min, Math.min(max, v));
  return (
    <div className={`inline-flex items-center rounded-[var(--radius-control)] border border-hairline bg-surface ${className}`}>
      <button
        type="button"
        onClick={() => onChange(clamp(value - step))}
        className="flex h-9 w-9 items-center justify-center text-[18px] font-bold text-muted transition-colors hover:bg-surface2 hover:text-ink"
        aria-label="decrement"
      >
        −
      </button>
      <div className="num flex min-w-[3rem] items-baseline justify-center gap-0.5 px-1 text-[18px] font-bold tabular-nums text-ink">
        {value}
        {suffix && <span className="text-[10px] font-medium text-muted">{suffix}</span>}
      </div>
      <button
        type="button"
        onClick={() => onChange(clamp(value + step))}
        className="flex h-9 w-9 items-center justify-center text-[18px] font-bold text-muted transition-colors hover:bg-surface2 hover:text-ink"
        aria-label="increment"
      >
        +
      </button>
    </div>
  );
}

/* ------------------------------------------------------------- Rest timer ring (plan §2) */

export function RestTimerRing({
  secondsLeft,
  total,
  onAdjust,
  onSkip,
  className = "",
}: {
  secondsLeft: number;
  total: number;
  onAdjust: (delta: number) => void;
  onSkip: () => void;
  className?: string;
}) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const pct = total > 0 ? secondsLeft / total : 0;
  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      <div className="relative">
        <svg width="128" height="128" viewBox="0 0 128 128" aria-hidden>
          <circle cx="64" cy="64" r={r} fill="none" stroke="var(--c-surface3)" strokeWidth="6" />
          <circle
            cx="64"
            cy="64"
            r={r}
            fill="none"
            stroke="var(--c-primary)"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - pct)}
            transform="rotate(-90 64 64)"
            style={{ transition: "stroke-dashoffset 1s linear" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="num text-[32px] font-bold tabular-nums text-ink">
            {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")}
          </div>
          <div className="eyebrow !text-[9px] text-faint">rest</div>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => onAdjust(-15)}
          className="num h-7 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 text-[11px] font-semibold text-muted transition-colors hover:bg-surface2 hover:text-ink"
        >
          −15s
        </button>
        <button
          type="button"
          onClick={() => onAdjust(15)}
          className="num h-7 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 text-[11px] font-semibold text-muted transition-colors hover:bg-surface2 hover:text-ink"
        >
          +15s
        </button>
        <button
          type="button"
          onClick={onSkip}
          className="h-7 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 text-[11px] font-semibold text-muted transition-colors hover:bg-surface2 hover:text-ink"
        >
          Skip
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- Confirm popover (plan §1 delete chat) */

export function ConfirmPopover({
  message,
  onConfirm,
  onCancel,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  children,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <div onClick={() => setOpen((o) => !o)}>{children}</div>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => { setOpen(false); onCancel(); }} aria-hidden />
          <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-[var(--radius-card)] border border-hairline bg-surface p-3 shadow-lg">
            <div className="mb-3 text-[12px] text-ink2">{message}</div>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => { setOpen(false); onCancel(); }}
                className="h-7 rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 text-[11px] font-semibold text-muted transition-colors hover:bg-surface2 hover:text-ink"
              >
                {cancelLabel}
              </button>
              <button
                type="button"
                onClick={() => { setOpen(false); onConfirm(); }}
                className="h-7 rounded-[var(--radius-control)] bg-alert px-2.5 text-[11px] font-semibold text-white transition-colors hover:bg-alert/90"
              >
                {confirmLabel}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Markdown (plan §1 coach replies) */

/** Minimal, safe markdown renderer: bold, italic, lists, headings, tables, paragraphs.
 *  No raw HTML is allowed (everything is text-escaped). Good enough for coach replies. */
export function Markdown({ content, className = "" }: { content: string; className?: string }) {
  const blocks = useMemoMarkdown(content);
  return <div className={`space-y-2 text-[13px] leading-relaxed text-ink2 ${className}`}>{blocks}</div>;
}

function useMemoMarkdown(content: string) {
  // simple line-by-line parser — headings, lists, tables, paragraphs, bold/italic
  const lines = content.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) {
      out.push(<p key={key++} className="whitespace-pre-wrap">{renderInline(para.join(" "))}</p>);
      para = [];
    }
  };
  while (i < lines.length) {
    const line = lines[i];
    // table: a line with pipes, followed by a separator row
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      flushPara();
      const headers = line.split("|").map((s) => s.trim()).filter(Boolean);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(lines[i].split("|").map((s) => s.trim()).filter(Boolean));
        i++;
      }
      out.push(
        <div key={key++} className="overflow-x-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr>
                {headers.map((h, hi) => (
                  <th key={hi} className="border-b border-hairline2 px-2 py-1 text-left font-semibold text-ink">{renderInline(h)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {headers.map((_, ci) => (
                    <td key={ci} className="border-b border-hairline px-2 py-1 text-muted">{renderInline(r[ci] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }
    // headings
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      flushPara();
      const level = h[1].length;
      const cls = level === 1 ? "text-[18px] font-bold text-ink" : level === 2 ? "text-[16px] font-bold text-ink" : "text-[14px] font-semibold text-ink";
      out.push(<div key={key++} className={cls}>{renderInline(h[2])}</div>);
      i++;
      continue;
    }
    // bullet list
    if (/^\s*[-*]\s+/.test(line)) {
      flushPara();
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      out.push(
        <ul key={key++} className="list-disc space-y-0.5 pl-5">
          {items.map((it, ii) => <li key={ii}>{renderInline(it)}</li>)}
        </ul>
      );
      continue;
    }
    // numbered list
    if (/^\s*\d+\.\s+/.test(line)) {
      flushPara();
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      out.push(
        <ol key={key++} className="list-decimal space-y-0.5 pl-5">
          {items.map((it, ii) => <li key={ii}>{renderInline(it)}</li>)}
        </ol>
      );
      continue;
    }
    // blank line → flush
    if (line.trim() === "") {
      flushPara();
      i++;
      continue;
    }
    para.push(line);
    i++;
  }
  flushPara();
  return out;
}

/** Render inline bold/italic/code. Escapes HTML by treating text as React children. */
function renderInline(text: string): ReactNode[] {
  // split on **bold**, *italic*, `code`
  const tokens = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return tokens.map((tok, i) => {
    if (/^\*\*[^*]+\*\*$/.test(tok)) return <strong key={i} className="font-semibold text-ink">{tok.slice(2, -2)}</strong>;
    if (/^\*[^*]+\*$/.test(tok)) return <em key={i}>{tok.slice(1, -1)}</em>;
    if (/^`[^`]+`$/.test(tok)) return <code key={i} className="num rounded-[3px] bg-surface3 px-1 py-0.5 text-[12px] text-ink">{tok.slice(1, -1)}</code>;
    return <span key={i}>{tok}</span>;
  });
}

/* ------------------------------------------------------------- State-based tone helpers
 * Per the user's rule: DATA color must reflect STATE (in-range / abnormal /
 * out-of-range), NOT the accent color. Accent is reserved for non-data UI
 * (active nav, buttons, focus rings, brand). These helpers compute the correct
 * semantic tone for a value so graphs and badges always read state at a glance.
 */

export type DataTone = "positive" | "warning" | "alert" | "muted";

/** Tone for a 0–100 score (readiness / recovery / sleep score).
 *  ≥75 positive (good), 50–74 warning (fair), <50 alert (poor). */
export function scoreTone(value: number | null | undefined): DataTone {
  if (value === null || value === undefined || !Number.isFinite(value)) return "muted";
  if (value >= 75) return "positive";
  if (value >= 50) return "warning";
  return "alert";
}

/** Tone for ACWR (acute:chronic workload ratio).
 *  0.8–1.3 positive (optimal), 1.3–1.5 warning (elevated), else alert. */
export function acwrTone(value: number | null | undefined): DataTone {
  if (value === null || value === undefined || !Number.isFinite(value)) return "muted";
  if (value >= 0.8 && value <= 1.3) return "positive";
  if (value < 0.8) return "warning";
  if (value <= 1.5) return "warning";
  return "alert";
}

/** Tone for a value against a reference range (low/high).
 *  In range → positive; within 10% of a boundary → warning; outside → alert. */
export function rangeTone(
  value: number | null | undefined,
  low: number | null,
  high: number | null,
): DataTone {
  if (value === null || value === undefined || !Number.isFinite(value)) return "muted";
  if (low === null || high === null) return "muted";
  const margin = (high - low) * 0.1;
  if (value < low - margin || value > high + margin) return "alert";
  if (value < low || value > high) return "warning";
  return "positive";
}

/** Tone for HRV deviation from baseline (in ms or %).
 *  |dev| < 1 SD → positive, 1–2 SD → warning, >2 SD → alert. Pass sd as the
 *  30-day standard deviation. Falls back to a flat 8ms / 16ms threshold. */
export function hrvDevTone(deviation: number | null | undefined, sd: number | null = null): DataTone {
  if (deviation === null || deviation === undefined || !Number.isFinite(deviation)) return "muted";
  const abs = Math.abs(deviation);
  const one = sd && sd > 0 ? sd : 8;
  if (abs < one) return "positive";
  if (abs < one * 2) return "warning";
  return "alert";
}

/** Map a DataTone to the ScoreBar/RangeBar/StatPod tone union. */
export function toneFor(tone: DataTone): "positive" | "warning" | "alert" | "muted" {
  return tone === "positive" ? "positive" : tone === "warning" ? "warning" : tone === "alert" ? "alert" : "muted";
}

/* ------------------------------------------------------------- Info button (plan: metric pages) */

/** Small (i) info button that opens a popover with an explanation. Used on
 *  metric pages and anywhere a value needs context. */
export function InfoButton({
  title,
  children,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full text-faint transition-colors hover:bg-surface2 hover:text-ink"
        aria-label={`Info: ${typeof title === "string" ? title : "more info"}`}
        aria-expanded={open}
      >
        <Info size={13} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute right-0 top-full z-50 mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-[var(--radius-card)] border border-hairline bg-surface p-3 shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
            <div className="mb-1.5 text-[12px] font-semibold text-ink">{title}</div>
            <div className="space-y-1.5 text-[11px] leading-relaxed text-muted">{children}</div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="mt-2 text-[10px] font-semibold text-primaryText hover:underline"
            >
              Close
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/** Structured metric explanation block — the four standard sections every
 *  metric page info popover should have. */
export function MetricInfoContent({
  whatItMeasures,
  whyItMatters,
  whatInfluencesIt,
  howToReadIt,
}: {
  whatItMeasures: ReactNode;
  whyItMatters: ReactNode;
  whatInfluencesIt: ReactNode;
  howToReadIt: ReactNode;
}) {
  return (
    <>
      <div>
        <div className="eyebrow !text-[9px] text-faint">What it measures</div>
        <div className="mt-0.5">{whatItMeasures}</div>
      </div>
      <div>
        <div className="eyebrow !text-[9px] text-faint">Why it matters</div>
        <div className="mt-0.5">{whyItMatters}</div>
      </div>
      <div>
        <div className="eyebrow !text-[9px] text-faint">What influences it</div>
        <div className="mt-0.5">{whatInfluencesIt}</div>
      </div>
      <div>
        <div className="eyebrow !text-[9px] text-faint">How to read it</div>
        <div className="mt-0.5">{howToReadIt}</div>
      </div>
    </>
  );
}
