# Apex Health — Design Rules

> The single source of truth for every visual decision. Every PR, every prompt,
> every component edit checks against this file. If a change breaks a rule
> here, it doesn't ship.

---

## The 9 Principles

### 1. One answer per screen
Every page starts with a sentence that answers its question ("You're moderately ready. Keep today aerobic."), then one hero instrument, then supporting sections. If a page can't answer "what is this screen's one answer?" in one sentence, the layout is wrong.

### 2. One hero, two sizes of everything else
The hero is at least 2× the visual weight of any other element on the page. On the Overview, the readiness number is 72–80px; everything else is ≤28px. Never make two elements the same size if one matters more.

### 3. No outlines. No card inside a card.
Cards are separated from the background by **surface contrast** (≥ 1.14:1), not by 1px borders. Outlines are only for inputs and the focused element. A card never contains another bordered card. If you need grouping inside a card, use spacing + a label, not a box.

### 4. Sentence-case labels, 13px minimum
No all-caps eyebrows. At most **one** small-caps label per page, if any. Nothing below 12px, ever. Labels are sentence case ("Sleep score", not "SLEEP SCORE"). Numbers are the big things; labels are the small things.

### 5. Neutral by default; colour has three jobs
Colour is used for exactly three things:
- (a) **A status dot + a word** ("● Good", "● Watch", "● Alert") — never a coloured big number.
- (b) **Chart series** (one accent line, a shaded "your normal" band).
- (c) **The accent** for actions and the hero ring.

Numbers stay white/text-coloured. Never colour a big number. The state of a value is shown by a dot + word next to it, not by tinting the number.

### 6. The accent is not a status colour
The default accent is **warm orange (`#FF7A1A`)**, distinct from "good" (green `#5BD6A0`). A green button and a healthy reading must never be the same colour. Available accents: orange, ice blue, lime — all different from the status colours.

### 7. Plain words
Say "Body signals", "Training load", "Last night", "Today's plan". Retire "telemetry", "calibrated", "synthesis", "biosignal", "validated". The Overview title is a greeting + a sentence ("Good morning, Matteo. You're moderately ready."), not a noun phrase ("Physiological Telemetry").

### 8. Every chart is built the same way
One accent line. A shaded "your normal" band (mean ± 1 SD). The latest point marked with a dot. Y-labels on the left. At most three gridlines. Hover shows the exact value + date. No chart has bars + lines on the same axis unless it's a combo chart with a clear legend.

### 9. Seven sections maximum per page
Lists of metrics are **rows**, not cards. The Biometrics hub is grouped rows (label · value · status dot · sparkline), not a 24-card grid. If a page has more than 7 distinct sections, it's trying to do too much — split it.

---

## Tokens (frozen)

### Colour

| Token | Dark | Light |
|---|---|---|
| background | `#0B0C0F` | `#F4F3F0` |
| surface (cards) | `#191C22` | `#FFFFFF` |
| surface-2 (inputs, active nav) | `#23272F` | `#ECEAE5` |
| divider (rare) | `rgba(255,255,255,.07)` | `rgba(0,0,0,.08)` |
| text | `#EEF0F3` | `#14161A` |
| text-2 | `#A3A9B3` | `#4A505A` |
| text-3 | `#7A818D` | `#656B75` |
| accent (orange) | `#FF7A1A` | `#C2410C` (text) / `#E85D04` (fills) |
| ok (good) | `#5BD6A0` | darker equivalent |
| watch (caution) | `#F2C14E` | darker equivalent |
| alert (bad) | `#FF5C6C` | darker equivalent |
| sleep deep | `#3F4DB8` | same hue, deeper |
| sleep REM | `#6F7CF0` | |
| sleep light | `#A9B2FA` | |
| sleep awake | `#F2C14E` | |

### Type scale

| Size | Use |
|---|---|
| 12px | Minimum caption (use sparingly) |
| 14px | Body text, labels |
| 16px | Secondary values |
| 20px | Page sentence (the answer) |
| 28px | Section titles |
| 40px | Page title |
| 72–80px | Hero number (semibold) |

All numbers use `tabular-nums` (Geist). JetBrains Mono only for chart axes and ids.

### Spacing + radius

- 8-point spacing grid
- Card padding: 28px
- Gap between sections: 24–32px
- Card radius: 20px
- Inner element radius: 12px

### Contrast requirements (checkable)
- background → surface: ≥ 1.14:1 (dark: `#0B0C0F` → `#191C22` = 1.16:1 ✓)
- surface → surface-2: ≥ 1.07:1
- text on surface: ≥ 7:1 (text-2 `#A3A9B3` on `#191C22` = 7.2:1 ✓)
- text-3 on surface: ≥ 4.3:1 (`#7A818D` on `#191C22` = 4.35:1 ✓)
- accent on surface: ≥ 4.5:1 for text use

Light theme: cards get a soft shadow (`0 1px 2px rgba(20,22,26,.06)`) instead of an outline, because the background→surface contrast is only 1.11:1.

---

## What to delete (from the current codebase)

- [ ] All uppercase "eyebrow" labels (167 uses) → sentence case, 13px
- [ ] All `text-[9px]` and `text-[10px]` (185 uses) → minimum 12px
- [ ] Nested tiles (StatPod inside Card inside Card) → flat rows
- [ ] The state-tone law on big numbers (coloured BigStat values) → white numbers + status dot
- [ ] The 8-colour accent picker → 3 accents only (orange, ice blue, lime)
- [ ] The "LOW/HIGH" chips on biometric cards → status dot + word
- [ ] The source badge on every metric card → hidden, shown on hover only
- [ ] "Telemetry" copy → plain words ("Body signals", not "Physiological Telemetry")
- [ ] The "Physiological Telemetry" page title → greeting + sentence

---

## Mechanical guardrails (CI check)

A lint rule that fails the build on:
- `text-[9px]` or `text-[10px]` anywhere
- `uppercase` class outside of one allowed small-caps label per page
- `border` class on a `Card` (outlines only on inputs + focus)
- `bg-positive` / `bg-warning` / `bg-alert` on a `BigStat` or hero number
- The word "telemetry" / "calibrated" / "synthesis" / "biosignal" in any new string

---

## How to use this file

Before any UI edit:
1. Read the 9 principles.
2. Check the tokens you're using are from the frozen table.
3. Verify your change doesn't break a guardrail.

After any UI edit:
1. Open the page in the browser.
2. Can you point to the one hero element? (Principle 2)
3. Are there any borders on cards? (Principle 3)
4. Is any text below 12px? (Principle 4)
5. Is any big number coloured? (Principle 5)
6. Does it use "telemetry" or similar jargon? (Principle 7)

If any answer is wrong, the edit doesn't ship.
