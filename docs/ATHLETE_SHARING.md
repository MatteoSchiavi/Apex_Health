# Explicit athlete sharing

A share is a **read-only, frozen snapshot** of exactly the fields reviewed by its authenticated owner. Creating a share does not send a message, publish a social post, create an AI grant, or permit any recipient to edit, delegate, or activate a plan.

## Review and creation

`POST /athlete/shares/preview` accepts `{selection, expires_in_days}`. `selection` is discriminated by `type`:

- `activity`: 1–20 owned canonical activity IDs; default fields are `date`, `discipline`, `duration_s`, `distance_m`.
- `workout`: 1–20 owned sessions in confirmed, active, or completed plans; default fields are `date`, `discipline`, `duration_min`, `distance_m`.
- `plan`: 1–20 owned confirmed, active, or completed plans; default fields are `title`, `starts_on`, `ends_on`, `session_count`.
- `progress`: `sport` (`running` or `cycling`), explicit `starts_on` and `ends_on` (at most 730 inclusive days), and selected aggregate fields (`volume`, `consistency`, `adherence`, `goal_progress`). Defaults are volume and consistency. This reuses the deterministic sport overview and never includes its private goal context, medical inputs, provider payloads, or activity provenance identifiers.

Resource selectors use `resource_ids`, finite `fields`, and `include_feedback` (default false). All names and shapes are defined in `backend/app/schemas/sharing.py`; arbitrary JSON paths are rejected. Activity HR, power, and elevation require selecting their specific fields. Workout descriptions, intensity targets, approved structured steps, and plan session instructions also require explicit field selection. Selecting structured steps includes the descriptions inside those approved blocks, which the preview displays.

Feedback is absent unless both `include_feedback=true` and specific feedback fields are selected. `feedback_note`, `modification_reason`, and `terrain_notes` are individually opt-in; enabling feedback alone does not include them. Pain and illness flags are excluded from this sharing contract. Progress adherence may include aggregate completion counts derived from explicit associations/check-ins, but does not expose individual feedback or notes.

The preview returns the complete snapshot, privacy notice, and `payload_hash`. Creation uses the identical request plus `preview_hash`; the server recomputes the snapshot and returns 409 if selected information changed. Expiry is an integer from 1 through 30 days, default 7. Snapshots are capped at 256 KB; oversized requests are refused rather than silently truncated. There may be at most 100 active grants per owner.

```json
{
  "selection": {
    "type": "activity",
    "resource_ids": [123],
    "fields": ["date", "discipline", "duration_s", "distance_m"],
    "include_feedback": false
  },
  "expires_in_days": 7
}
```

## Recipient access and revocation

Creation returns the 256-bit random capability once, as `token` and `url_fragment`. The browser places it in a URL **fragment**, never a path or query string, and reads `/sharing/view` using `X-Apex-Share`. The token must not be stored in localStorage or sent to analytics, logs, other tools, or an external messaging service. Standard HTTP access logs do not contain URL fragments or custom header contents; operators must not add this header to custom logging. Use HTTPS when transferring the private link.

`GET /athlete/shares` returns only the owner's metadata, never capability tokens or snapshot values. `DELETE /athlete/shares/{id}` revokes the grant and immediately erases its encrypted snapshot. Public reads refuse missing, malformed, unknown, revoked, expired, disabled-owner, or deleted-underlying-resource grants with the same unavailable response. Each read verifies that original dependency records remain owned and present; recipients cannot guess an ID to access a different record. Responses use no-store, no-referrer, and noindex headers.

Revocation blocks future reads. It cannot erase a screenshot, download, or copy that a recipient already saved. Changing source values does not silently change a reviewed snapshot; revoke and create a new one to share updates.

## Privacy, retention, and source rules

Only finite selected canonical values are serialized. No GPS/location, raw provider payload, sleep/HRV, medical record, private AI/chat context, imported source text, credentials, recipient identity, or bearer token is included in the snapshot by default. Source links are checked against the supported canonical-source allowlist; unsupported source records are refused. Record ownership is always enforced independently of the sharing capability. This does not relax existing AI source policies.

At rest, snapshots use the existing application encryption. Only a SHA-256 capability hash is stored. Selection metadata, dependency IDs, expiry, revocation timestamps, and sanitized creation/revocation audits remain available to the owner. Expired access is blocked immediately by time comparison. **Encrypted expired snapshots are erased lazily when the owner opens share management or the expired capability is requested.** There is currently no scheduled background purge, so an unused expired ciphertext can remain at rest until one of those actions occurs. Account deletion cascades grants; explicit revocation erases their ciphertext immediately.

Migration `0029` adds `athlete_shares` after `0028`. Downgrade refuses to discard any grant records; an owner-reviewed archival/erasure step is required first. No production migration, publication, or deployment is implied by this implementation.
