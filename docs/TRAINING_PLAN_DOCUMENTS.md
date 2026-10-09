# Reviewed document baselines

1. Upload through existing Lab/Documents. Original bytes and reviewed excerpts remain encrypted and account-scoped.
2. Review and confirm the current document hash/revision. Upload alone does not make it planning or AI context.
3. Select “Use this as my active plan” to prepare a manual structured draft, or explicitly request AI extraction with active consent, authorization and extraction budget. Only the reviewed excerpt is used; source text is untrusted data.
4. Review dates, weekly structure, actual sports/workouts, duration/distance/intensity targets, protection and ambiguous items. Unknown dates/durations remain null. Edit the structure instead of filling a missing value automatically.
5. Acknowledge the reviewed structure and activate its exact hash. Activation requires actual plan dates and at least one dated workout. Missing intensity/duration may remain unknown; unsupported sports and stale document/extraction versions reject.

Draft structures are encrypted. Versions, source-document revisions, payload hashes, extraction method and confirmation timestamps are preserved. Identical structure retries return the same version. Revising creates another draft; old drafts cannot activate after a newer revision. Confirmation retries return the same plan receipt rather than creating another plan.

Confirmation creates the shared active training baseline. Previous document baselines retain their records with supersession dates. Protected upcoming sessions reject replacement until explicitly unprotected. Historical completed/partial/skipped session identities persist, including their explicit recorded association and check-in. Deleting an original deactivates its planning baseline while preserving historical workout records and already confirmed provenance fields where possible; source-document/draft references follow the migration's deletion behavior.

Whole-plan and workout protection are explicit revision-controlled controls. Protected workouts reject typed edits rather than being silently moved/replaced. Normal proposals remain exact local diffs with evidence, data gaps, objective uncertainty/deferral, approval/rejection, receipt and undo. Activation is a user's baseline selection; it is not a model-facing approval tool.

The extractor is not a verifier of a coach's intent. Athletes must inspect every extracted session. A structured draft cannot make absent source values reliable. This release supports the existing bounded document parsers, not handwritten-plan OCR or a full season optimization engine. Manual review is usable with AI entirely disabled.
