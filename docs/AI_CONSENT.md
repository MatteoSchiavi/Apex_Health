# Voluntary AI authorization and budgets

AI consent is a separate unticked control in progressive Profile/onboarding and Settings. It is independent of account creation, Terms and provider permissions. The disclosure precedes the control, links the operator's existing privacy notice, names the configured endpoint identity and explains selected context/documents, reviewable output, withdrawal, historical retention, export and deletion. The public privacy page carries the same disclosure.

Consent records account, status, `athlete-ai-consent-v1`, purpose, configured provider identity, accepted timestamp and withdrawal timestamp. Acceptance/withdrawal audit events retain only policy/identity/timestamp metadata, not athlete notes. Endpoint identities exclude credentials and query parameters and include enabled completion endpoints and optional embedding origin. A policy/provider change invalidates the old grant. There is no migrated consent for existing users.

Effective access requires enabled server policy, a present enabled account credential with an allowed persisted tier, active matching consent a configured provider identity and an available account budget. The states are:

- `disabled`: no new external completion or embedding is authorized, including when the account budget is exhausted.
- `basic`: existing `cheap_only` tier; onboarding extraction and simple read-only assistance. Model-facing write tools, powerful/medical routing, strategic coaching and reports are blocked.
- `full`: existing `full` tier; typed reviewable proposals are allowed, while approval and execution remain outside the agent.

Client profile/chat input cannot raise account access. Source/document ownership, review and AI eligibility remain independent gates. User text/profile/documents are fenced as untrusted data. Neither access level exposes SQL, filesystem, arbitrary fetch/code/device execution, approval or arbitrary document authority to the model.

Every completion and optional journal embedding passes the shared guard. Authorization is checked before reservation and again immediately before invocation. Withdrawal blocks subsequent calls, including later calls in an agent turn. Requests already sent to a provider cannot be recalled; withdrawal does not retroactively delete historic records or third-party copies. Source erasure and final snapshot checks prevent an in-flight report from recreating erased local evidence.

## Atomic pre-call budget

A PostgreSQL account advisory lock serializes daily reservations and consent transitions. Reservations commit before provider I/O. Categories are onboarding extraction (40,000 tokens), standard chat (80,000), strategic coaching (100,000), and periodic reports (80,000), beneath the account's configured daily token ceiling (default 160,000) and estimated USD ceiling (default $0.25). UTC is the explicit budget reset boundary, independent of local training days.

Input UTF-8 bytes conservatively bound tokens, with the client output maximum of 4,096 reserved before invocation. Estimated cost reserves the conservative existing rate envelope. Account and category exhaustion rejects before the provider is called. Successful reported usage reconciles the reservation. Timeouts, failures, cancellations and unreported usage retain the conservative reservation; a timeout does not prove the provider did not bill it. Historic usage rows are included without double counting reconciled ledger costs.

`AI_PROCESSING_ENABLED=false` is the operator's global stop. `AI_DAILY_TOKEN_LIMIT` configures the account token ceiling. `DAILY_TOKEN_BUDGET_USD<=0` disables only the estimated USD ceiling, not consent/token/category checks. The state/budget endpoint is account-scoped and the UI exposes category balances. Custom-provider invoices/pricing are operator facts; estimates are not billing guarantees.

Consent and budget ledgers are retained account records unless removed by account/operator deletion; the existing selected AI/tool logs have their documented cleanup windows. Profile deletion clears profile notes and managed targets. Source deletion, reviewed document deletion, selected-record export and operator account deletion retain their existing separate meanings. Backups and remote provider retention require the operator's documented policy; Apex does not assert that withdrawal erases them. See [SECURITY.md](SECURITY.md), [DATA_LIFECYCLE.md](DATA_LIFECYCLE.md) and [LEGAL_DEPLOYMENT.md](LEGAL_DEPLOYMENT.md).
