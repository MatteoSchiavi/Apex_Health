# Form and calendar recovery

This follow-up preserves Apex's existing interface while addressing interrupted
equipment, data-management, feedback and calendar workflows.

- Equipment creation locks submitted fields, retains failed input and clears only
  a successful creation. Retired equipment can be reactivated. Recording service
  refreshes maintenance history.
- Reminder edits survive activity associations, sport defaults, maintenance and
  background reads. Requests update only the reminder fields actually edited.
- Evidence inspection validates the selected observation identity and ignores
  late responses. Annotation drafts belong to one observation, require explicit
  discard before switching and remain intact after a failed save.
- Source deletion remains bound to its reviewed preview. Successful deletion
  clears affected cached measurements. Changing import format clears the actual
  selected file, and pending imports cannot be replaced by a dropped file.
- Feedback locks its submitted draft during requests, retains failed reports and
  preserves their original page across navigation. Reporting the current page
  requires explicitly discarding the previous draft.
- Calendar loading and failed sources are distinguished from a truly empty day.
  Failed sources can be retried; successful sync also refreshes calendar and
  equipment queries.

Browser regressions cover English and Italian, light and dark themes, phone and
desktop widths, delayed and failed reads/writes, draft preservation and request
identity. Full release validation is recorded in the associated pull request.
These synthetic checks do not establish real Garmin account acceptance, live
Coach usefulness or physical-device keyboard usability.
