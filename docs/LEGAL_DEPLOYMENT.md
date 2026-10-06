# Legal deployment review for Apex Health

This is an implementation checklist, not a certification of legal compliance. The default scope is a private, self-hosted instance for the owner and individually invited friends in Italy/EU. The public English and Italian pages describe the code as inspected on 5 October 2026. The operator must check the actual deployment and obtain qualified Italian/EU legal advice where needed. The official sites below could not be fetched from this cloud environment: its proxy returned HTTP 403 for EUR-Lex and the Italian Garante. The links are primary source references for the operator to verify, not a claim of live legal research.

## Required deployment facts

Set these non-secret variables in the deployment `.env` before inviting users. `GET /legal/config` exposes them publicly. Empty fields produce a visible incomplete-notice warning. Filling them removes that warning but does not by itself establish a valid legal basis or complete review.

| Variable | Required decision |
| --- | --- |
| `LEGAL_CONTROLLER_NAME` | Actual person or entity deciding the purposes and means of processing. Do not assume the software author is the controller. |
| `LEGAL_CONTROLLER_ADDRESS`, `LEGAL_CONTACT_EMAIL` | Reachable address and privacy contact; add DPO contact if one is legally required. |
| `LEGAL_EFFECTIVE_DATE` | Date on which the operator adopted these notices. |
| `LEGAL_ACCOUNT_BASIS` | Specific GDPR Article 6 basis or bases for account, service, security, and related processing, with purpose mapping. |
| `LEGAL_HEALTH_BASIS` | Specific GDPR Article 9(2) condition for health data. If explicit consent is chosen, implement an informed, specific, recorded and withdrawable choice *before* health-data collection; the current invite flow does not do that. |
| `LEGAL_HOSTING_REGION`, `LEGAL_BACKUP_LOCATION` | Actual server and local/offsite backup regions. Check any CDN, reverse proxy and logs too. |
| `LEGAL_AI_PROCESSOR` | Actual enabled chat, embedding and voice providers and their processing locations; distinguish each if different. |
| `LEGAL_TRANSFER_DETAILS` | Actual non-EEA destinations, transfer mechanism and safeguards, or an accurate statement that none occur. |

Review who acts as controller/processor for invited friends. A private, self-hosted, invite-only service is **not automatically** exempt under the GDPR household exception; the facts of the activity matter. Keep registration closed to named invites and avoid public distribution or claims of clinical use under the current scope. Decide whether children may join and add appropriate age/parental controls if so. If the service becomes public, paid, or clinical, revisit consumer terms, provider contracts, accessibility, advertising/tracking, medical-device and AI rules before expanding it. This checklist does not recommend making the service public.

## Data-flow findings to verify in operation

The app stores health and training records in PostgreSQL, imports from optional Garmin, WHOOP, Oura, Strava, COROS, Technogym, Fitbit nutrition and CSV/FIT sources, and can use Open-Meteo. Its chat model endpoint is configurable by tier; text embeddings and voice transcription use an OpenAI-compatible endpoint by default. Prompt context can include profile, goals, injuries, events and recent metrics. An operator must verify configured endpoints and whether provider contracts permit these uses, sign Article 28 processor agreements where required, and disclose material recipients and transfer safeguards.

The app uses `hcc_session` and `csrf_token` for authentication and CSRF protection. The frontend also uses localStorage for theme/language, sync state, selected chat and an unsent chat draft. That draft can contain health text. Account-specific keys are cleared on logout, auth failure or session change, but can remain on a shared browser after abrupt closure until a new session check; users should clear site data there. There is no advertising or analytics script in the inspected app code. Check the deployed host and any injected scripts separately. Essential security cookies need clear information; adding optional tracking requires an appropriate prior choice under applicable ePrivacy/Italian cookie rules. Do not add a consent banner merely for the two necessary cookies.

The existing `GET /lab/export/account.json` and `GET /lab/export/observations.csv` are account export tools, but the JSON export is a selected-table export with a 100,000-row-per-table cap. It now includes profile, chat history and AI reports, but does not contain every record, original uploaded document bytes or credentials. Do not describe it as a complete GDPR Article 15 response or a guaranteed Article 20 portable export. `GET /lab/sources/{source}/deletion-preview` followed by `POST /lab/sources/{source}/delete` erases source-linked data and some caches, not the whole account. A full account-erasure request currently needs an operator-run process; verify scope and backups before promising completion. A disconnected service can re-import data if reconnected.

Scheduled cleanup targets processed raw imports after 180 days, qualifying activity streams after 400 days, and selected AI/tool/sync logs after 400 days. Per-user lab observation and agent-log preferences have a separate daily prune task. Expired sessions are purged. Other records do not share a single account-wide retention limit. Encrypted local backups default to up to 14 daily and 6 monthly archives; Backblaze B2 upload is optional. Automatic-update recovery backups are stored separately under `backups/deployments/` and require operator retention/deletion; see [AUTO_UPDATES.md](AUTO_UPDATES.md). Confirm offsite lifecycle and document how deletions remain excluded on restore. Publish only retention promises that match enabled scheduled jobs and actual archive policy.

AI outputs are estimates, and the app should not be presented as a diagnostic or therapeutic device without a separate intended-purpose and regulatory assessment. The current code does not appear to take solely automated decisions with legal or similarly significant effects; review this if it begins controlling access, benefits, clinical treatment or employment. Consider a GDPR Article 35 DPIA if the actual scale, sensitivity and processing risks trigger it. Maintain security, incident, rights-request and breach-response procedures, including processor agreements and access controls; a web notice alone cannot supply them.

## Primary sources to check

- [GDPR, Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj): Articles 2(2)(c), 5–6, 9, 12–15, 17–22, 25, 28, 32–35 and 44–49.
- [ePrivacy Directive 2002/58/EC](https://eur-lex.europa.eu/eli/dir/2002/58/oj): Article 5(3), as amended by Directive 2009/136/EC, for storage or access on user devices.
- [Italian Garante cookie guidelines, 10 June 2021](https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/9677876): distinguish technical storage from optional tracking and check current updates.
- [Medical Device Regulation (EU) 2017/745](https://eur-lex.europa.eu/eli/reg/2017/745/oj): Article 2 intended medical purpose; software qualification depends on intended use and claims.
- [EU AI Act, Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj): assess applicability to actual AI function and deployment rather than assuming a category.

These sources and deployment facts require current legal review. The cloud environment blocked direct retrieval of EUR-Lex and Garante (HTTP 403 on 5 October 2026), so this document does not assert that the latest official guidance was checked live.
