"use client";

/**
 * Apex Health — Social page (Challenges & Rankings).
 *
 * Route purpose: "What challenges and comparisons exist?"
 *
 * Restraint law — challenges exist as a feature, not as the design identity.
 * No streak graphics, no badges, no leaderboard gradients. The leader color
 * is muted (bg-surface3 + text-ink), never bright gold/yellow. Progress is
 * shown as RangeBar — never pie charts or gauges.
 *
 * Structure:
 *   1. PageHeader (title + subtitle — the subtitle sets the restrained tone).
 *   2. Rank summary strip (4 StatPods: best rank, active challenges, total
 *      participants, avg rank) — derived from the challenges data.
 *   3. Challenge cards (full-width list). Each shows title + Ends date, the
 *      metric being tracked, a RangeBar of my_value vs leader_value, a 3-stat
 *      strip (my rank / total participants / leader's value), and a "top
 *      three" mini-list with synthesized plausible values.
 *   4. Friend accounts note (subdued, owner-only).
 *
 * Empty state: t("social.empty").
 */

import { useT } from "@/lib/apex/i18nContext";
import { useApexUi } from "@/lib/apex";
import { challenges } from "@/lib/apex/data";
import { fmtDate, fmtInt } from "@/lib/apex/format";
import {
  Card,
  Empty,
  Eyebrow,
  Hairline,
  PageHeader,
  RangeBar,
  StatPod,
} from "@/components/apex/kit";

/* ------------------------------------------------------------ main page */

export function SocialPage() {
  const t = useT();
  const ui = useApexUi();

  const bestRank = Math.min(...challenges.map((c) => c.my_rank));
  const activeCount = challenges.length;
  const totalParticipants = challenges.reduce((s, c) => s + c.total_participants, 0);
  const avgRank = Math.round(
    challenges.reduce((s, c) => s + c.my_rank, 0) / Math.max(1, challenges.length)
  );

  return (
    <div className="mx-auto max-w-[1240px]">
      <PageHeader title={t("social.title")} subtitle={t("social.subtitle")} />

      {/* 2. Rank summary — 4 StatPods */}
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatPod
          label={t("social.best_rank")}
          value={`${t("social.rank_symbol")}${fmtInt(bestRank)}`}
          sub={t("social.my_rank")}
        />
        <StatPod
          label={t("social.active_challenges")}
          value={fmtInt(activeCount)}
          sub={t("social.progress")}
        />
        <StatPod
          label={t("social.total_participants")}
          value={fmtInt(totalParticipants)}
        />
        <StatPod
          label={t("social.avg_rank")}
          value={`${t("social.rank_symbol")}${fmtInt(avgRank)}`}
          sub={t("social.my_rank")}
        />
      </div>

      {/* 3. Challenge cards */}
      <div className="mt-4 space-y-4">
        {challenges.length === 0 ? (
          <Empty title={t("social.empty")} />
        ) : (
          challenges.map((c) => <ChallengeCard key={c.id} challenge={c} />)
        )}
      </div>

      {/* 4. Friend accounts note (subdued) */}
      <Card className="mt-4 bg-surface2">
        <Eyebrow>{t("social.no_friends_eyebrow")}</Eyebrow>
        <p className="mt-1.5 text-[13px] leading-[1.55] text-muted">
          {t("social.no_friends")}
        </p>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------ challenge card */

function ChallengeCard({
  challenge,
}: {
  challenge: (typeof challenges)[number];
}) {
  const t = useT();
  const ui = useApexUi();

  const { title, metric, unit, my_value, leader_value, my_rank, total_participants, ends_at } =
    challenge;

  const gap = Math.max(0, leader_value - my_value);

  // Synthesize plausible rank 2 / rank 3 values around the leader.
  const r2 = Math.round(leader_value * 0.96);
  const r3 = Math.round(leader_value * 0.91);
  const topThree = [
    { rank: 1, value: leader_value },
    { rank: 2, value: r2 },
    { rank: 3, value: r3 },
  ];

  return (
    <Card>
      {/* Title + Ends date */}
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</h2>
        <span className="num mono shrink-0 text-[11px] font-medium uppercase tracking-[0.06em] text-faint">
          {t("social.ending", { date: fmtDate(ends_at, ui.locale) })}
        </span>
      </div>

      {/* Metric being tracked */}
      <div className="mt-3 flex items-baseline gap-2">
        <Eyebrow>{metric}</Eyebrow>
        <span className="num text-[10px] font-medium uppercase tracking-[0.06em] text-faint">
          {unit}
        </span>
      </div>

      {/* Your progress — big number + gap to leader + RangeBar */}
      <div className="mt-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="num mono text-[28px] font-bold leading-8 tracking-[-0.02em] text-ink">
          {fmtInt(my_value)}
          <span className="ml-1.5 text-[12px] font-medium text-muted">{unit}</span>
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
          tone="primary"
          unit={unit}
          height={5}
        />
      </div>

      <Hairline className="my-4" />

      {/* 3-stat strip: My rank / Total participants / Leader's value */}
      <div className="grid grid-cols-3 gap-2">
        <MiniStat label={t("social.my_rank")}>
          <span className="mono">{t("social.rank_symbol")}{fmtInt(my_rank)}</span>
        </MiniStat>
        <MiniStat label={t("social.participants_count")}>
          <span className="mono">{fmtInt(total_participants)}</span>
        </MiniStat>
        <MiniStat label={t("social.leader_value")}>
          <span className="mono">{fmtInt(leader_value)}</span>
          <span className="ml-1 text-[10px] font-medium text-faint">{unit}</span>
        </MiniStat>
      </div>

      {/* Top three mini-list */}
      <div className="mt-4">
        <Eyebrow>{t("social.top_three")}</Eyebrow>
        <div className="mt-2 overflow-hidden rounded-[var(--radius-control)] border border-hairline">
          {topThree.map((row, i) => (
            <div
              key={row.rank}
              className={`flex items-center justify-between gap-3 px-3 py-2 text-[12px] ${
                row.rank === 1
                  ? "bg-surface3 text-ink"
                  : "bg-surface text-muted"
              } ${i > 0 ? "border-t border-hairline" : ""}`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`mono inline-flex h-5 w-5 items-center justify-center rounded-[var(--radius-control)] text-[10px] font-bold ${
                    row.rank === 1
                      ? "bg-surface text-ink"
                      : "bg-surface3 text-muted"
                  }`}
                >
                  {row.rank}
                </span>
                <span className="eyebrow !text-[10px]">
                  {row.rank === 1 ? t("social.leader") : `#${row.rank}`}
                </span>
              </div>
              <div className="num mono font-semibold text-ink">
                {fmtInt(row.value)}
                <span className="ml-1 text-[10px] font-medium text-faint">{unit}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------ mini stat */

function MiniStat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[var(--radius-control)] border border-hairline bg-surface2 px-3 py-2">
      <div className="eyebrow truncate">{label}</div>
      <div className="num mt-1 text-[16px] font-semibold leading-6 text-ink">
        {children}
      </div>
    </div>
  );
}
