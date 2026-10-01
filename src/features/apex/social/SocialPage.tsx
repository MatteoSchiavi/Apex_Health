"use client";

/**
 * Apex Health — Social page (plan §9): Challenges & Rankings.
 *
 * The page's job: light friendly competition — where do I stand, what am I
 * in, who is winning.
 *
 * Layout (strictly per plan §9):
 *   Row 1, Where I stand (col-12): four tiles — one per headline metric
 *     (steps, activities, training load, sleep score): rank out of N,
 *     value, and the change since last week (DeltaChip).
 *   Row 2, Challenges and rankings (col-12 xl:col-7 + col-12 xl:col-5):
 *     Left, Active challenges: a card each — name, metric, days left,
 *     participant initials, a progress bar for you vs the leader, your
 *     rank, Join / Leave. Tapping opens the leaderboard drawer.
 *     "New challenge" button opens a drawer: name, metric, start, end.
 *     Right, Rankings: metric selector + period toggle (this week /
 *     this month / all time), table with the user's row highlighted.
 *   Row 3, Past challenges (col-12, collapsed): finished challenges with
 *     the winner and the user's finishing place.
 *   Privacy card (col-12, small): per-metric sharing switches. Steps,
 *     activities and distance on by default; sleep score and training
 *     load off until the user opts in.
 *
 * Restraint law — challenges exist as a feature, not as the design identity.
 * No streak graphics, no gold leader colour. Leader is bg-surface3.
 *
 * Data: client-side mock (no multi-user backend). Composes from
 * `challenges` in `@/lib/apex/data` (the canonical array) plus
 * `@/lib/apex/socialData.ts` (leaderboards, rankings, past, privacy).
 */

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Plus, Trophy } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { me, challenges as CANONICAL_CHALLENGES } from "@/lib/apex/data";
import { fmtDate, fmtInt } from "@/lib/apex/format";
import {
  ApexButton,
  Badge,
  Card,
  CardHeader,
  DeltaChip,
  Empty,
  Eyebrow,
  Hairline,
  PageHeader,
  RangeBar,
  Segmented,
} from "@/components/apex/kit";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  CHALLENGE_BOARDS,
  PAST_CHALLENGES,
  PRIVACY_DEFAULTS,
  PRIVACY_METRICS,
  RANKING_METRIC_LABEL,
  RANKING_METRIC_UNIT,
  findParticipant,
  getRanking,
  myRank,
  type ChallengeBoard,
  type PrivacyMetric,
  type RankingMetric,
  type RankingPeriod,
  type SocialParticipant,
} from "@/lib/apex/socialData";

/* ------------------------------------------------------------ main page */

export function SocialPage() {
  const t = useT();
  const ui = useApexUi();

  // Joined-challenge membership (client state; persisted in localStorage).
  // The canonical array has 3 challenges; start joined to ids 1 and 3 to show
  // both "Leave" and "Join" affordances.
  const [joinedIds, setJoinedIds] = useState<Set<number>>(() => {
    if (typeof window === "undefined") return new Set([1, 3]);
    try {
      const raw = window.localStorage.getItem("apex:challenge:joined");
      if (raw) return new Set(JSON.parse(raw) as number[]);
    } catch { /* ignore */ }
    return new Set([1, 3]);
  });

  const toggleJoined = (id: number) => {
    setJoinedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        window.localStorage.setItem("apex:challenge:joined", JSON.stringify([...next]));
      } catch { /* ignore */ }
      return next;
    });
  };

  // Privacy toggles — per-metric; persisted.
  const [privacy, setPrivacy] = useState<Record<PrivacyMetric, boolean>>(() => {
    if (typeof window === "undefined") return { ...PRIVACY_DEFAULTS };
    try {
      const raw = window.localStorage.getItem("apex:privacy:social");
      if (raw) return { ...PRIVACY_DEFAULTS, ...(JSON.parse(raw) as Partial<Record<PrivacyMetric, boolean>>) };
    } catch { /* ignore */ }
    return { ...PRIVACY_DEFAULTS };
  });

  const setPrivacyMetric = (key: PrivacyMetric, value: boolean) => {
    setPrivacy((prev) => {
      const next = { ...prev, [key]: value };
      try {
        window.localStorage.setItem("apex:privacy:social", JSON.stringify(next));
      } catch { /* ignore */ }
      return next;
    });
  };

  // Challenge leaderboard drawer + New-challenge drawer.
  const [openBoardId, setOpenBoardId] = useState<number | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [pastOpen, setPastOpen] = useState(false);

  // Rankings selectors.
  const [rankMetric, setRankMetric] = useState<RankingMetric>("steps");
  const [rankPeriod, setRankPeriod] = useState<RankingPeriod>("week");

  // Hide the user from the rankings table when they've opted out of that
  // metric. Per the plan, opting out hides you from the ranking.
  const rankingTable = useMemo(() => {
    const table = getRanking(rankMetric, rankPeriod);
    const exposed = privacy[metricToPrivacyKey(rankMetric)];
    if (exposed) return table;
    return { ...table, rows: table.rows.filter((r) => r.participant_id !== me.user_id) };
  }, [rankMetric, rankPeriod, privacy]);

  const userStats = useMemo(() => {
    return {
      steps:          myRank("steps", "week"),
      activities:     myRank("activities", "week"),
      training_load:  myRank("training_load", "week"),
      sleep_score:    myRank("sleep_score", "week"),
    };
  }, []);

  const visibleChallenges = CANONICAL_CHALLENGES.filter((c) => joinedIds.has(c.id));

  /* ----- render ----------------------------------------------------------- */

  return (
    <div className="mx-auto max-w-[1240px] space-y-4">
      <PageHeader
        title={t("social.title")}
        subtitle={t("social.subtitle")}
        actions={
          <ApexButton
            variant="primary"
            size="md"
            icon={<Plus size={14} strokeWidth={2.4} />}
            onClick={() => setNewOpen(true)}
          >
            {t("social_new_challenge")}
          </ApexButton>
        }
      />

      {/* ───────────────────────────────────── Row 1 — Where I stand */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StandTile
          metricLabel="Steps"
          unit="steps"
          stat={userStats.steps}
          goodWhen="up"
        />
        <StandTile
          metricLabel="Activities"
          unit=""
          stat={userStats.activities}
          goodWhen="up"
        />
        <StandTile
          metricLabel="Training load"
          unit="TSS"
          stat={userStats.training_load}
          goodWhen="up"
        />
        <StandTile
          metricLabel="Sleep score"
          unit="/100"
          stat={userStats.sleep_score}
          goodWhen="up"
        />
      </div>

      {/* ───────────────────────────────────── Row 2 — Challenges + Rankings */}
      <div className="grid grid-cols-12 gap-3">
        {/* Left — Active challenges */}
        <div className="col-span-12 xl:col-span-7 space-y-3">
          <Eyebrow>{t("social.active_challenges")}</Eyebrow>
          {visibleChallenges.length === 0 ? (
            <Empty
              title={t("social.empty")}
              action={
                <ApexButton variant="primary" size="sm" onClick={() => setNewOpen(true)}>
                  {t("social_new_challenge")}
                </ApexButton>
              }
            />
          ) : (
            visibleChallenges.map((c) => {
              const board = CHALLENGE_BOARDS.find((b) => b.challenge_id === c.id);
              return (
                <ChallengeCard
                  key={c.id}
                  challenge={c}
                  board={board}
                  joined={true}
                  onLeave={() => toggleJoined(c.id)}
                  onOpen={() => setOpenBoardId(c.id)}
                  t={t}
                  locale={ui.locale}
                />
              );
            })
          )}
          {/* Available (un-joined) challenges — show as Join cards */}
          {CANONICAL_CHALLENGES.filter((c) => !joinedIds.has(c.id)).map((c) => (
            <ChallengeCard
              key={c.id}
              challenge={c}
              board={CHALLENGE_BOARDS.find((b) => b.challenge_id === c.id)}
              joined={false}
              onJoin={() => toggleJoined(c.id)}
              onOpen={() => setOpenBoardId(c.id)}
              t={t}
              locale={ui.locale}
            />
          ))}
        </div>

        {/* Right — Rankings */}
        <div className="col-span-12 xl:col-span-5">
          <Card>
            <CardHeader eyebrow={t("social_rankings")} title={RANKING_METRIC_LABEL[rankMetric]} />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Segmented<RankingMetric>
                value={rankMetric}
                onChange={setRankMetric}
                options={[
                  { value: "steps",         label: RANKING_METRIC_LABEL.steps },
                  { value: "activities",    label: RANKING_METRIC_LABEL.activities },
                  { value: "training_load", label: RANKING_METRIC_LABEL.training_load },
                  { value: "sleep_score",   label: RANKING_METRIC_LABEL.sleep_score },
                ]}
                size="sm"
              />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <Segmented<RankingPeriod>
                value={rankPeriod}
                onChange={setRankPeriod}
                options={[
                  { value: "week",  label: t("social_period_week") },
                  { value: "month", label: t("social_period_month") },
                  { value: "all",   label: t("social_period_all") },
                ]}
                size="sm"
              />
            </div>

            {rankingTable.rows.length === 0 ? (
              <div className="mt-4">
                <Empty title="You're opted out of this ranking" /* TODO i18n */ body={t("social_privacy_note")} />
              </div>
            ) : (
              <div className="mt-3 overflow-hidden rounded-[var(--radius-control)] border border-hairline">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-hairline bg-surface2/40 text-faint">
                      <th className="eyebrow px-3 py-2 text-left">#</th>
                      <th className="eyebrow px-3 py-2 text-left">Name</th>
                      <th className="eyebrow px-3 py-2 text-right">Value</th>
                      <th className="eyebrow px-3 py-2 text-right">Δ wk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rankingTable.rows.map((row, i) => {
                      const p = findParticipant(row.participant_id);
                      const isMe = row.participant_id === me.user_id;
                      const unit = RANKING_METRIC_UNIT[rankingTable.metric];
                      return (
                        <tr
                          key={row.participant_id}
                          className={`border-b border-hairline last:border-b-0 ${
                            isMe ? "bg-primarySoft/60" : "hover:bg-surface2/40"
                          }`}
                        >
                          <td className="num mono px-3 py-2 text-muted">{i + 1}</td>
                          <td className="px-3 py-2 text-ink2">
                            <span className="font-medium">{p?.name ?? "Unknown"}</span>
                            {isMe && (
                              <span className="ml-1.5 eyebrow !text-[9px] text-primaryText">YOU</span>
                            )}
                          </td>
                          <td className="num mono px-3 py-2 text-right font-semibold text-ink">
                            {fmtInt(row.value)}{unit ? <span className="ml-1 text-[10px] font-normal text-faint">{unit}</span> : null}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <DeltaChip delta={row.value - row.prev_value} unit={unit} goodWhen="up" compact />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* ───────────────────────────────────── Row 3 — Past challenges (collapsed) */}
      <div>
        <button
          type="button"
          onClick={() => setPastOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-3 rounded-[var(--radius-card)] border border-hairline bg-surface px-4 py-3 text-left transition-colors hover:bg-surface2/40"
        >
          <div>
            <Eyebrow>{t("social_past")}</Eyebrow>
            <div className="num mt-0.5 text-[13px] font-semibold text-ink">
              {PAST_CHALLENGES.length} finished · {PAST_CHALLENGES.filter((p) => p.my_rank <= 3).length} podiums
            </div>
          </div>
          <div className="text-faint">
            {pastOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
        </button>
        {pastOpen && (
          <Card pad={false} className="mt-2">
            <div className="divide-y divide-hairline">
              {PAST_CHALLENGES.map((p) => {
                const winner = findParticipant(p.winner_id);
                return (
                  <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-semibold text-ink">{p.title}</div>
                      <div className="num mt-0.5 text-[11px] text-muted">
                        {p.metric} · {fmtDate(p.ended_at, ui.locale)} · {fmtInt(p.total_participants)} participants
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-[11px]">
                      <div className="flex items-center gap-1.5">
                        <Trophy size={11} className="text-faint" />
                        <span className="num text-muted">
                          <span className="font-semibold text-ink2">{winner?.name ?? "—"}</span>
                          <span className="ml-1.5 text-faint">won</span>
                        </span>
                      </div>
                      <Badge tone={p.my_rank <= 3 ? "positive" : "neutral"} dot={p.my_rank <= 3}>
                        {t("social_rank", { n: p.my_rank, total: p.total_participants })}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        )}
      </div>

      {/* ───────────────────────────────────── Privacy card */}
      <Card className="bg-surface2">
        <CardHeader eyebrow={t("social_privacy")} title={"Per-metric sharing" /* TODO i18n */} />
        <p className="mt-1 text-[12px] leading-relaxed text-muted">{t("social_privacy_note")}</p>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {PRIVACY_METRICS.map((m) => (
            <div
              key={m.key}
              className="flex items-center justify-between rounded-[var(--radius-control)] border border-hairline bg-surface px-3 py-2"
            >
              <div>
                <div className="text-[12px] font-medium text-ink2">{m.label}</div>
                <div className="num text-[10px] text-faint">
                  {m.key === "sleep_score" || m.key === "training_load"
                    ? "Off until you opt in"
                    : "Shared by default"}
                </div>
              </div>
              <Switch
                checked={privacy[m.key]}
                onCheckedChange={(v) => setPrivacyMetric(m.key, v)}
                aria-label={`Share ${m.label}`}
              />
            </div>
          ))}
        </div>
      </Card>

      {/* ───────────────────────────────────── Challenge leaderboard drawer */}
      <ChallengeBoardSheet
        openId={openBoardId}
        onClose={() => setOpenBoardId(null)}
        t={t}
        locale={ui.locale}
      />

      {/* ───────────────────────────────────── New challenge drawer */}
      <NewChallengeSheet open={newOpen} onClose={() => setNewOpen(false)} t={t} />
    </div>
  );
}

/* ------------------------------------------------------------ Row 1 stand tile */

function StandTile({
  metricLabel,
  unit,
  stat,
  goodWhen,
}: {
  metricLabel: string;
  unit: string;
  stat: { rank: number; total: number; value: number; delta: number } | null;
  goodWhen: "up" | "down" | "none";
}) {
  if (!stat) {
    return (
      <Card className="bg-surface2">
        <Eyebrow>{metricLabel}</Eyebrow>
        <div className="mt-2 text-[13px] text-muted">No data</div>
      </Card>
    );
  }
  return (
    <Card className="bg-surface2">
      <div className="flex items-center justify-between gap-2">
        <Eyebrow>{metricLabel}</Eyebrow>
        <Badge tone={stat.rank === 1 ? "positive" : stat.rank <= 3 ? "primary" : "neutral"} dot={stat.rank === 1}>
          #{stat.rank} / {stat.total}
        </Badge>
      </div>
      <div className="num mt-2 text-[26px] font-bold leading-8 tracking-[-0.02em] text-ink">
        {fmtInt(stat.value)}
        {unit && <span className="ml-1.5 text-[11px] font-medium text-muted">{unit}</span>}
      </div>
      <div className="mt-1">
        <DeltaChip delta={stat.delta} unit={unit} goodWhen={goodWhen} compact />
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------ Row 2 challenge card */

interface ChallengeCardProps {
  challenge: (typeof CANONICAL_CHALLENGES)[number];
  board: ChallengeBoard | undefined;
  joined: boolean;
  onJoin?: () => void;
  onLeave?: () => void;
  onOpen: () => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
  locale: "en" | "it";
}

function ChallengeCard({
  challenge,
  board,
  joined,
  onJoin,
  onLeave,
  onOpen,
  t,
  locale,
}: ChallengeCardProps) {
  const { title, metric, unit, my_value, leader_value, my_rank, total_participants, ends_at } = challenge;

  const gap = Math.max(0, leader_value - my_value);
  const daysLeft = Math.max(0, Math.ceil((new Date(ends_at).getTime() - Date.now()) / (24 * 3600 * 1000)));

  // Participant initials (from the board; fall back to a 4-char "MS · LR · MB…").
  const participants: SocialParticipant[] = (board?.rows ?? [])
    .map((r) => findParticipant(r.participant_id))
    .filter((p): p is SocialParticipant => p !== undefined)
    .slice(0, 5);

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={onOpen} className="min-w-0 text-left">
          <h3 className="text-[14px] font-semibold tracking-[-0.01em] text-ink hover:text-primaryText">
            {title}
          </h3>
          <div className="num mt-0.5 text-[11px] text-muted">
            {metric} · {unit}
          </div>
        </button>
        <div className="num shrink-0 text-right text-[11px] text-faint">
          <div className="eyebrow !text-[10px]">{daysLeft}d left</div>
          <div className="mt-0.5">{fmtDate(ends_at, locale)}</div>
        </div>
      </div>

      {/* Your progress vs leader */}
      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="num mono text-[22px] font-bold leading-7 tracking-[-0.02em] text-ink">
          {fmtInt(my_value)}
          <span className="ml-1.5 text-[11px] font-medium text-muted">{unit}</span>
        </div>
        <div className="num text-[11px] text-muted">
          {t("social.vs_leader", { gap: fmtInt(gap), unit })}
        </div>
      </div>
      <div className="mt-2">
        <RangeBar
          value={my_value}
          low={0}
          high={leader_value}
          tone={my_rank === 1 ? "positive" : "primary"}
          unit={unit}
          height={5}
        />
      </div>

      {/* 3-stat strip */}
      <div className="mt-4 grid grid-cols-3 gap-2">
        <MiniStat label={t("social.my_rank")}>
          <span className="mono">#{fmtInt(my_rank)}</span>
        </MiniStat>
        <MiniStat label={t("social.participants_count")}>
          <span className="mono">{fmtInt(total_participants)}</span>
        </MiniStat>
        <MiniStat label={t("social.leader_value")}>
          <span className="mono">{fmtInt(leader_value)}</span>
        </MiniStat>
      </div>

      {/* Participant initials */}
      {participants.length > 0 && (
        <div className="mt-3 flex items-center gap-1.5">
          {participants.map((p) => (
            <span
              key={p.id}
              title={p.name}
              className={`num mono inline-flex h-6 w-6 items-center justify-center rounded-full text-[9px] font-bold ${
                p.is_me ? "bg-primary text-white" : "bg-surface3 text-muted"
              }`}
            >
              {p.initials}
            </span>
          ))}
          {total_participants > participants.length && (
            <span className="num text-[10px] text-faint">+{total_participants - participants.length}</span>
          )}
        </div>
      )}

      <Hairline className="my-3" />

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="text-[11px] font-semibold text-primaryText hover:underline"
        >
          View leaderboard →
        </button>
        {joined ? (
          <ApexButton variant="secondary" size="sm" onClick={onLeave}>
            {t("social_leave")}
          </ApexButton>
        ) : (
          <ApexButton variant="primary" size="sm" onClick={onJoin}>
            {t("social_join")}
          </ApexButton>
        )}
      </div>
    </Card>
  );
}

function MiniStat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2">
      <div className="eyebrow truncate">{label}</div>
      <div className="num mt-1 text-[14px] font-semibold leading-5 text-ink">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------ Challenge board sheet */

function ChallengeBoardSheet({
  openId,
  onClose,
  t,
  locale,
}: {
  openId: number | null;
  onClose: () => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
  locale: "en" | "it";
}) {
  const challenge = CANONICAL_CHALLENGES.find((c) => c.id === openId) ?? null;
  const board = CHALLENGE_BOARDS.find((b) => b.challenge_id === openId) ?? null;

  return (
    <Sheet open={openId !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{challenge?.title ?? ""}</SheetTitle>
          <SheetDescription>
            {challenge ? `${challenge.metric} · ${challenge.unit}` : ""}
          </SheetDescription>
        </SheetHeader>

        {challenge && board && (
          <div className="space-y-3 px-4 pb-6">
            <div className="num text-[11px] text-muted">
              Ends {fmtDate(challenge.ends_at, locale)} · {fmtInt(challenge.total_participants)} participants
            </div>

            <div className="overflow-hidden rounded-[var(--radius-control)] border border-hairline">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-hairline bg-surface2/40 text-faint">
                    <th className="eyebrow px-3 py-2 text-left">#</th>
                    <th className="eyebrow px-3 py-2 text-left">Name</th>
                    <th className="eyebrow px-3 py-2 text-right">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {[...board.rows]
                    .sort((a, b) => b.value - a.value)
                    .map((row, i) => {
                      const p = findParticipant(row.participant_id);
                      const isMe = row.participant_id === me.user_id;
                      return (
                        <tr
                          key={row.participant_id}
                          className={`border-b border-hairline last:border-b-0 ${
                            isMe ? "bg-primarySoft/60" : "hover:bg-surface2/40"
                          }`}
                        >
                          <td className="num mono px-3 py-2 text-muted">{i + 1}</td>
                          <td className="px-3 py-2 text-ink2">
                            <span className="font-medium">{p?.name ?? "Unknown"}</span>
                            {isMe && (
                              <span className="ml-1.5 eyebrow !text-[9px] text-primaryText">YOU</span>
                            )}
                          </td>
                          <td className="num mono px-3 py-2 text-right font-semibold text-ink">
                            {fmtInt(row.value)}
                            <span className="ml-1 text-[10px] font-normal text-faint">{challenge.unit}</span>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>

            <div className="rounded-[var(--radius-control)] border border-hairline bg-surface2 p-3 text-[11px] leading-relaxed text-muted">
              Your rank: <span className="font-semibold text-ink2">#{challenge.my_rank}</span> of {fmtInt(challenge.total_participants)} —
              {fmtInt(Math.max(0, challenge.leader_value - challenge.my_value))} {challenge.unit} behind the leader.
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

/* ------------------------------------------------------------ New challenge sheet */

function NewChallengeSheet({
  open,
  onClose,
  t,
}: {
  open: boolean;
  onClose: () => void;
  t: (p: string, vars?: Record<string, string | number>) => string;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const monthAhead = (() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return d.toISOString().slice(0, 10);
  })();

  const [name, setName] = useState("");
  const [metric, setMetric] = useState<RankingMetric>("steps");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(monthAhead);

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{t("social_new_challenge")}</SheetTitle>
          <SheetDescription>Pick a metric, set the dates, invite friends later.</SheetDescription>
        </SheetHeader>

        <div className="space-y-3 px-4 pb-6">
          <label className="block">
            <span className="text-[11px] font-medium text-muted">Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. November Distance"
              className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
            />
          </label>

          <div>
            <span className="text-[11px] font-medium text-muted">Metric</span>
            <div className="mt-1">
              <Segmented<RankingMetric>
                value={metric}
                onChange={setMetric}
                options={[
                  { value: "steps",         label: RANKING_METRIC_LABEL.steps },
                  { value: "activities",    label: RANKING_METRIC_LABEL.activities },
                  { value: "training_load", label: RANKING_METRIC_LABEL.training_load },
                  { value: "sleep_score",   label: RANKING_METRIC_LABEL.sleep_score },
                ]}
                size="sm"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[11px] font-medium text-muted">{t("social_challenge_start")}</span>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
              />
            </label>
            <label className="block">
              <span className="text-[11px] font-medium text-muted">{t("social_challenge_end")}</span>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="num mt-1 w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="rounded-[var(--radius-control)] border border-hairline2 bg-surface2 p-2 text-[11px] leading-relaxed text-muted">
            This is a mock — challenges are saved client-side for now. The backend
            `POST /challenges` will receive the same fields.
          </div>
        </div>

        <SheetFooter className="flex-row gap-2 border-t border-hairline">
          <ApexButton variant="secondary" onClick={onClose} className="flex-1">
            Cancel
          </ApexButton>
          <ApexButton
            variant="primary"
            onClick={() => {
              // Mock only — no persistence backend.
              onClose();
            }}
            disabled={!name.trim()}
            className="flex-1"
          >
            Create
          </ApexButton>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

/* ------------------------------------------------------------ helpers */

function metricToPrivacyKey(metric: RankingMetric): PrivacyMetric {
  // steps / activities / sleep_score / training_load map 1:1.
  // distance has no RankingMetric equivalent — the privacy toggle stands alone.
  return metric as PrivacyMetric;
}
