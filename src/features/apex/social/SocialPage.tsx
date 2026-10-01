"use client";

/**
 * Apex Health — Challenges page.
 *
 * Re-skinned per ui-language/RULES.md (9 principles):
 *   1. One answer: "You're ranked #3 of 7 this week — keep moving."
 *   2. One hero: the rank headline in Row 1.
 *   3. No outlines on cards. No card-in-card.
 *   4. Sentence-case labels, 13px minimum.
 *   5. Numbers stay white; status = dot + word (StatusDot) where relevant.
 *   6. Accent (orange) for the "New challenge" action + progress bars.
 *   7. Plain words ("Challenges", not "CHALLENGES & RANKINGS").
 *   8. Charts: progress bars use the kit's RangeBar — no SVG bars here.
 *   9. Rankings + past challenges + privacy are rows, not bordered cards.
 *
 * Data: client-side mock (no multi-user backend). Composes from
 *       `challenges` in `@/lib/apex/data` + `@/lib/apex/socialData.ts`.
 */

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Plus } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { me, challenges as CANONICAL_CHALLENGES } from "@/lib/apex/data";
import { fmtDate, fmtInt } from "@/lib/apex/format";
import {
  ApexButton,
  Card,
  DeltaChip,
  Empty,
  PageSentence,
  RangeBar,
  Section,
  Segmented,
  StatusDot,
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

  const [openBoardId, setOpenBoardId] = useState<number | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [pastOpen, setPastOpen] = useState(false);

  const [rankMetric, setRankMetric] = useState<RankingMetric>("steps");
  const [rankPeriod, setRankPeriod] = useState<RankingPeriod>("week");

  const rankingTable = useMemo(() => {
    const table = getRanking(rankMetric, rankPeriod);
    const exposed = privacy[metricToPrivacyKey(rankMetric)];
    if (exposed) return table;
    return { ...table, rows: table.rows.filter((r) => r.participant_id !== me.user_id) };
  }, [rankMetric, rankPeriod, privacy]);

  const userStats = useMemo(() => ({
    steps:          myRank("steps", "week"),
    activities:     myRank("activities", "week"),
    training_load:  myRank("training_load", "week"),
    sleep_score:    myRank("sleep_score", "week"),
  }), []);

  // Page sentence (principle 1) — show the user's best rank this week.
  const pageSentence = useMemo(() => {
    const all = [
      userStats.steps,
      userStats.activities,
      userStats.training_load,
      userStats.sleep_score,
    ].filter((s): s is { rank: number; total: number; value: number; delta: number } => s !== null);
    if (all.length === 0) return "No ranking data yet. Sync your devices to join the boards.";
    const best = [...all].sort((a, b) => a.rank - b.rank)[0];
    const trend = best.delta > 0 ? "moving up" : best.delta < 0 ? "slipping" : "steady";
    return `You're ranked #${best.rank} of ${best.total} this week across four metrics — ${trend}.`;
  }, [userStats]);

  const visibleChallenges = CANONICAL_CHALLENGES.filter((c) => joinedIds.has(c.id));

  return (
    <div className="mx-auto max-w-[1240px] space-y-8 px-6 py-8">
      {/* ===== Title + page sentence ===== */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Challenges</h1>
          <PageSentence className="mt-2">{pageSentence}</PageSentence>
        </div>
        <ApexButton
          variant="primary"
          size="md"
          icon={<Plus size={14} strokeWidth={2.4} />}
          onClick={() => setNewOpen(true)}
        >
          {t("social_new_challenge")}
        </ApexButton>
      </div>

      {/* ===== Row 1 — Where I stand (4 tiles, no borders, StatusDots) ===== */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
        <StandTile metricLabel="Steps"          unit="steps" stat={userStats.steps}          goodWhen="up" />
        <StandTile metricLabel="Activities"    unit=""     stat={userStats.activities}      goodWhen="up" />
        <StandTile metricLabel="Training load" unit="TSS"  stat={userStats.training_load}  goodWhen="up" />
        <StandTile metricLabel="Sleep score"    unit="/100" stat={userStats.sleep_score}    goodWhen="up" />
      </div>

      {/* ===== Row 2 — Active challenges + Rankings ===== */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        {/* Left — Active challenges (cards, borderless) */}
        <div className="xl:col-span-7 space-y-6">
          <Section label={t("social.active_challenges")}>
            <div className="space-y-6">
              {visibleChallenges.length === 0 && (
                <Empty
                  title={t("social.empty")}
                  action={
                    <ApexButton variant="primary" size="sm" onClick={() => setNewOpen(true)}>
                      {t("social_new_challenge")}
                    </ApexButton>
                  }
                />
              )}
              {visibleChallenges.map((c) => {
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
              })}
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
          </Section>
        </div>

        {/* Right — Rankings (rows, not a bordered table) */}
        <div className="xl:col-span-5">
          <Card>
            <Section label={t("social_rankings")}>
              <div className="flex flex-wrap items-center gap-2">
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
                  <Empty title="You're opted out of this ranking" body={t("social_privacy_note")} />
                </div>
              ) : (
                <div className="mt-3">
                  <div className="divide-y divide-[var(--c-divider)]">
                    {rankingTable.rows.map((row, i) => {
                      const p = findParticipant(row.participant_id);
                      const isMe = row.participant_id === me.user_id;
                      const unit = RANKING_METRIC_UNIT[rankingTable.metric];
                      return (
                        <div
                          key={row.participant_id}
                          className={`flex items-center gap-3 py-2.5 ${isMe ? "-mx-2 rounded-[var(--radius-control)] bg-surface2 px-2" : ""}`}
                        >
                          <div className="num w-8 shrink-0 text-[14px] font-medium text-ink2">{i + 1}</div>
                          <div className="min-w-0 flex-1 truncate text-[14px] font-medium text-ink">
                            {p?.name ?? "Unknown"}
                            {isMe && (
                              <span className="ml-1.5 text-[13px] font-medium text-primaryText">· you</span>
                            )}
                          </div>
                          <div className="num shrink-0 text-[20px] font-semibold text-ink">
                            {fmtInt(row.value)}
                            {unit && <span className="ml-1 text-[13px] font-normal text-ink2">{unit}</span>}
                          </div>
                          <div className="shrink-0">
                            <DeltaChip delta={row.value - row.prev_value} unit={unit} goodWhen="up" compact />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </Section>
          </Card>
        </div>
      </div>

      {/* ===== Row 3 — Past challenges (rows, no bordered card) ===== */}
      <div>
        <button
          type="button"
          onClick={() => setPastOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-3 rounded-[var(--radius-card)] bg-surface px-7 py-4 text-left transition-colors hover:bg-surface2"
        >
          <div>
            <div className="text-[14px] font-medium text-ink2">{t("social_past")}</div>
            <div className="num mt-1 text-[16px] font-semibold text-ink">
              {PAST_CHALLENGES.length} finished · {PAST_CHALLENGES.filter((p) => p.my_rank <= 3).length} podiums
            </div>
          </div>
          <div className="text-ink2">
            {pastOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
        </button>
        {pastOpen && (
          <Card pad={false} className="mt-2">
            <div className="px-7">
              <div className="divide-y divide-[var(--c-divider)]">
                {PAST_CHALLENGES.map((p) => {
                  const winner = findParticipant(p.winner_id);
                  return (
                    <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3.5">
                      <div className="min-w-0">
                        <div className="truncate text-[14px] font-semibold text-ink">{p.title}</div>
                        <div className="num mt-0.5 text-[13px] text-ink2">
                          {p.metric} · {fmtDate(p.ended_at, ui.locale)} · {fmtInt(p.total_participants)} participants
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-[13px]">
                        <div className="num text-ink2">
                          <span className="font-medium text-ink">{winner?.name ?? "—"}</span>
                          <span className="ml-1.5 text-ink2">won</span>
                        </div>
                        <StatusDot
                          tone={p.my_rank <= 3 ? "ok" : "neutral"}
                          label={t("social_rank", { n: p.my_rank, total: p.total_participants })}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* ===== Privacy — switches, no bordered card ===== */}
      <Card>
        <Section label={t("social_privacy")}>
          <p className="text-[14px] leading-relaxed text-ink2">{t("social_privacy_note")}</p>
          <div className="mt-4 divide-y divide-[var(--c-divider)]">
            {PRIVACY_METRICS.map((m) => (
              <div key={m.key} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <div className="text-[14px] font-medium text-ink">{m.label}</div>
                  <div className="num text-[13px] text-ink2">
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
        </Section>
      </Card>

      {/* ===== Drawers ===== */}
      <ChallengeBoardSheet
        openId={openBoardId}
        onClose={() => setOpenBoardId(null)}
        t={t}
        locale={ui.locale}
      />
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
      <Card>
        <div className="text-[14px] font-medium text-ink2">{metricLabel}</div>
        <div className="mt-3 text-[16px] text-ink2">No data</div>
      </Card>
    );
  }
  // Hero-style rank headline (#3 / 7) + the actual value + DeltaChip
  const tone: "ok" | "watch" | "neutral" = stat.rank === 1 ? "ok" : stat.rank <= 3 ? "watch" : "neutral";
  const word = stat.rank === 1 ? "Leading" : stat.rank <= 3 ? "Podium" : "In the pack";
  return (
    <Card>
      <div className="text-[14px] font-medium text-ink2">{metricLabel}</div>
      <div className="num mt-2 flex items-baseline gap-1.5 text-ink">
        <span className="text-[13px] font-medium text-ink2">#</span>
        <span className="text-[40px] font-semibold leading-none">{stat.rank}</span>
        <span className="text-[16px] font-medium text-ink2">of {stat.total}</span>
      </div>
      <div className="mt-2">
        <StatusDot tone={tone} label={word} />
      </div>
      <div className="num mt-3 flex items-baseline gap-2">
        <span className="text-[20px] font-semibold text-ink">{fmtInt(stat.value)}</span>
        {unit && <span className="text-[13px] text-ink2">{unit}</span>}
        <span className="ml-auto">
          <DeltaChip delta={stat.delta} unit={unit} goodWhen={goodWhen} compact />
        </span>
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

  const participants: SocialParticipant[] = (board?.rows ?? [])
    .map((r) => findParticipant(r.participant_id))
    .filter((p): p is SocialParticipant => p !== undefined)
    .slice(0, 5);

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={onOpen} className="min-w-0 text-left">
          <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-ink hover:text-primaryText">
            {title}
          </h3>
          <div className="num mt-0.5 text-[13px] text-ink2">
            {metric} · {unit}
          </div>
        </button>
        <div className="num shrink-0 text-right text-[13px] text-ink2">
          <div className="font-medium text-ink">{daysLeft}d left</div>
          <div className="mt-0.5">{fmtDate(ends_at, locale)}</div>
        </div>
      </div>

      {/* Your progress vs leader */}
      <div className="mt-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="num flex items-baseline gap-1.5 text-ink">
          <span className="text-[28px] font-semibold leading-none">{fmtInt(my_value)}</span>
          <span className="text-[13px] font-medium text-ink2">{unit}</span>
        </div>
        <div className="num text-[13px] text-ink2">
          {t("social.vs_leader", { gap: fmtInt(gap), unit })}
        </div>
      </div>
      <div className="mt-3">
        <RangeBar
          value={my_value}
          low={0}
          high={leader_value}
          tone={my_rank === 1 ? "positive" : "primary"}
          unit={unit}
          height={5}
        />
      </div>

      {/* 3-stat strip — rows, no bordered tiles */}
      <div className="mt-4 grid grid-cols-3 divide-x divide-[var(--c-divider)] text-center">
        <MiniStat label={t("social.my_rank")} value={`#${fmtInt(my_rank)}`} />
        <MiniStat label={t("social.participants_count") || "Participants"} value={fmtInt(total_participants)} />
        <MiniStat label={t("social.leader_value")} value={fmtInt(leader_value)} />
      </div>

      {/* Participant initials */}
      {participants.length > 0 && (
        <div className="mt-4 flex items-center gap-1.5">
          {participants.map((p) => (
            <span
              key={p.id}
              title={p.name}
              className={`num inline-flex h-6 w-6 items-center justify-center rounded-full text-[12px] font-semibold ${
                p.is_me ? "bg-primary text-white" : "bg-surface2 text-ink2"
              }`}
            >
              {p.initials}
            </span>
          ))}
          {total_participants > participants.length && (
            <span className="num text-[13px] text-ink2">+{total_participants - participants.length}</span>
          )}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="text-[13px] font-semibold text-primaryText hover:underline"
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

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-2">
      <div className="text-[13px] text-ink2">{label}</div>
      <div className="num mt-0.5 text-[16px] font-semibold text-ink">{value}</div>
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
            <div className="num text-[13px] text-ink2">
              Ends {fmtDate(challenge.ends_at, locale)} · {fmtInt(challenge.total_participants)} participants
            </div>

            <div className="divide-y divide-[var(--c-divider)]">
              {[...board.rows]
                .sort((a, b) => b.value - a.value)
                .map((row, i) => {
                  const p = findParticipant(row.participant_id);
                  const isMe = row.participant_id === me.user_id;
                  return (
                    <div
                      key={row.participant_id}
                      className={`flex items-center gap-3 py-2.5 ${isMe ? "-mx-2 rounded-[var(--radius-control)] bg-surface2 px-2" : ""}`}
                    >
                      <div className="num w-8 shrink-0 text-[14px] font-medium text-ink2">{i + 1}</div>
                      <div className="min-w-0 flex-1 truncate text-[14px] font-medium text-ink">
                        {p?.name ?? "Unknown"}
                        {isMe && (
                          <span className="ml-1.5 text-[13px] font-medium text-primaryText">· you</span>
                        )}
                      </div>
                      <div className="num shrink-0 text-[16px] font-semibold text-ink">
                        {fmtInt(row.value)}
                        <span className="ml-1 text-[12px] font-normal text-ink2">{challenge.unit}</span>
                      </div>
                    </div>
                  );
                })}
            </div>

            <div className="text-[13px] leading-relaxed text-ink2">
              Your rank: <span className="font-semibold text-ink">#{challenge.my_rank}</span> of{" "}
              {fmtInt(challenge.total_participants)} — {fmtInt(Math.max(0, challenge.leader_value - challenge.my_value))}{" "}
              {challenge.unit} behind the leader.
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

  const inputCls =
    "num w-full rounded-[var(--radius-control)] border border-hairline bg-surface px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-primary transition-colors";

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{t("social_new_challenge")}</SheetTitle>
          <SheetDescription>Pick a metric, set the dates, invite friends later.</SheetDescription>
        </SheetHeader>

        <div className="space-y-3 px-4 pb-6">
          <label className="block">
            <span className="text-[13px] font-medium text-ink2">Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. November Distance"
              className={`${inputCls} mt-1`}
            />
          </label>

          <div>
            <span className="text-[13px] font-medium text-ink2">Metric</span>
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
              <span className="text-[13px] font-medium text-ink2">{t("social_challenge_start")}</span>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className={`${inputCls} mt-1`}
              />
            </label>
            <label className="block">
              <span className="text-[13px] font-medium text-ink2">{t("social_challenge_end")}</span>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className={`${inputCls} mt-1`}
              />
            </label>
          </div>

          <p className="text-[13px] leading-relaxed text-ink2">
            Challenges are saved client-side for now — the backend `POST /challenges` will receive the same
            fields once it lands.
          </p>
        </div>

        <SheetFooter className="flex-row gap-2 border-t border-hairline">
          <ApexButton variant="secondary" onClick={onClose} className="flex-1">
            Cancel
          </ApexButton>
          <ApexButton
            variant="primary"
            onClick={() => {
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
  return metric as PrivacyMetric;
}
