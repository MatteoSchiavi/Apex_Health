/** References emitted by changes_propose in backend/app/agent/loop.py. */
export function referencedProposalLinks(drafts: unknown): { id: number; href: string }[] {
  if (!Array.isArray(drafts)) return [];
  const seen = new Set<number>();
  return drafts.flatMap((draft: unknown) => {
    if (!draft || typeof draft !== "object" || Array.isArray(draft)) return [];
    const { type, id } = draft as Record<string, unknown>;
    if (type !== "change" || typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0 || seen.has(id)) return [];
    seen.add(id);
    return [{ id, href: `/app/coach?tab=changes#change-${id}` }];
  });
}
