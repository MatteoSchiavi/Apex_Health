# Check-in generation recovery

The reported screen contains a deterministic recorded-data fallback. It does not prove a new AI attempt failed on that visit: a previously failed morning/afternoon slot is reused, and a concurrent visit can still be waiting for the original attempt. The successful Coach reply confirms that AI works for at least that conversation; check-ins use a separate, shorter response contract.

## Reproduced failure and correction

A valid native score written as `Body Battery 55/100`, with an exact source claim for `55`, was rejected as `UNCITED_NUMERIC_TEXT`: the general answer validator interpreted the unit's `100` as another measurement. Check-ins now remove the redundant scale only for a named score with a verified source claim and an actual `/100` source unit. The resulting answer goes through the unchanged full validator. Unverified values, other units, other denominators, unsafe advice and incorrect metric bindings still fail.

The check-in now requests JSON mode explicitly and supplies exact, server-checked claim examples with the `value` field. Its prompt asks for three short lines, qualitative weekly trends and no invented averages, counts or rounded measurements. The output allowance is 1,024 tokens, including JSON claims, instead of 650; visible content remains at most three lines. Reservations still use the requested bounded output allowance.

Provider HTTP failures expose fixed reason codes for credentials, configuration, incompatible requests, rate limiting and timeouts. Output truncation is distinct from measurement validation failure. Error bodies, credentials and rejected health narratives are not logged or returned.

## Saved attempts and recovery

- `POST /dashboard/check-in` remains the foreground-open generation trigger. The durable morning/afternoon claim is committed before external I/O.
- `GET /dashboard/check-in` only reads the saved slot or current recorded data. It does not create a claim, reserve budget, invoke a provider or retry generation.
- The optional “Why recorded data?” disclosure shows the attempt time and specific reason. Pending generation, disabled AI and exhausted budget have distinct labels.
- “Check saved summary” performs only the GET. It can collect a summary completed by another visit. A failed read preserves the current recordings, and an account change prevents a late response from updating the new account's cache.
- A pending attempt older than the generation deadline plus a grace period is reported as interrupted, without retrying it.
- Earlier failed slots retain their quota. Deploying this fix does not generate a third AI attempt or rerun an already consumed morning/afternoon slot. The next eligible foreground open can generate the next period's summary.

The exact reason for the original deployed attempt cannot be established from the quoted screen alone. This change fixes the reproduced score-format failure and makes future failures inspectable in the app. No production health data was sent to a provider for these tests.

## Validation

Regression coverage includes exact numeric JSON generation, source-backed score normalization, fabricated values and wrong units, safe cached failure codes, truncated output, concurrent generation, read-only recovery without budget or quota changes, consent, erasure during generation, account scope, and morning/afternoon limits. Browser checks cover English/Italian, both themes, phone/desktop, three visible lines, read failure recovery, and exactly one opening POST followed only by explicit GET reads.
