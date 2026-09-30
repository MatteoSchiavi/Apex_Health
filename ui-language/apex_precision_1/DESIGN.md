---
name: Apex Precision
colors:
  surface: '#111318'
  surface-dim: '#111318'
  surface-bright: '#37393e'
  surface-container-lowest: '#0c0e12'
  surface-container-low: '#1a1c20'
  surface-container: '#1e2024'
  surface-container-high: '#282a2e'
  surface-container-highest: '#333539'
  on-surface: '#e2e2e8'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#e2e2e8'
  inverse-on-surface: '#2f3035'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#ffb3ad'
  on-tertiary: '#68000a'
  tertiary-container: '#ff5451'
  on-tertiary-container: '#5c0008'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#111318'
  on-background: '#e2e2e8'
  surface-variant: '#333539'
typography:
  display-hero:
    fontFamily: Geist
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 48px
    letterSpacing: -0.03em
  display-hero-mobile:
    fontFamily: Geist
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Geist
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.015em
  stat-xl:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 30px
    letterSpacing: -0.02em
  body-base:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: -0.005em
  body-medium:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0em
  label-caps:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.06em
  caption:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
  micro-telemetry:
    fontFamily: Geist
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 12px
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
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-tablet: 1.5rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system is engineered for elite human performance, physiological telemetry, and clinical athletic optimization. The aesthetic embodies quiet technical authority: deeply calculated, scientifically disciplined, and utterly devoid of gamified fitness tropes or aggressive motorsport clutter. The brand communicates the diagnostic precision of an advanced metabolic research facility paired with the effortless clarity of an archival Swiss editorial layout.

The interface serves high-performing athletes, performance physiologists, and data-focused health practitioners who require instant, uncompromised signal extraction. Surfaces are built on a monochromatic foundation of deep charcoal, near-black abyssal panels, and crisp surgical off-whites. Color operates under extreme restraint: functional semantic hues indicate distinct biological states rather than serving decorative purposes. Typography features razor-sharp optical pacing and dedicated tabular figures that eliminate visual jitter across real-time physiological telemetry. The emotional impact is focused, authoritative, calm, and unmistakably premium.

## Colors

The foundation is built upon a high-contrast dark theme by default, while supporting a pristine light theme with surgical clarity. The dark environment employs near-black charcoal surfaces that preserve low-light visual acuity and prevent digital fatigue during nocturnal or early-morning physiological reviews.

### Palette Architecture
- **Primary Telemetry Blue (`#3B82F6`)**: Reserved strictly for focal interactive signals, navigation states, active time windows, and calibrated primary curves.
- **Positive Biomarker Green (`#10B981`)**: Signals positive biological delta, sustained parasympathetic recovery, and target physiological thresholds.
- **Attention Coral / Alert Crimson (`#EF4444`)**: Deployed exclusively to flag acute strain spikes, severe nocturnal oxygen dips, systemic exhaustion, or elevated risk metrics.
- **Warning Amber (`#F59E0B`)**: Contextual intermediate indicator for borderline recovery or elevated autonomic friction.
- **Neutral Canvas (`#0A0C10` Dark / `#F8FAFC` Light)**: Uncompromisingly deep substrate with subtle cool slate undertones.
- **Surface Elevation Containers**: Dark containers step up through `#11141B` (base panel) to `#181C26` (elevated control surface). Light containers sit on `#FFFFFF` with muted slate foundations.
- **Hairlines & Boundaries**: 1px structural outlines rendered with `rgba(255, 255, 255, 0.08)` (Dark) and `rgba(15, 23, 42, 0.08)` (Light).

## Typography

The type system prioritizes optical neutrality, instant scannability, and structural order. Built using Geist, the geometric proportions, crisp apertures, and technical character mimic precision diagnostic instrumentation.

### Rules & Application
- **Tabular Figures**: Every numeric display, metric card, delta tag, and graph tick label strictly applies `font-feature-settings: "tnum" 1`. This eliminates horizontal shifting during continuous data streaming or scrubbing across physiological timelines.
- **Category Eyebrows**: Metric group titles and status labels use `label-caps` (all uppercase, 11px, +0.06em tracking, weight 600) to create a distinct semantic barrier between labels and dynamic values.
- **Tight Vertical Rhythm**: Numeric values and their relative units sit tightly together with leading matched to the font cap height. Units are positioned inline or stacked as secondary body labels to preserve vertical hierarchy.

## Layout & Spacing

Layouts follow a structured 12-column analytical fluid grid system anchored by a 4px spatial baseline. Density is calibrated to balance deep diagnostic focus with clean visual separation.

### Screen Adaptations
- **Desktop (>= 1280px)**: 12-column layout with 24px gutters and 32px canvas margins. Metrics partition into clean modular 3-column or 4-column telemetry pods, with primary physiological timelines (e.g., continuous hypnograms, metabolic power curves) spanning 8 to 12 columns.
- **Tablet (768px – 1279px)**: 8-column layout with 16px gutters and 24px margins. Modular cards dynamically stack into dual-column grids; secondary charts transition to tabbed views.
- **Mobile (< 768px)**: 4-column layout with 16px gutters and 16px outer margins. Key metric clusters collapse into 2x2 grids. High-density timelines (such as sleep stage bar plots or continuous heart rate strips) support native horizontal drag scrubbing with fixed Y-axis datum pins.

## Elevation & Depth

This system intentionally avoids deep ambient drop shadows, glossy neon glows, or skeuomorphic glass diffusion. Visual hierarchy is established strictly through tonal layering and low-contrast hairline boundaries.

### Layering Hierarchy
- **Base Canvas (Level 0)**: The foundational ground plane (`#0A0C10` in dark mode, `#F8FAFC` in light mode). Completely non-interactive.
- **Surface Panels (Level 1)**: Elevated metric containers, card modules, and chart backgrounds sit at `#11141B` (Dark) or `#FFFFFF` (Light), bounded by a hairline border (`1px solid rgba(255, 255, 255, 0.08)` or `1px solid rgba(15, 23, 42, 0.08)`).
- **Interactive Controls & Flyouts (Level 2)**: Floating inspection tooltips, active dropdowns, and date pickers use `#181C26` (Dark) or `#FFFFFF` (Light) accompanied by a minimal, precise edge-definition shadow (`box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35)` in dark mode, or `0 4px 12px rgba(15, 23, 42, 0.06)` in light mode).
- **Hairline Restraint**: Never introduce saturated color borders to denote panel elevation. Borders provide quiet optical separation, letting internal metric typography command full attention.

## Shapes

The geometric signature balances architectural discipline with ergonomic software design. The visual rhythm relies on subtle, consistent curvature:
- **Telemetry & Score Cards**: Standardized at `rounded-lg` (8px / 0.5rem), yielding clean structural enclosures without appearing bubbly or child-like.
- **Interactive Buttons, Selectors, and Input Controls**: Scaled at `rounded-sm` (4px / 0.25rem), providing crisp corner geometry that clearly defines clickable boundaries.
- **State Badges & Horizon Chips**: Set to `rounded-sm` (4px) or full pill radius (`rounded-full`) exclusively when representing continuous temporal states or discrete categorical tags.

## Components

### Telemetry & Score Cards
- **Structure**: Encapsulated within 8px rounded boundaries with 1px hairline borders (`rgba(255, 255, 255, 0.08)`). Padding is fixed at 16px for standard pods and 20px for hero telemetry panels.
- **Header Structure**: Top row pairs an uppercase label (`label-caps`, muted text) with an operational status badge or micro-icon.
- **Metric Readout**: Oversized numeric displays (`stat-xl` or `headline-lg`) paired with inline unit labels. 
- **Delta Indicator**: Subordinate row displaying comparative trends (e.g., `+4% vs baseline`, `improved by 12ms`) colored in positive green (`#10B981`) or coral alert (`#EF4444`), accompanied by a micro directional arrow.

### Buttons & Time Horizon Selectors
- **Primary Buttons**: Background `#3B82F6`, foreground `#FFFFFF`, 4px radius, medium weight (`body-medium`), zero external shadow, active press transforms down 1px.
- **Secondary / Subdued**: Subtle transparent surface with 1px hairline border, hover transition to `#181C26`.
- **Horizon Segmented Controllers**: Single continuous container with 1px border. Inactive segments display muted labels; active segment elevates with `#181C26` background, crisp light text, and no layout shift.

### Hypnogram & Stage Timeline Bars
- **Architecture**: Specialized horizontal multi-tiered bar structure representing discrete sleep/strain segments (Deep, REM, Core/Light, Awake).
- **Color Discipline**: Deep restorative stages use deep cobalt/indigo hues; REM stages use primary sky blue; Core uses slate tones; Awake/Disturbance segments render in crisp, sharp coral/amber hairline slices.
- **Axis & Scrubbing**: Hairline vertical playhead scrubs horizontally across tabular timestamps, projecting instant readouts on hover/touch.

### Form Inputs & Control Toggles
- **Inputs**: Hairline border containers with 4px corner radius, background `#11141B`, text in crisp off-white, focus state bounded by a 1px primary blue stroke (`#3B82F6`) with no heavy drop-shadow glow rings.
- **Checkboxes & Radios**: 16px square/circular controls with hairline borders; checked state fills with solid `#3B82F6` and an ultra-fine 1.5px white checkmark.

### Delta Chips & Health Badges
- **Format**: Inline-flex container with 4px border radius, 2px 6px padding.
- **Styling**: Semi-transparent tinted background (10% opacity of target semantic color) paired with full-saturation text for effortless contrast and low visual noise.