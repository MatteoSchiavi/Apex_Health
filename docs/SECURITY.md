# Security and encryption posture

New external AI calls require separate voluntary, policy/provider-bound consent as well as server/account/source authorization and atomic pre-call budgets. Withdrawal blocks subsequent completions and embeddings. Encrypted reviewed plan drafts preserve document ownership and explicit activation. See [AI_CONSENT.md](AI_CONSENT.md) and [TRAINING_PLAN_DOCUMENTS.md](TRAINING_PLAN_DOCUMENTS.md).

Apex is designed for a private, invite-only deployment. Authentication,
ownership checks and encryption do not replace host security, provider review
or the operator's legal responsibilities. See [LEGAL_DEPLOYMENT.md](LEGAL_DEPLOYMENT.md).

## Secrets held by the operator

| Setting | Purpose |
|---|---|
| `ENCRYPTION_KEY` | Application encryption of integration credentials, uploaded document originals/excerpts and encrypted lab notes |
| `BACKUP_ENCRYPTION_KEY` | Independent encryption of nightly and deployment database backups |
| `SESSION_SECRET` | Session-token hashing and signed CSRF protection |
| `OWNER_PASSWORD` | Bootstrap owner login; stored account passwords are Argon2 hashes |
| `POSTGRES_PASSWORD` | Database authentication; existing volume passwords need deliberate rotation |

Optional provider credentials and the owner Telegram token are additional
secrets. Disk encryption, if configured by the operator, has separate keys.
Generate values locally using [INSTALL.md](INSTALL.md), store them securely,
keep `.env` out of Git and never paste keys into chat or logs. Authorized
debugging can use the securely configured application without sharing keys.
Preserve existing encryption keys during upgrades; changing settings does not
reencrypt old records. Store backup keys separately from backup artifacts.

## Encryption boundaries

Integration credentials and document bytes are encrypted using helpers in
`backend/app/core/encryption.py`. The application derives Fernet key material
from `ENCRYPTION_KEY`. Passwords are Argon2id hashes; browser session tokens
are stored as hashes rather than usable tokens. Invite codes remain capability
tokens visible to the owner and must be protected and revoked if leaked.

Queryable health observations, activities, features, journals, feedback and
other database fields are not all encrypted columns. Do not describe the whole
database as application-encrypted. Access to the running server or database
can expose these records. Full-disk encryption can protect offline storage
when the operator has configured it; Compose does not configure disk encryption.
It does not protect records from an authorized running application or a
compromised host with keys available.

Encrypted database backups are written under the host `backups/` mount.
The current format streams authenticated encrypted frames; restore tools retain
support for legacy Fernet archives. Optional B2 upload is separately configured.
Restore drills use disposable databases. Deployment backups have separate
retention from nightly backups; see [AUTO_UPDATES.md](AUTO_UPDATES.md).

## Browser and access controls

Use HTTPS for network-facing access. The API binds to loopback by default;
trusted proxy headers must be restricted to actual proxy peers. A
`COOKIE_SECURE=false` HTTP trial should remain on loopback.

Session cookies are HttpOnly, SameSite=Lax and Secure when enabled. Unsafe
requests require session-bound signed CSRF tokens. Ordinary sessions have a
12-hour default sliding inactivity lifetime and 30-day absolute cap, with
browser-session cookies. Remember Me has a rolling 30-day inactivity lifetime,
renewed at most daily and capped at 90 days; older rows keep their assigned cap.
Logout revokes the session. Disabling a friend in `/admin` revokes sessions and
blocks login. Owner roles and owner sessions cannot be revoked from that panel.

The SPA does not store session tokens in localStorage, but it does retain theme,
language, account-specific sync state, selected conversation and an unsent
chat draft. Drafts can contain health text. Account-specific keys are cleared
on logout/session change; clear site data on shared browsers. The PWA caches
public assets and a generic offline page, not private API responses.

Account ownership and persisted owner roles are checked in the backend;
frontend route guards alone are insufficient. Auth/AI endpoints are rate limited.
CSP, frame denial, nosniff, referrer policy and HTTPS-only HSTS are set by the
application; verify that the deployed reverse proxy preserves them. Runtime
containers are non-root and resource-limited.

## Operational notifications and incident handling

Owner Telegram is outbound-only and uses the existing API/worker. Feedback
notifications can contain account identity and user-entered text sent to an
external service. Operational logs intentionally omit arbitrary exception and
health payloads. Delivery/retention limits are in [OWNER_ADMIN.md](OWNER_ADMIN.md).

Revoke leaked unused invites and sessions through Settings or `/admin`.
Disable departed friends to stop access; this does not erase their records.
Whole-account erasure remains an operator process covering records, backups
and external notification copies. Source deletion is not whole-account erasure.

For a suspected credential/key leak, revoke affected provider credentials and
prepare an explicit rotation and migration plan before replacing keys. A leaked
backup plus its key can expose historical data; later rotation cannot undo that.
Verify recovery using retained keys and disposable restores. Introducing disk
encryption to an existing server requires a host-specific backup/migration plan;
do not format live data volumes as an application setup step.
