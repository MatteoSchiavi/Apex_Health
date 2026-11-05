# Garmin API migration

The runtime now uses Garmin's official Personal API exclusively for the owner's
own data. The previous password transport, global credential fallback, MFA flow,
placeholder adapter and third-party dependency have been removed. There is no
fallback from an API failure to a password login.

Existing measurements, Garmin source IDs, main-device choices and raw revisions
are retained. Saved password-session credentials cannot be reused: owner listings
return `reconnect_required`. Connect an API key in Settings; it is verified before
replacing the encrypted credential record. Friend accounts cannot use Personal
API keys. A separately approved Business API integration remains separate work.

The internal `GarminTransport` protocol remains the test boundary;
`build_live_client` selects only `GarminPersonalClient` for API-key credentials.
Generic normalizers continue reading historical raw formats so that migration does
not make old data unreplayable. These formats are compatibility data, not active
password authentication paths.

The 30-day pilot cap is removed. Original activity archives now pass through durable
raw storage and validated FIT projection. Additional official read surfaces are
archived without guessing medical units or treating raw retention as UI support.

Use [setup and data handling](GARMIN_PERSONAL_API.md) and the
[26-endpoint inventory](GARMIN_API_COVERAGE.md) as the current implementation contract.
The [October reopening decision](GARMIN_API_REOPENING_2026_10.md) and
[October acceptance](PERSONAL_API_ACCEPTANCE_2026_10.md) are historical records,
not evidence that this expanded revision has been tested on a live account.
