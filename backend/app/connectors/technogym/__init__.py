"""Technogym connector package (MASTER_SPEC §11, §23 Phase 6).

Stage 11a (build regardless): OAuth2 enduser-to-enduser flow, pull completed
sessions raw-first into `raw_ingest` -> `activities` (full history, §6.3),
optional FIT/TCX upload. Stage 11b (contingent on the real access tier, §24)
stays behind `sync_plan_to_technogym`'s documented fallback until the owner
confirms what the registered client may call.

Automated tests use recorded fixtures only (§0/§16.7/§20) — the real OAuth
connection is the owner's manual step (tools/technogym_connect.py or the
/settings/integrations endpoints).
"""
