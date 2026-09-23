---
name: Apex Precision
colors:
  surface: '#111317'
  surface-dim: '#111317'
  surface-bright: '#37393d'
  surface-container-lowest: '#0c0e11'
  surface-container-low: '#1a1c1f'
  surface-container: '#1e2023'
  surface-container-high: '#282a2d'
  surface-container-highest: '#333538'
  on-surface: '#e2e2e6'
  on-surface-variant: '#c4c7c8'
  inverse-surface: '#e2e2e6'
  inverse-on-surface: '#2f3034'
  outline: '#8e9192'
  outline-variant: '#444748'
  surface-tint: '#c6c6c7'
  primary: '#ffffff'
  on-primary: '#2f3131'
  primary-container: '#e2e2e2'
  on-primary-container: '#636565'
  inverse-primary: '#5d5f5f'
  secondary: '#adc6ff'
  on-secondary: '#002e6a'
  secondary-container: '#0566d9'
  on-secondary-container: '#e6ecff'
  tertiary: '#ffffff'
  on-tertiary: '#003824'
  tertiary-container: '#6ffbbe'
  on-tertiary-container: '#00734e'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e2e2e2'
  primary-fixed-dim: '#c6c6c7'
  on-primary-fixed: '#1a1c1c'
  on-primary-fixed-variant: '#454747'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#111317'
  on-background: '#e2e2e6'
  surface-variant: '#333538'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 3rem
    fontWeight: '600'
    lineHeight: 3.5rem
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Geist
    fontSize: 2rem
    fontWeight: '600'
    lineHeight: 2.5rem
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Geist
    fontSize: 1.25rem
    fontWeight: '500'
    lineHeight: 1.75rem
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.25rem
    letterSpacing: 0em
  body-sm:
    fontFamily: Geist
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1rem
    letterSpacing: 0.01em
  metric-xl:
    fontFamily: JetBrains Mono
    fontSize: 2.25rem
    fontWeight: '500'
    lineHeight: 2.5rem
    letterSpacing: -0.03em
  metric-lg:
    fontFamily: JetBrains Mono
    fontSize: 1.5rem
    fontWeight: '500'
    lineHeight: 1.75rem
    letterSpacing: -0.02em
  metric-md:
    fontFamily: JetBrains Mono
    fontSize: 1rem
    fontWeight: '500'
    lineHeight: 1.25rem
    letterSpacing: -0.01em
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1rem
    letterSpacing: 0.02em
  data-timestamp:
    fontFamily: JetBrains Mono
    fontSize: 0.6875rem
    fontWeight: '400'
    lineHeight: 0.875rem
    letterSpacing: 0.04em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-lg: 1.5rem
  margin: 1rem
  margin-md: 1.5rem
  margin-lg: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system is tailored for mission-critical health telemetry, clinical intelligence, and physiological optimization. It operates under a clinical-technical aesthetic that treats bodily data with the rigor of avionics telemetry. The brand voice is austere, decisive, and surgically precise—eliminating decorative ambiguity in favor of cognitive immediacy.

The interface prioritizes high-density data visualization, zero copy bloat, and instantaneous state parsing. Visual weight is strictly calibrated: neutral foundations step back to let physiological deviations, confidence thresholds, and diagnostic signals command immediate focus. The tactile feel balances engineered minimalism with instrument-grade ergonomics, projecting institutional trust, diagnostic sovereignty, and unyielding accuracy.

## Colors

The palette establishes an ultra-refined, high-contrast monochrome substrate engineered for prolonged visual focus under dense information loads. Colors operate with strict semantic discipline; no hue is introduced for decorative embellishment.

### Dark Mode (Primary Default)
- **Base Canvas (`#0D0F12`)**: Root ground layer for deep black levels and minimized eye fatigue.
- **Surface Elevation 1 (`#13171D`)**: Standard card, container, and modular grouping substrate.
- **Surface Elevation 2 (`#1B2028`)**: Active states, dropdown menus, flyouts, and modal panels.
- **Surface Borders (`#2A2E37`)**: Hairline structural divisions for containers and table grids.
- **High-Contrast Text (`#FFFFFF`)**: Primary metrics, values, column headings, and critical labels.
- **Muted Text / Baselines (`#6B7280`)**: Secondary telemetry metadata, inactive indicators, axis lines.

### Light Mode (Clinical/Export Contexts)
- **Base Canvas (`#F8F9FA`)**: Clean off-white daylight working surface.
- **Surface Elevation 1 (`#FFFFFF`)**: Pure white structured modules and elevated cards.
- **Surface Elevation 2 (`#F1F3F5`)**: Interacting rows, hover fields, and control toggles.
- **Surface Borders (`#E2E8F0`)**: Crisp low-contrast structure lines.
- **Text Primary (`#0D0F12`)**: High-legibility charcoal black.
- **Text Secondary (`#64748B`)**: Supporting labels, grid markers, and secondary scales.

### Semantic Telemetry Codes
- **Optimal / Recovered (`#10B981`)**: Normalized vital ranges, successful synchronizations, upward baseline recovery.
- **Warning / Off-Value Amber (`#E5A93C`)**: Borderline physiological shifts, mild homeostasis imbalances, low battery or latency warnings.
- **Critical Alert / Deficit Red (`#EF4444`)**: Acute metric drops, dangerous anomalies, urgent hardware errors. Reserved strictly for non-nominal conditions requiring immediate clinician intervention.
- **Telemetry Stream / Focus Blue (`#3B82F6`)**: Active telemetry streams, focus rings, selected table rows, crosshair scrubbers.

## Typography

The typographical hierarchy is bifurcated into structural navigation (`Geist`) and quantitative telemetry (`JetBrains Mono`). 

### Behavioral Rules
1. **Separation of Concerns**: Prose descriptions, contextual guidance, and view titles must render strictly in `Geist`. Numerical readouts, delta values, units (e.g., `mg/dL`, `ms`, `bpm`), tabular data, coordinate stamps, and live device states must render in `JetBrains Mono`.
2. **Numeric Alignment**: All instances of `JetBrains Mono` leverage tabular figures (`tnum`) and slashed zeros to prevent metric column shifting during real-time data streaming.
3. **Purity of Hierarchy**: Avoid nested intermediate weights. Restrict weights to `400` (Regular) for descriptions and secondary telemetry, `500` (Medium) for numeric readouts, and `600` (Semi-Bold) for high-order landmarks.

## Layout & Spacing

The layout operates on a compact 4px mathematical baseline grid designed for high-density analytical dashboards. The spatial system treats screen area as an operational resource, eliminating dead whitespace in favor of structural grid alignment.

### Grid Architecture
- **Desktop (1440px+)**: 12-column dynamic grid. Standard gutters at `1.5rem` (`gutter-lg`), side margins at `2rem` (`margin-lg`). Modular widgets snap across 3, 4, 6, or 12 column partitions.
- **Tablet / Workstation Small (768px – 1439px)**: 8-column layout. Gutters at `1rem`, outer margins at `1.5rem`. Secondary parameter streams fold into contextual sub-panes.
- **Mobile (Below 768px)**: 4-column single-axis stack. Gutters and outer margins locked to `1rem`. Multi-metric comparative tables pivot into consolidated metric cards.

### Spacing Principles
- Component internal paddings default to `space-sm` (8px) or `space-md` (12px) to maximize data yield within the viewport.
- Analytical grouping uses structural hairline dividers rather than expansive spacing gaps to delineate data streams.

## Elevation & Depth

This design system avoids decorative blurred drop shadows and skeuomorphic lighting. Visual depth is established through tonal planar stacking and hairline borders.

### Surface Tiers
- **Tier 0 (Root Base)**: `#0D0F12` (Dark) / `#F8F9FA` (Light). Acts as the foundational frame.
- **Tier 1 (Containment)**: `#13171D` (Dark) / `#FFFFFF` (Light). Standard container backgrounds for time-series charts, vitals matrices, and telemetry feeds.
- **Tier 2 (Floating & Focus)**: `#1B2028` (Dark) / `#F1F3F5` (Light). Tooltips, active popovers, contextual commands, and scrub controls.

### Structural Separation
- Surfaces do not bleed into one another. Every containment block must be bounded by a solid 1px border (`#2A2E37` in Dark, `#E2E8F0` in Light).
- High-priority overlays (such as acute clinical alerts or real-time diagnostic modal inspectors) use a 1px border highlighted with a 15% opacity tint of their respective semantic color (e.g., `#EF4444` at 15% border alpha).

## Shapes

The interface embraces an engineered, instrument-grade geometry using soft, low-radius curvature (`roundedness: 1`).

### Radius Tokens
- **Standard Corners (0.25rem / 4px)**: Buttons, inputs, chips, table cell selectors, metric badges, and inline status markers.
- **Container Corners (`rounded-lg`, 0.5rem / 8px)**: Analytics cards, chart containers, modal inspectors, and diagnostic modules.
- **Outer Shell Corners (`rounded-xl`, 0.75rem / 12px)**: Standalone floating modal windows and deep system overlays.

Zero full-pill geometries are permitted, ensuring that buttons, tags, and inputs maintain uniform mechanical structure aligned with the underlying data grid.

## Components

### Buttons & Interactive Controls
- **Primary Action**: Solid `#FFFFFF` fill with `#0D0F12` `Geist` text (Dark Mode) or `#0D0F12` fill with `#FFFFFF` text (Light Mode). 0.25rem corner radius, 32px height for compact ergonomics.
- **Secondary / Telemetry Action**: Background transparent, 1px border `#2A2E37`, text `#FFFFFF`. Hover triggers background `#1B2028`.
- **Destructive / Alert Action**: Background `rgba(239, 68, 68, 0.1)`, 1px border `#EF4444`, text `#EF4444`.

### Telemetry Badges & Chips
- Designed for instant glanceability with monospaced precision.
- Heights restricted to 20px–24px. Padding: 0 6px.
- Structure: 1px border with a 10% translucent background corresponding to the semantic state (`#10B981`, `#E5A93C`, `#EF4444`, `#3B82F6`). Label text set in `JetBrains Mono` (`data-mono`) at 500 weight.
- Includes an optional 4px circular status dot directly preceding the label.

### Data Tables & Telemetry Lists
- Row heights clamped at 36px (compact) or 44px (default).
- Zero vertical column borders; horizontal separations use 1px `#2A2E37` (Dark) / `#E2E8F0` (Light).
- Column headers: `JetBrains Mono` uppercase, 0.6875rem, muted text `#6B7280`.
- Metric values right-aligned with unit tokens appended in muted monospace (`#6B7280`).

### Checkboxes & Segmented Toggles
- Checkbox: 14px × 14px square, 2px radius, hairline border `#2A2E37`. Checked state fills `#3B82F6` with a white precision vector tick.
- Segmented Control: Recessed `#0D0F12` track, 1px hairline border, containing 28px height items. Selected item elevates to `#1B2028` with an active `#FFFFFF` label.

### Input Fields & Scrubbers
- Height: 32px. Monospace data entry option for dosage, metric thresholds, and ranges.
- Default state: Background `#13171D`, border 1px `#2A2E37`, placeholder text `#6B7280`.
- Focus state: Border transitions to `#3B82F6` with no diffuse drop shadow; single crisp hairline glow ring (`0 0 0 1px #3B82F6`).

### Analytics Cards & Telemetry Blocks
- 1px border `#2A2E37` with surface fill `#13171D`.
- Card Header: Left-aligned title in `Geist` (`body-sm`), right-aligned real-time stream status or timestamp in `JetBrains Mono` (`data-timestamp`).
- Body: Prominent primary metric (`metric-xl`), delta comparison percentage (with semantic arrow indicator), and embedded time-series sparkline without decorative chart axes.