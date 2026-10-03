# Apex Health — Swiss modern UI

These rules describe the authenticated SPA in frontend/. The current redesign
follows the owner’s direction: professional, sharp, monochrome, organized,
readable data, minimal clutter. Earlier Apex Precision mockups are historical
references, not the implementation contract.

## Hierarchy and layout

- Use an editorial grid, generous spacing and flat surfaces. No nested bordered cards.
- The overview leads with readiness, followed by recovery, body signals, training
  load, sessions and the last recorded night.
- Separate focused tasks with tabs. Metric catalogs are rows, session logs are
  tables, histories are charts, account workflows are forms.
- Keep every catalog metric reachable, including newly added backend metrics.
- On narrow screens, navigation and tabs scroll horizontally. Tables scroll
  inside their container; the page itself must never overflow.
- Preserve all authenticated workflows and account roles.

## Typography and color

- Use locally bundled Geist for headings, prose and tabular numbers.
- Labels are sentence case, at least 13px; captions have an absolute 12px minimum.
- Neutral numbers, monochrome chart lines and grayscale sleep stages.
- Green, amber and red are reserved for labeled, supported status information.
  A status always includes words; color is never the only explanation.
- Warm orange remains the interaction/focus accent in the Apex palette.
- Sharp 2px controls, 24–32px surface padding and 24px section spacing.
- Light and dark themes share semantic tokens in frontend/src/styles/tokens.css.
- Body text meets WCAG AA contrast. Do not fade text with arbitrary opacity.

## Data presentation

- Show recorded values, exact dates and correct units; respect account unit preferences.
- Readiness, recovery and sleep scores use the UI score bands:
  75–100 good, 50–74 moderate, below 50 low. These are score descriptions.
- Do not declare an absolute body measurement healthy based on arbitrary
  thresholds, its direction of change or the mean of the displayed history.
- Missing values are dashes, never zero. Loading and failed requests are distinct
  from an empty history. History dates must be explicit.
- Daily charts preserve calendar gaps, use one scale and unit per view, include
  an exact tooltip and mark the latest recorded point.
- A period average may be a labeled dashed reference. Do not invent a personal
  normal band or treat observed minimum/maximum as a normal range.
- Sleep timelines require recorded stage epochs. Without epochs, show reported
  stage totals only; never generate physiological cycles from totals.
- Normalized power is not average power. W/kg requires a measured body weight.
  Do not derive heart-rate zones from the highest sample in a single session.
- Acute and chronic load are daily averages in TSS/d. Activity and weekly total
  training load use TSS. ACWR is a separate ratio.
- Paginated summaries describe loaded sessions until all pages are present.
- Queued sync work is not complete until its authenticated status says so.
- Persist preferences to the account, clear query caches on account changes and
  scope local conversation drafts and pending job IDs to the account.

## Verification

Run npm run build, npm run check:i18n and npm run test:ui in frontend/.
Review real browser screenshots in both themes and on mobile.
Browser fixtures are confined to tests; the application has no mock-data mode.
