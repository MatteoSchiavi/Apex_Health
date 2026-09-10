# Garmin fixtures — the ONLY thing connector tests talk to (§0, §16.7, §20)

Synthetic payloads shaped exactly like the `garminconnect` endpoint responses
the connector consumes. They are the recorded contract: if the real API drifts,
the parser breaks against the live account, the raw row stays unprocessed, and
the fix is re-validated against this corpus — never against a real account from
automated code.

Layout:
- `activities.json` — activity summaries, newest first (Garmin returns them
  paginated; tests exercise pagination with page_size=3 -> 2 pages)
- `streams/{activity_id}.json` — per-sample streams; 7101 carries semicircle
  GPS positions, 7102 carries degrees (parser accepts both). 7103/7104 have no
  stream files (gym/manual activities) -> empty fetch.
- `sleep/{date}.json` — the session ENDING (waking up) that local morning (§17)
- `hrv/{date}.json`, `stress/{date}.json` — intraday readings + daily summary
- `stats/{date}.json`, `body_composition/{date}.json` — daily aggregates
  (weight is in grams upstream; the normalizer converts)

Built-in drill cases:
- activity 7104 starts 2025-03-08 23:30 GMT = 2025-03-09 00:30 in
  Europe/Rome — proves the §17 day-boundary rule (local_date 03-09, not the
  UTC day 03-08), and its `walking` typeKey exercises the documented
  discipline fallback (`gym_general`).
- `sleep/2025-03-02.json` is malformed (upstream shape change drill): its raw
  row must stay `processed=false` while every other payload normalizes.
- Days 2025-03-01 backward are empty: backfill stops after 10 consecutive
  empty days — the source's history boundary, not a missed fetch.
