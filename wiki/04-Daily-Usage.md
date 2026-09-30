# Chapter 4 — Using the app day to day

*Thirteen pages, every metric with a home, EN/IT, light/dark.*

The UI follows one design language (**Apex Precision**): a 12-column layout with a telemetry status strip on top, arc gauges and zone bars for scores, and honest empty states — a day without data says so instead of rendering zeros. On portrait/narrow screens the sidebar moves to a bottom navigation bar; theme (light/dark) and language (English/Italiano) switch instantly from Settings → Appearance and persist per user.

## The pages

| Page | What you get |
|---|---|
| **Overview** `/app` | Status strip (device sync states), readiness hero + synthesis diagnosis, ACWR load band, biomarkers, parasympathetic tone, last night. Anchors to today or — if today is unsynced — the most recent measured day, with prev/next day arrows and an honest "showing D-n" notice. |
| **Activities** `/app/activities` | Paginated list with discipline + sources; the detail page has the altitude-colored GPS trace, synchronized multi-stream chart (HR/power/cadence/speed), HR zones, laps, weather chips, gear and per-field source provenance. |
| **Sleep** `/app/sleep` | Nightly list with scores; the night page shows the measured hypnogram (30 s epochs from raw ingest when available), duration analysis, vitals and rhythm. |
| **Biometrics** `/app/biometrics` | Hub of every metric, each with its own deep page: current readouts, 60-day sparkline, and baseline/deviation context. |
| **Training** `/app/training` | AI plan drafts you confirm in place, the gym day plan with sets/reps/rest, and the adaptive advisor's adjustment notes in plain language. |
| **Coach** `/app/coach` | Resumable AI chats (sessions saved server-side, mirrored locally so a reload never loses a draft). Plans/supplement drafts produced by tools are confirmable right in the web thread. |
| **Social** `/app/social` | Events calendar, challenges and the friends leaderboard. |
| **Settings** `/app/settings` | Profile, appearance (theme/language/units), Devices & Services (connect/sync, main-device law), API tokens, invites, password. |

## The safety interlock (read this once)

Deterministic guardrails run in code **before** any coaching output:

- Elevated illness-risk **vetoes high intensity**.
- ACWR outside 0.8–1.5 **caps prescriptions** — both tails are treated as risk; a ratio under 0.8 is detraining, never "safe".
- Injury-risk spikes cap intensity below Zone 3.

The watch payload carries a machine-readable verdict (`go` / `modify` / `rest`) and the gym plan shows the veto note verbatim. The AI can layer advice on top — it can never talk the interlock out of a veto.

## 4.1 — Main-device law

In Settings → Devices you pick each source's priority. Your **main device wins every field, every day**. A secondary source only ever fills true gaps: if the main device recorded nothing for a day, the secondary covers it; if the main row exists, the secondary only fills columns the main left NULL (per-field merge) — never overwrites. Plausibility filters (HRV 2–400 ms, RHR 25–120, SpO₂ 70–100) drop sensor artifacts at the door, before they can poison a baseline or fire a false alert.

## 4.2 — The watch: "Apex Day" (Connect IQ)

The glance deliberately does not duplicate what Garmin already shows natively (Training Readiness, Recovery, Body Battery). It shows what only Apex knows: today's gym session with the exercises block, active supplements, open alerts and the journal streak, plus the 7-day schedule view.

Setup: mint a token (**Settings → API tokens** — the plaintext is shown exactly once, tokens expire absolutely after 365 days and can be revoked instantly), then paste your server URL + token into the Connect IQ app settings. The watch talks to the same URL you use in the browser, so it keeps working through the tunnel of [Remote access](06-Remote-Access.md).

**Next:** [Maintenance →](05-Maintenance.md)
