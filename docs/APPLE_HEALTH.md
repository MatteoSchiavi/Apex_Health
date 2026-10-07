# Apple Health synchronization

The small iOS companion in `ios/ApexHealthBridge/` synchronizes authorized HealthKit measurements to the user's Apex account. It provides pairing, read authorization, sync status and Sync now. The existing Apple Health ZIP importer remains available for older history and fallback. Apple provides local HealthKit access on Apple devices; there is no server-side HealthKit OAuth endpoint.

## Pairing and security

In Apex web Settings, create an Apple Health pairing code. `POST /healthkit/pairings` requires the authenticated browser session and CSRF token. Codes contain 256 random bits, expire after ten minutes, are stored as peppered hashes, and can be exchanged once. Creating a replacement invalidates prior unused codes for the account.

The companion sends `{code,name}` to `POST /healthkit/exchange` without browser cookies. The response contains `{token,device_id,checkpoint}`. The token is scoped to `healthkit_sync`, stored in iOS Keychain with `AfterFirstUnlockThisDeviceOnly`, expires after 365 days, and cannot access Watch or web endpoints. Disabled users, expired tokens and revoked devices are rejected. Settings lists only the user's HealthKit devices through `GET /healthkit/devices` and revokes them through the CSRF-protected `DELETE /healthkit/devices/{id}`. Revocation stops subsequent uploads; it does not itself erase previously synchronized history.

`GET /healthkit/status` accepts the scoped bearer and returns only the device ID, integer checkpoint and its last successful receipt time. `POST /healthkit/deltas` accepts that bearer and this contract:

```json
{
  "batch_id": "a UUID persisted before upload",
  "expected_checkpoint": 0,
  "additions": [],
  "deletions": []
}
```

Each addition contains `uuid`, the actual HealthKit `type` identifier, aware `start_at`/`end_at`, `value`, `unit`, `source_bundle`, `source_name`, optional `device`, bounded JSON `metadata`, and optional numeric `workout_activity_type`. Sleep uses `HKCategoryTypeIdentifierSleepAnalysis` and numeric category codes 0–5 without a unit. Workouts use `HKWorkoutType`, numeric activity type, and null quantity/unit. Metadata includes the available `source_revision`; optional `workout_summary` preserves native duration, distance and active-energy summary. There are at most 500 additions/deletions combined and a 2 MiB HTTP body limit; metadata allows at most 32 fields, 8192 UTF-8 bytes and six nesting levels. Non-finite quantities, booleans as numbers, unsupported types, wrong units and invalid timestamps are rejected. Quantity bounds are ingestion checks, not clinical interpretation.

The receipt is `{checkpoint,accepted,deleted}`. Counts represent acknowledged input list lengths, including already-known UUIDs and tombstones. Empty batches are acknowledged and increment the checkpoint. A repeated batch UUID with identical content returns its original receipt; changed content or an unexpected checkpoint returns 409. Account/device locks serialize checkpoint, ledger, projections and receipt in one transaction. Immutable UUID collisions reject the whole transaction. Unknown deletions become tombstones, so delayed backfill cannot resurrect deleted data. Deletions remove the ledger payload and safely remove or replace this source's derived projections.

## Data types and provenance

| Measurement | Wire unit | Representation |
| --- | --- | --- |
| Heart rate / resting heart rate | `count/min` | Source summary; resting HR may fill a missing canonical value |
| HRV SDNN | `ms` | Separate `hrv_sdnn_ms` provider summary; never RMSSD |
| Steps | `count` | Source-selected nonoverlapping intervals |
| Active energy | `kcal` | Source-selected intervals; never provider training load |
| Body mass / body fat | `kg` / `%` | Latest selected-source measurement |
| Respiratory rate | `count/min` | Selected-source mean |
| Oxygen saturation | `%` | Selected-source mean |
| VO2max estimate | `mL/kg/min` | Latest selected-source estimate; retains Apple origin |
| Body / basal / sleeping wrist temperature | `degC` | Separate source contexts; wrist/basal values do not become generic body temperature |
| Sleep | Category codes | Source-selected overlap arbitration and wake-date episodes |
| Workouts | Numeric activity type | Source link, timestamps and available summary |

HealthKit sample UUID, original type, source bundle/name, source revision, device descriptor, units, metadata, instants and ingestion time are retained in the account-scoped ledger. Automatic ingestion uses `apple_healthkit`, distinct from ZIP ingestion's `apple_health_import` and ZIP summary namespace `apple_health`. Daily source measurements appear in `daily_biometrics.source_metrics.apple_healthkit`. Equivalent existing measurement types also produce source-labelled lab observations for inspection. SDNN, active energy and wrist/basal temperature retain distinct provider context rather than acquiring an invented canonical equivalence or AI permission. Source eligibility remains governed by the central registry/policy.

For steps and energy, select one producer per local day, preferring Watch, then iPhone, then source identity, and count overlapping intervals once. Bundle/device identity separates similarly named producers. Sleep applies the ZIP importer's stage arbitration: stages override generic asleep, awake overrides generic asleep, and in-bed time alone is not sleep. Episodes separated by at least two hours remain separate; their date is the local wake date. Competing producers' stages are not averaged. Only newly created sleep rows are marked `origin=apple_healthkit`; a conflicting existing sleep row remains intact.

Canonical daily values are filled when blank. Supplier snapshots record the Apple-derived value and other provider namespaces. Recompute/deletion only changes a matching owned projection; changed or ambiguous suppliers preserve the current value and record a limitation. Workouts use existing device arbitration and reconciliation to attach a HealthKit source link to a matching activity. Removing the Apple link preserves activities with other sources; an exclusively HealthKit activity and its direct activity-dependent records are removed. Source-only observations receive a deletion revision with no current numeric value. Historical observation revisions remain audit history.

## Backfill and background behavior

The companion's initial predicate covers the last **90 days**, including overlapping samples. The lower bound stays fixed for that pairing. Each type uses an `HKAnchoredObjectQuery`; query anchors remain on the device. The server stores only a bounded integer delivery checkpoint, never HealthKit query anchors.

Before upload, the companion writes each pending query page, proposed anchor and stable batch UUID to an atomic protected journal excluded from device backups. It uploads at most 100 samples per chunk and respects server item/body limits. The anchor advances only after every batch is acknowledged and local state is saved. A crash or uncertain HTTP acknowledgement replays the same batch. A corrupt or missing journal requires explicit re-pairing instead of silently resetting anchors.

`HKObserverQuery` triggers anchored catch-up, and hourly background delivery is requested. Delivery is best effort: iOS throttling, force quit, reboot/first unlock, power conditions and permissions can delay it. Read authorization deliberately does not expose whether individual types were denied; no results can mean no data or unavailable read access. Keep the app open for initial backfill. Use Sync now to retry connectivity failures. No realtime delivery guarantee is made.

## Apple setup and required manual verification

1. On a Mac, open `ios/ApexHealthBridge/ApexHealthBridge.xcodeproj` in current Xcode; select the Apple Developer team, replace the placeholder `org.apexhealth.bridge` bundle ID with your registered ID, and resolve signing/provisioning. The deployment target is iOS 17 or newer.
2. Enable HealthKit and HealthKit Background Delivery for the App ID and provisioning profile. The checked-in entitlements request `com.apple.developer.healthkit` and `com.apple.developer.healthkit.background-delivery`. The read explanation uses `NSHealthShareUsageDescription`. No Health write or clinical-record access is requested.
3. Run `swift test --package-path ios/ApexHealthBridge` on a compatible Mac, then build the app target with Xcode. Swift tests cover wire/security/journal/checkpoint behavior. The Linux Codex environment cannot compile or execute Swift, Xcode, HealthKit or Apple signing, so these remain manual checks.
4. Install on a physical iPhone. Enter the deployed Apex API base URL, pair via web Settings, authorize read access and verify 90-day backfill against the Health app. Use HTTPS in deployed environments; HTTP is restricted to explicit local development addresses.
5. Verify UTC/local day boundaries, percentage conversion, SDNN identity, temperature availability, sleep stages/naps, Watch/iPhone overlaps, multiple source apps and duplicate workout reconciliation. Delete a sample/workout in Health and confirm safe removal in Apex, preserving other providers.
6. Interrupt networking, force quit around uncertain acknowledgement, and retry/relaunch. Confirm stable batch UUIDs, exactly-once receipts and no premature anchor advancement. Test an empty page, several batches, checkpoint conflict, expired pairing, revoked device and disabled account.
7. Test background updates while locked/suspended and after restart/first unlock; document observed delays. Denied permissions and unavailable types must remain missing. Review the checked-in privacy manifest against actual App Store distribution and provide the required privacy disclosures.

The companion uses an ephemeral HTTP session without cookie credential storage. Secrets stay in Keychain; the protected journal contains pending health data and anchors. Server endpoints do not log health payloads or tokens. Use the project's protected database, encrypted backup and access controls; HealthKit synchronization does not introduce a public data feed.

## Manual ZIP fallback

In Health, choose profile → Export All Health Data, then upload the ZIP to `POST /imports/apple-health` with the authenticated Apex web session. The upload limit is 100 MB and exactly one `export.xml` is required (up to 500 MB uncompressed). XML is parsed without extracting archive paths; the original ZIP is stored encrypted through the source-document path. Re-uploading an identical file for the same account is idempotent. The importer handles workouts, supported daily measurements and sleep with the same source/overlap helpers, preserves SDNN separately, and ignores unsupported types. ZIP history and automatic HealthKit data remain separately attributable.
