# Human actions for the private alpha

These actions require the developer, provider account owner, Apple signing team,
or participating athletes. Automated code and fixture verification is recorded
separately in ALPHA_IMPLEMENTATION_PLAN.md; this list does not claim it is done.

## Provider access

- Confirm Garmin Developer application/approval and permitted data products with
  Garmin. Obtain official credentials and current partner schemas only after
  approval. The current Garmin Connect path is unofficial; no official API or
  device-delivery acceptance is implemented. See GARMIN_OFFICIAL_MIGRATION.md.
- Register or confirm each enabled provider application, consent scope, redirect
  URL, terms and permitted derived/AI use. Supply real OAuth/MCP credentials
  through the existing deployment configuration, never repository files.
- With consenting athletes, run a multi-week soak for each enabled connector:
  real connection, refresh, pagination/backfill, incremental import, revoked
  consent, upstream outage, source changes and incomplete sensor days. Record
  dated outcomes and grant scopes before changing live/production maturity.

## Apple companion

- Choose the real App ID/bundle ID, Apple Developer team and reachable HTTPS API
  URL. Open ios/ApexHealthBridge/ApexHealthBridge.xcodeproj on a Mac with Xcode
  15+, configure signing/provisioning, and enable HealthKit and Background
  Delivery for the App ID. Review the privacy manifest for actual distribution.
- Build the iOS target and execute Swift core tests using the exact commands in
  ios/ApexHealthBridge/README.md. Linux static checks cannot verify either.
- Install the signed app on a physical iPhone. Verify selective/denied read
  permissions, Watch/iPhone overlap, SDNN attribution, staged sleep, workouts,
  replay after a crash/offline period, deleted samples, revoked/expired tokens,
  checkpoint mismatch and background observer completion. Apple does not expose
  denied read permission as a reliable distinct “no samples” state.
- Exercise long background/offline periods and battery/network restrictions.
  Background delivery is best effort; confirm foreground sync provides a usable
  recovery path. No App Store publication is part of this implementation.

## Alpha research and operation

- Select 5–15 consenting private-alpha athletes; explain data use, provider and
  model limitations, optional feedback, export/deletion and support expectations.
- Interview participants about whether they understand a daily interpretation,
  its evidence and missingness, can review/edit/reject a change, and find the
  feedback useful. Record actual task completion and reasons, not invented
  acceptance or outcome statistics.
- Review first-party aggregates with the named time window and denominators.
  Acceptance and reported influence are product signals, not evidence of health
  or performance benefit. Choose the next iteration using observations and
  interviews before expanding recruitment or adding public-SaaS infrastructure.
- On the intended home server, supply private configuration and verify TLS,
  backup storage/keys, restore access and database extension permissions. Keep
  signing/provider credentials and health-data backup keys under operator control.
