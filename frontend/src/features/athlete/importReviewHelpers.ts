import type { ImportProposal } from "./importTypes";

// Evidence paths use row indexes; keep surviving quotes beside the same facts
// when a user discards a row. Removed evidence remains an unapproved history.
export function removeImportRow(proposal: ImportProposal, kind: "weekly" | "dated", index: number): ImportProposal {
  const prefix = kind === "weekly" ? "weekly.rows" : "dated.sessions";
  const rowPath = new RegExp(`^${prefix.replaceAll(".", "\\.")}\\.(\\d+)(\\.|$)`);
  function remap(field: string) {
    const match = field.match(rowPath);
    if (!match) return field;
    const old = Number(match[1]);
    return old === index ? "excluded." + field : old > index ? field.replace(rowPath, `${prefix}.${old - 1}${match[2]}`) : field;
  }
  const sources = proposal.sources.map(source => ({ ...source, field: remap(source.field) }));
  const issues = proposal.issues.map(issue => ({ ...issue, field: remap(issue.field) })).filter(issue => !issue.field.startsWith("excluded."));
  if (kind === "weekly" && proposal.weekly) {
    const rows = proposal.weekly.rows.filter((_, i) => i !== index);
    return { ...proposal, weekly: rows.length ? { ...proposal.weekly, rows } : null, sources, issues };
  }
  if (kind === "dated" && proposal.dated) return { ...proposal, dated: { ...proposal.dated, sessions: proposal.dated.sessions.filter((_, i) => i !== index) }, sources, issues };
  return proposal;
}
