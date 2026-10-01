/**
 * Apex Health — Social mock data (plan §9).
 *
 * The Challenges page is client-only (no multi-user backend in the sandbox),
 * so this file owns the mock social graph used by `SocialPage.tsx`:
 *   - PARTICIPANTS:   6 mock friends + the current user (`me`).
 *   - CHALLENGE_BOARDS:  per-challenge leaderboards (the user + 4-5 friends).
 *   - PAST_CHALLENGES:    finished challenges with winner + user's finishing place.
 *   - RANKINGS:           4 headline metrics × 7 participants × 3 periods.
 *   - PRIVACY_DEFAULTS:   per-metric sharing toggles (steps / activities /
 *                         distance on by default; sleep score / training load
 *                         off until opt-in, per the plan).
 *
 * Lives outside `src/lib/apex/data.ts` (off-limits) so the page can compose
 * from a typed, deterministic mock without modifying the canonical data file.
 */

import { me } from "./data";

/* ------------------------------------------------------------ participants */

export interface SocialParticipant {
  id: number;
  name: string;
  initials: string;
  /** "me" for the current user — used for row highlight + privacy checks. */
  is_me?: boolean;
}

export const PARTICIPANTS: SocialParticipant[] = [
  { id: me.user_id,  name: me.name,           initials: initialsOf(me.name), is_me: true },
  { id: 101,         name: "Luca Romano",      initials: "LR" },
  { id: 102,         name: "Sofia Conti",      initials: "SC" },
  { id: 103,         name: "Marco Bianchi",   initials: "MB" },
  { id: 104,         name: "Giulia Ferraro",  initials: "GF" },
  { id: 105,         name: "Davide Esposito", initials: "DE" },
  { id: 106,         name: "Elena Russo",     initials: "ER" },
];

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name.slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function findParticipant(id: number): SocialParticipant | undefined {
  return PARTICIPANTS.find((p) => p.id === id);
}

/* ------------------------------------------------------------ challenges leaderboard */

export interface ChallengeBoardRow {
  participant_id: number;
  value: number;
  /** Cumulative progress over the days of the challenge (chronological). */
  cumulative: number[];
}

export interface ChallengeBoard {
  challenge_id: number;
  rows: ChallengeBoardRow[];
}

/**
 * Build a leaderboard per challenge. Mirrors the existing `challenges` array
 * from `src/lib/apex/data.ts` (ids 1, 2, 3). For each challenge we put 5-6
 * participants including the user. The user's value matches the `my_value`
 * from the canonical array so the card and the leaderboard agree.
 */
export const CHALLENGE_BOARDS: ChallengeBoard[] = [
  {
    challenge_id: 1, // "October Distance — Cycling" — km
    rows: [
      { participant_id: 102, value: 781, cumulative: [80, 165, 250, 340, 430, 540, 620, 700, 781] },
      { participant_id: 101, value: 742, cumulative: [70, 145, 220, 300, 380, 470, 560, 660, 742] },
      { participant_id: 105, value: 690, cumulative: [60, 130, 200, 270, 340, 420, 510, 600, 690] },
      { participant_id: me.user_id, value: 624, cumulative: [50, 110, 175, 245, 320, 400, 475, 555, 624] },
      { participant_id: 103, value: 588, cumulative: [55, 120, 185, 250, 320, 390, 460, 525, 588] },
      { participant_id: 104, value: 502, cumulative: [40, 90, 145, 200, 260, 320, 380, 440, 502] },
    ],
  },
  {
    challenge_id: 2, // "Vertical Climb Challenge" — m
    rows: [
      { participant_id: 104, value: 6310, cumulative: [700, 1450, 2200, 2950, 3700, 4500, 5200, 5800, 6310] },
      { participant_id: 106, value: 5920, cumulative: [650, 1300, 2000, 2700, 3400, 4100, 4800, 5400, 5920] },
      { participant_id: 103, value: 5410, cumulative: [600, 1200, 1800, 2400, 3050, 3700, 4350, 4900, 5410] },
      { participant_id: 101, value: 5080, cumulative: [550, 1100, 1650, 2200, 2750, 3350, 3950, 4500, 5080] },
      { participant_id: me.user_id, value: 4820, cumulative: [500, 1000, 1500, 2050, 2600, 3150, 3700, 4250, 4820] },
      { participant_id: 102, value: 4190, cumulative: [400, 850, 1300, 1750, 2200, 2650, 3100, 3600, 4190] },
    ],
  },
  {
    challenge_id: 3, // "Recovery Score Streak" — days above 75
    rows: [
      { participant_id: 106, value: 22, cumulative: [2, 4, 6, 8, 10, 12, 14, 18, 22] },
      { participant_id: 104, value: 20, cumulative: [2, 4, 6, 8, 10, 12, 14, 17, 20] },
      { participant_id: 105, value: 17, cumulative: [1, 3, 5, 7, 9, 11, 13, 15, 17] },
      { participant_id: 101, value: 16, cumulative: [1, 3, 5, 7, 9, 11, 13, 14, 16] },
      { participant_id: 102, value: 15, cumulative: [1, 3, 5, 7, 9, 11, 13, 14, 15] },
      { participant_id: me.user_id, value: 14, cumulative: [1, 2, 4, 6, 8, 10, 12, 13, 14] },
      { participant_id: 103, value: 12, cumulative: [1, 2, 3, 5, 7, 9, 10, 11, 12] },
    ],
  },
];

/* ------------------------------------------------------------ past challenges */

export interface PastChallenge {
  id: number;
  title: string;
  metric: string;
  unit: string;
  ended_at: string;
  winner_id: number;
  my_value: number;
  my_rank: number;
  total_participants: number;
}

export const PAST_CHALLENGES: PastChallenge[] = [
  {
    id: 901,
    title: "September Step Count",
    metric: "Daily steps",
    unit: "steps",
    ended_at: daysAgo(36),
    winner_id: 105,
    my_value: 268_400,
    my_rank: 3,
    total_participants: 48,
  },
  {
    id: 902,
    title: "Late-Summer 100 km",
    metric: "Total distance",
    unit: "km",
    ended_at: daysAgo(70),
    winner_id: 101,
    my_value: 92,
    my_rank: 5,
    total_participants: 22,
  },
  {
    id: 903,
    title: "Sleep Score Sprint",
    metric: "Sleep score",
    unit: "/100",
    ended_at: daysAgo(110),
    winner_id: 106,
    my_value: 78,
    my_rank: 8,
    total_participants: 35,
  },
];

/* ------------------------------------------------------------ rankings */

export type RankingMetric = "steps" | "activities" | "training_load" | "sleep_score";
export type RankingPeriod = "week" | "month" | "all";

export interface RankingRow {
  participant_id: number;
  value: number;
  /** Previous period value — for the DeltaChip. */
  prev_value: number;
}

export interface RankingTable {
  metric: RankingMetric;
  period: RankingPeriod;
  rows: RankingRow[];
}

export const RANKING_METRIC_LABEL: Record<RankingMetric, string> = {
  steps: "Steps",
  activities: "Activities",
  training_load: "Training load",
  sleep_score: "Sleep score",
};

export const RANKING_METRIC_UNIT: Record<RankingMetric, string> = {
  steps: "steps",
  activities: "",
  training_load: "TSS",
  sleep_score: "/100",
};

/**
 * Deterministic per-metric × per-period mock values for 7 participants.
 * The user's row is highlighted; `prev_value` feeds the DeltaChip.
 */
export const RANKINGS: RankingTable[] = [
  // ---- steps ----
  build("steps", "week", [
    { id: 105, value:  84_320, prev:  79_540 },
    { id: 101, value:  78_410, prev:  82_180 },
    { id: me.user_id, value:  71_250, prev:  68_900 },
    { id: 102, value:  69_580, prev:  71_220 },
    { id: 103, value:  62_140, prev:  64_300 },
    { id: 106, value:  58_770, prev:  55_900 },
    { id: 104, value:  52_010, prev:  49_880 },
  ]),
  build("steps", "month", [
    { id: 105, value: 312_800, prev: 298_400 },
    { id: 101, value: 287_100, prev: 305_200 },
    { id: 102, value: 271_400, prev: 268_900 },
    { id: me.user_id, value: 264_800, prev: 251_300 },
    { id: 103, value: 248_900, prev: 252_700 },
    { id: 106, value: 232_400, prev: 220_100 },
    { id: 104, value: 209_600, prev: 198_400 },
  ]),
  build("steps", "all", [
    { id: 105, value: 1_842_000, prev: 1_780_000 },
    { id: 101, value: 1_712_000, prev: 1_690_000 },
    { id: me.user_id, value: 1_648_000, prev: 1_590_000 },
    { id: 102, value: 1_592_000, prev: 1_548_000 },
    { id: 103, value: 1_481_000, prev: 1_450_000 },
    { id: 106, value: 1_402_000, prev: 1_372_000 },
    { id: 104, value: 1_289_000, prev: 1_248_000 },
  ]),
  // ---- activities ----
  build("activities", "week", [
    { id: 101, value: 14, prev: 11 },
    { id: me.user_id, value: 12, prev: 10 },
    { id: 103, value: 11, prev: 13 },
    { id: 105, value: 10, prev:  9 },
    { id: 104, value:  9, prev:  8 },
    { id: 102, value:  8, prev: 10 },
    { id: 106, value:  7, prev:  6 },
  ]),
  build("activities", "month", [
    { id: 101, value: 52, prev: 48 },
    { id: me.user_id, value: 48, prev: 42 },
    { id: 103, value: 45, prev: 50 },
    { id: 105, value: 42, prev: 39 },
    { id: 102, value: 39, prev: 41 },
    { id: 104, value: 37, prev: 33 },
    { id: 106, value: 31, prev: 29 },
  ]),
  build("activities", "all", [
    { id: me.user_id, value: 612, prev: 590 },
    { id: 101, value: 598, prev: 580 },
    { id: 103, value: 564, prev: 555 },
    { id: 105, value: 521, prev: 502 },
    { id: 102, value: 498, prev: 484 },
    { id: 104, value: 462, prev: 441 },
    { id: 106, value: 421, prev: 405 },
  ]),
  // ---- training load ----
  build("training_load", "week", [
    { id: 101, value: 487, prev: 412 },
    { id: 103, value: 421, prev: 398 },
    { id: me.user_id, value: 392, prev: 358 },
    { id: 104, value: 358, prev: 332 },
    { id: 105, value: 318, prev: 295 },
    { id: 102, value: 274, prev: 268 },
    { id: 106, value: 198, prev: 215 },
  ]),
  build("training_load", "month", [
    { id: 101, value: 1894, prev: 1740 },
    { id: 103, value: 1721, prev: 1685 },
    { id: me.user_id, value: 1620, prev: 1480 },
    { id: 104, value: 1498, prev: 1421 },
    { id: 105, value: 1342, prev: 1298 },
    { id: 102, value: 1198, prev: 1175 },
    { id: 106, value:  881, prev:  910 },
  ]),
  build("training_load", "all", [
    { id: me.user_id, value: 18_420, prev: 17_980 },
    { id: 101, value: 17_810, prev: 17_410 },
    { id: 103, value: 16_540, prev: 16_120 },
    { id: 104, value: 14_220, prev: 13_910 },
    { id: 105, value: 12_980, prev: 12_710 },
    { id: 102, value: 11_440, prev: 11_180 },
    { id: 106, value:  8_120, prev:  7_980 },
  ]),
  // ---- sleep score ----
  build("sleep_score", "week", [
    { id: 106, value: 88, prev: 85 },
    { id: 104, value: 84, prev: 81 },
    { id: me.user_id, value: 81, prev: 78 },
    { id: 102, value: 79, prev: 82 },
    { id: 101, value: 77, prev: 76 },
    { id: 105, value: 75, prev: 78 },
    { id: 103, value: 72, prev: 70 },
  ]),
  build("sleep_score", "month", [
    { id: 106, value: 86, prev: 84 },
    { id: 104, value: 83, prev: 80 },
    { id: 102, value: 80, prev: 82 },
    { id: me.user_id, value: 79, prev: 75 },
    { id: 101, value: 78, prev: 76 },
    { id: 105, value: 76, prev: 79 },
    { id: 103, value: 73, prev: 71 },
  ]),
  build("sleep_score", "all", [
    { id: 106, value: 84, prev: 83 },
    { id: 104, value: 82, prev: 80 },
    { id: me.user_id, value: 80, prev: 78 },
    { id: 102, value: 79, prev: 80 },
    { id: 101, value: 78, prev: 77 },
    { id: 105, value: 76, prev: 78 },
    { id: 103, value: 73, prev: 72 },
  ]),
];

function build(
  metric: RankingMetric,
  period: RankingPeriod,
  rows: { id: number; value: number; prev: number }[],
): RankingTable {
  return {
    metric,
    period,
    rows: rows
      .map((r) => ({ participant_id: r.id, value: r.value, prev_value: r.prev }))
      .sort((a, b) => b.value - a.value),
  };
}

export function getRanking(metric: RankingMetric, period: RankingPeriod): RankingTable {
  return (
    RANKINGS.find((r) => r.metric === metric && r.period === period) ??
    RANKINGS.find((r) => r.metric === metric && r.period === "week")!
  );
}

/** The user's rank for a given metric+period, plus value + delta. */
export function myRank(
  metric: RankingMetric,
  period: RankingPeriod,
): { rank: number; total: number; value: number; delta: number } | null {
  const table = getRanking(metric, period);
  const idx = table.rows.findIndex((r) => r.participant_id === me.user_id);
  if (idx < 0) return null;
  const row = table.rows[idx];
  return {
    rank: idx + 1,
    total: table.rows.length,
    value: row.value,
    delta: row.value - row.prev_value,
  };
}

/* ------------------------------------------------------------ privacy */

export type PrivacyMetric = "steps" | "activities" | "distance" | "sleep_score" | "training_load";

export const PRIVACY_METRICS: { key: PrivacyMetric; label: string }[] = [
  { key: "steps",          label: "Steps" },
  { key: "activities",     label: "Activities" },
  { key: "distance",       label: "Distance" },
  { key: "sleep_score",    label: "Sleep score" },
  { key: "training_load",  label: "Training load" },
];

/**
 * Per-metric sharing defaults. Plan §9: steps, activities and distance on
 * by default; sleep score and training load OFF until the user opts in.
 *
 * Persisted client-side (Zustand) — the user's toggles survive reloads but
 * the data file ships with the documented defaults.
 */
export const PRIVACY_DEFAULTS: Record<PrivacyMetric, boolean> = {
  steps: true,
  activities: true,
  distance: true,
  sleep_score: false,
  training_load: false,
};

/* ------------------------------------------------------------ date helper */

function daysAgo(n: number): string {
  const d = new Date();
  d.setHours(23, 59, 0, 0);
  d.setDate(d.getDate() - n);
  return d.toISOString();
}
