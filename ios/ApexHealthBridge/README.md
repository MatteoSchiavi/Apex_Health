# Apex HealthKit synchronization companion

A minimal iOS 17+ SwiftUI bridge, with pairing, read authorization, status, sync-now and troubleshooting. It does not duplicate the Apex dashboard. This is private-alpha source, **not an App Store release or a live-device-verified integration**.

## Build and signing

The committed `ApexHealthBridge.xcodeproj` is ready to open in Xcode 15 or later. A dependency-free Python generator also rebuilds it deterministically:

```bash
cd ios/ApexHealthBridge
python3 scripts/generate_xcode_project.py --bundle-id com.yourcompany.ApexHealthBridge --team YOUR_APPLE_TEAM_ID
open ApexHealthBridge.xcodeproj
```

Select your Apple Developer team and an available App ID. Enable **HealthKit** and **Background Delivery** for that App ID and provisioning profile; the checked-in entitlements request both. Set the deployment target to iOS 17 or newer. A physical iPhone is required for meaningful health-data and background tests. The app requests read access only and declares `NSHealthShareUsageDescription`; no Health write access or clinical-record entitlement is requested. Review the privacy manifest against your actual distribution before publishing.

Build and core-test commands on a Mac:

```bash
swift test
xcodebuild -project ApexHealthBridge.xcodeproj -scheme ApexHealthBridge -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
xcodebuild -project ApexHealthBridge.xcodeproj -scheme ApexHealthBridge -destination 'generic/platform=iOS' build
```

Core Swift tests cover URL policy, stored configuration validation, wire fields/nulls/UTC timestamps, metadata and batch bounds, UUID collision rejection, empty-page acknowledgements, crash replay, deletion precedence, checkpoint mismatch and multi-batch anchor advancement, and durable scan rotation across background budgets. They have **not been executed in the Linux implementation environment**, which has neither Swift nor Xcode. The app target needs a Mac build as well as physical-device verification; static artifact checks do not replace these checks.

## Pairing and data contract

1. Sign in to Apex in the web UI and create a ten-minute, one-use code in device settings.
2. Enter your Apex **API base URL**, code and device name in the companion. If your reverse proxy exposes the API beneath `/api`, include `/api` in this URL.
3. The app posts `{code,name}` to `healthkit/exchange`. The narrowly scoped token goes into Keychain (`AfterFirstUnlockThisDeviceOnly`), with no browser cookies or credential storage.
4. Review Apple Health read permissions, then start synchronization. The token can be revoked in Apex device settings. Removing local pairing deletes the local token/journal; **server revocation is a separate action**.

The app uses HTTPS except literal loopback development addresses (`localhost`, `127.0.0.1`, `::1`). HTTP LAN/private-IP addresses are rejected. ATS permits local networking only; it has no global insecure-load exception. Some OS/network configurations may still reject HTTP IP-literal loopback, so prefer HTTPS or localhost. Loopback on an iPhone refers to the iPhone; use a reachable HTTPS server for physical-device testing. All HTTP redirects are refused, including same-origin redirects: configure the final API base URL. URLSession is ephemeral, cookie-free, has no URL credentials or cache, and never follows redirects with a token or pairing code.

Supported types and units:

| HealthKit type | Wire unit/semantics |
| --- | --- |
| Heart rate and resting heart rate | `count/min` |
| HRV SDNN | `ms`; preserved as SDNN, never converted to RMSSD |
| Sleep analysis | Original numeric category; no stage reconstruction |
| Workouts (`HKWorkoutType`) | Null value/unit; original numeric activity type; optional bounded `workout_summary` metadata |
| Steps | `count` |
| Active energy | `kcal` |
| Body mass | `kg` |
| Body fat and oxygen saturation | `%`, 0–100 (HealthKit fractions multiplied by 100) |
| Respiratory rate | `count/min` |
| VO2max | `mL/kg/min` |
| Body, basal body, sleeping wrist temperature | `degC`; wrist type guarded by OS availability |

Every sample retains its UUID, original type, start/end, source name/bundle and bounded device description. `metadata.source_revision` retains source version, product type and OS version. The app preserves a bounded allowlist of useful scalar metadata (user-entered flag, sync ID/version, timezone, motion context, VO2max test type) rather than arbitrary user notes. Workouts include available duration seconds, distance meters and total kilocalories in `metadata.workout_summary`; missing stats remain missing. Sample metadata stays within 32 fields and 8192 serialized bytes. Backend ingestion time is recorded by the server. No raw health data, token, pairing code or raw server error body is logged or included in error messages.

## Anchor, journal and retry behavior

The initial query predicate covers the last **90 days**, including samples overlapping the boundary. Its lower bound is fixed for the entire pairing; incremental queries reuse the same predicate and each type's archived secure-coding anchor. It does not fetch older records. All types use anchored queries; observers trigger bounded catch-up and hourly background delivery requests.

A single coordinator serializes the token-global checkpoint. It first persists the entire queried page, proposed next anchor and UUID-keyed batch(es) to an atomic, protected local journal. Requests contain at most 500 additions/deletions and 2 MiB encoded JSON; each chunk contains at most 100 samples. Deletions preserve original UUIDs even when they refer to unknown server samples. If a sample and deletion occur together, the deletion wins.

`POST healthkit/deltas` retries the **same batch UUID and expected checkpoint** after network failure or uncertain acknowledgement. A page's anchor advances only after **every batch** is acknowledged and the updated state is atomically saved. Empty pages also upload an empty batch to obtain a server acknowledgement before advancing their anchors. A crash between the server commit and local persistence replays the same batch; backend idempotency returns the original acknowledgement. The client refuses mismatched checkpoints/counts instead of resetting state. A missing/corrupt journal requires explicit device revocation and re-pairing, not a silent anchor reset. The protected journal is excluded from device backups and the token is device-only; protected files/Keychain remain unavailable before the first unlock after restart.

Foreground catch-up drains pages while the app is active. Retryable connectivity, 429 and server failures receive up to three increasing-delay foreground retries, retaining the journal afterwards. Observer attempts prioritize their changed type and wait for any current upload to finish, so concurrent callbacks keep token checkpoint updates serialized. The scan position is durable, so small background budgets rotate across types instead of repeatedly checking only the first empty types. Background observers process a small number of pages and always call their completion handler after the attempt; completion does not promise the full historical backfill has finished. iOS schedules background delivery at its discretion. Force quit, reboot/first unlock, denied permissions, power constraints and OS throttling can delay it. Keep the app open for the initial backfill and use Sync now after a failure.

## Required physical-device verification

1. Build signed, pair with the private-alpha backend and grant only selected read types. Confirm the app cannot request Health write permission and cannot access denied types. iOS intentionally hides per-type read denial; empty results must not be presented as proof of absent health data.
2. Verify a 90-day backfill, UTC/day boundaries, SDNN distinction, percentage units, wrist-temperature availability, sleep categories and original workout activity/source fields against Health. Include Watch/iPhone and two source apps; the native client preserves every original UUID and leaves canonical reconciliation to Apex.
3. Disable networking after a batch is journaled, restore networking, force-quit/relaunch at uncertain acknowledgement, and verify the same batch UUID/checkpoint is replayed exactly once server-side. Repeat with an empty page and a multi-batch page; no anchor may advance early.
4. Add and delete a sample in Health, including deleting a sample unknown to Apex; confirm the deletion UUID reaches the backend and the correct source sample disappears without changing unrelated sources.
5. Lock/unlock and reboot/first-unlock; test background Health updates while the app is suspended. Document actual delays rather than assuming real time. After force quit, reopen the app and verify catch-up. Deny background delivery and confirm Sync now still works.
6. Revoke the device token in Apex. Verify uploads stop, errors stay generic, local state is retained, and a new one-time pairing uses a new independent journal/anchors. Verify expired/reused pairing codes fail.
7. Verify remote HTTP, embedded URL credentials, query/fragment URLs and redirected endpoints are rejected; verify no cookies or Authorization headers reach an alternate origin. Inspect device console to confirm no health payloads, tokens or codes are printed.
8. Verify protected journal/Keychain failure pauses instead of clearing state; remove local pairing and confirm journal/token are removed, then revoke the server-side device.
