# Provider support in the private alpha

This page describes what is present in this repository. “Implemented” means
there is application code for the stated path; it does not mean that a provider
account was connected or that production operation has been established. The
repository contains mocked/fixture tests for several paths, but those tests do
not verify live credentials, provider approval, current upstream behavior, or
production reliability. No live provider verification is claimed here.

## Support matrix

| Provider and path | Ingestion and normalization in this alpha | Fixtures and automated coverage | Live / production evidence in this repository | Access and commercial gate | Write-back | AI evidence policy | `support.py` status |
|---|---|---|---|---|---|---|---|
| **Garmin Connect (unofficial)** | Implemented account connection and sync through `garminconnect`; activity summaries and activity samples, sleep, HRV, stress, daily stats, and body composition are ingested. The adapter converts the installed library's current activity-detail shape to the internal sample shape. FIT enrichment is a separate local-file path. Normalizers retain raw records and source attribution. | Garmin JSON fixtures cover activities, streams, sleep, HRV, stress, stats, and body composition. Garmin sync/shape tests exist. These are deterministic fixtures, not captured proof of current production service behavior. | `live_tested=false`; `production_supported=false`. No live Garmin account sync is recorded. | `commercial_approval_required=true` for official commercial use; current path uses unofficial Garmin Connect sign-in/session credentials and is upstream-dependent. | `none`. No official Garmin Training API delivery. Local workout descriptions and FIT/TCX download are exports, not watch acceptance. | `ai_evidence_eligible=true`, subject to metadata restrictions. | `EXPERIMENTAL` |
| **Apple Health export ZIP** | Implemented manual `export.zip` upload and bounded XML parsing for the record types documented in [APPLE_HEALTH.md](APPLE_HEALTH.md). Separate from native HealthKit access. | Apple Health import tests exercise parser/import with test inputs. | `live_tested=false`; `production_supported=false`. Manual export/import operation on a physical device is not independently validated. | `commercial_approval_required=false`; no API credential is needed for a user-supplied ZIP. | `none`. | `ai_evidence_eligible=false`; Apple ZIP follows a separate import path outside the current AI-origin allowlist. | `MANUAL_IMPORT` |
| **Apple HealthKit native companion** | Native iOS reader, permissions flow, pairing, bounded delta upload, backend receipt, and source-owned normalization/projections are implemented in `ios/ApexHealthBridge`, `/healthkit`, and the backend ingestion service. | `test_healthkit_bridge.py` and native contract/sync-state tests exist. | `live_tested=false`; `production_supported=false`. No physical-device, signed-installation, or background-delivery validation is recorded. | `commercial_approval_required=false` in `support.py`. A signing team, HealthKit entitlement, provisioning and device permissions are still required for a real install. | `none`; the companion requests read access only. | `ai_evidence_eligible=false` in `support.py`. | `DEVELOPMENT_ONLY` |
| **WHOOP Developer API v2** | Implemented OAuth2 account connection, token refresh, sync, raw ingestion and source-specific normalization for the enabled profile, body measurement, cycle/recovery, sleep, and workout feeds. WHOOP sleep performance remains provider-scoped metadata; canonical `sleep_score` stays empty. | `fixture_tested=true`; `test_whoop_connector.py` covers mocked OAuth/API and normalization. It does not call WHOOP. | `live_tested=false`; `production_supported=false`. A live session requires real app keys, network access and athlete consent; none is evidenced here. | `commercial_approval_required=null` (not established by this repository); owner app credentials and per-athlete OAuth scopes are required technically. | `none`. | `ai_evidence_eligible=true`, subject to metadata restrictions. | `EXPERIMENTAL` |
| **Oura API v2** | Implemented OAuth2 connection, token handling, sync, raw ingestion and source-specific normalization. | `fixture_tested=false`; sync/normalization code exists, but no Oura-specific fixture/test module is present. | `live_tested=false`; `production_supported=false`. | `commercial_approval_required=null` (not established here); code expects app credentials and athlete authorization. | `none`. | `ai_evidence_eligible=true`, subject to metadata restrictions. | `EXPERIMENTAL` |
| **Strava API v3** | Implemented OAuth2 account connection, refresh, paged activity ingestion and normalization of summary activities. Records are partial; activity streams are not fetched. | `fixture_tested=true`; mocked regression coverage is in `test_strava_connector.py`. | `live_tested=false`; `production_supported=false`. Real authorization was not performed per `UI_DATA_CHANGES.md`. | `commercial_approval_required=true`; registered application, configured credentials/redirect URI and athlete consent are required. | `none`; disconnect attempts provider deauthorization. | `ai_evidence_eligible=false`; Strava-origin evidence is excluded from AI, including merged activities with a restricted source link. | `EXPERIMENTAL` |
| **COROS through configured MCP server** | Implemented account-scoped bearer-token connection to an administrator-selected Streamable HTTP MCP endpoint and one configured activity tool. This is not a direct COROS API connector. | `fixture_tested=true`; MCP/normalization tests use test doubles. No verified external server fixture is supplied. | `live_tested=false`; `production_supported=false`. No server URL/schema is verified per [COROS_MCP.md](COROS_MCP.md). | `commercial_approval_required=true`; status is `PENDING_PROVIDER_APPROVAL`. A compatible server and per-account token are required technically. | `none`. | `ai_evidence_eligible=true`, subject to metadata restrictions and configured service account scoping. | `PENDING_PROVIDER_APPROVAL` |
| **Technogym / Mywellness** | Implemented OAuth2 connection, paged workout ingestion, raw detail capture and activity normalization. FIT/TCX upload code is contingent on the account access tier. | `fixture_tested=true`; client/sync tests use checked-in JSON fixtures and mocked HTTP. | `live_tested=false`; `production_supported=false`. No provider credentials or production acceptance evidence are recorded. | `commercial_approval_required=true`; actual access tier and upload permission must be confirmed with the provider. | `experimental_access_dependent`; this does not guarantee workout delivery. | `ai_evidence_eligible=true`, subject to metadata restrictions. | `EXPERIMENTAL` |
| **Fitbit food diary** | Implemented OAuth2 read-only nutrition integration. The selected date is fetched from Fitbit, not stored as a second Apex food log. | `fixture_tested=true`; `test_nutrition_integration.py` covers mocked behavior. | `live_tested=false`; `production_supported=false`. Real Fitbit authorization was not exercised per `UI_DATA_CHANGES.md`. | `commercial_approval_required=null` (not established here); registered app credentials, nutrition scope and user consent are required technically. | `none`. | `ai_evidence_eligible=false`; not a performance evidence source. | `EXPERIMENTAL` |
| **Google Fit export / generic CSV** | No direct Google Fit ingestion or Google-specific normalization is implemented. Generic CSV upload supports manually mapped workout and daily-metric rows under `csv_import`. | `google_fit` has `fixture_tested=false`; `test_csv_import.py` covers generic CSV only, not a Google Fit export contract. | `live_tested=false`; `production_supported=false`. No export-format validation is evidenced. | `commercial_approval_required=null`; user-supplied generic CSV requires no Google API credentials. | `none`. | `ai_evidence_eligible=false` for this provider path. | `MANUAL_IMPORT` |

## How to read these statuses

- **Private-alpha implementation** describes code and application behavior in
  this repository. It is not a service-level commitment or production support
  claim.
- **Fixture/mock coverage** establishes behavior against the supplied test
  shapes. It does not establish that a provider currently returns those shapes.
- **Live verification** would require a dated record of an actual authorized
  provider session, with the tested scope and outcome. There is no such evidence
  for the provider paths above in the repository's current validation record.
- **Production validation** would require operation in the intended deployment
  with monitoring and a documented success window. It is not inferred from CI,
  a passing connector test, or the presence of OAuth code.
- **Commercial approval** is separate from technical OAuth/API access. The
  codebase cannot establish that the operator's use, user count, data use, or
  deployment has provider approval. Check current provider terms and account
  entitlements before enabling a connector for other people.

The current implementation's AI origin allowlist lives in
`backend/app/services/evidence.py`. It includes Garmin, FIT, manual, web,
WHOOP, Oura, COROS and Technogym, with additional metadata restrictions. Strava
is deliberately absent. Apple ZIP data follows a separate import path and is
not in this allowlist. These statements describe repository policy, not a
claim that AI outputs are clinically validated.
