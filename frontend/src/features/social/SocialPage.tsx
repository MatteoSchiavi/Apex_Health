/**
 * Social — challenges + global rankings (owner feature batch).
 * Metrics mirror the backend METRICS set; leaderboards show rank/athlete/
 * value with the session user highlighted.
 */

import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Tabs } from "../../components/Tabs";
import { useUi } from "../../app/stores/ui";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Input,
  Loading,
  PageHeader,
  Select,
  fmtNum,
} from "../../components/kit";

const METRICS: {
  key: string;
  labelKey: string;
  unit: string;
  betterDown?: boolean;
}[] = [
  {
    key: "5k_time_s",
    labelKey: "social.metric_5k",
    unit: "min",
    betterDown: true,
  },
  { key: "activities_count", labelKey: "social.metric_activities", unit: "" },
  { key: "steps", labelKey: "social.metric_steps", unit: "" },
  { key: "distance_m", labelKey: "social.metric_distance", unit: "km" },
  {
    key: "intensity_minutes",
    labelKey: "social.metric_intensity",
    unit: "min",
  },
  { key: "sleep_score_avg", labelKey: "social.metric_sleep", unit: "/100" },
  { key: "training_load_sum", labelKey: "social.metric_load", unit: "" },
];

function fmtValue(metric: string, v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (metric === "5k_time_s") {
    const m = Math.floor(v / 60);
    const s = Math.round(v % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  }
  if (metric === "distance_m") return fmtNum(v / 1000, 1);
  return fmtNum(v, 0);
}

interface RankingRow {
  user_id: number;
  display_name: string;
  value: number | null;
}

function Rankings() {
  const { t } = useTranslation();
  const me = useUi((s) => s.me);
  const [metric, setMetric] = useState("steps");
  const [period, setPeriod] = useState("weekly");
  const meta = METRICS.find((m) => m.key === metric)!;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["rankings", metric, period],
    queryFn: () => api.get<RankingRow[]>(`/rankings?metric=${metric}&period=${period}`),
  });

  return (
    <Card>
      <CardHeader
        eyebrow={t("social.rankings")}
        right={
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="h-7 rounded-control border border-hairline bg-surface2 px-2 text-[12px] text-ink"
          >
            {METRICS.map((m) => (
              <option key={m.key} value={m.key}>
                {t(m.labelKey)}
              </option>
            ))}
          </select>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted">
          {t("social.period")}
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="ml-2 h-10 rounded-control border border-hairline bg-surface2 px-3 text-sm text-ink"
          >
            {["weekly", "monthly", "all_time"].map((option) => (
              <option key={option} value={option}>{t(`social.${option}`)}</option>
            ))}
          </select>
        </label>
        <span className="text-xs text-muted">{t("social.period_utc")}</span>
      </div>
      {isLoading ? (
        <Loading />
      ) : isError ? (
        <ErrorNote />
      ) : !data || data.length === 0 ? (
        <Empty>{t("social.no_data")}</Empty>
      ) : (
        <table className="data-table">
          <thead>
            <tr className="border-b border-hairline text-left">
              <th className="eyebrow py-2 pr-3">{t("social.rank")}</th>
              <th className="eyebrow py-2 pr-3">{t("social.athlete")}</th>
              <th className="eyebrow py-2 text-right">{t("social.value")}</th>
            </tr>
          </thead>
          <tbody className="num">
            {data.map((r, i) => (
              <tr
                key={r.user_id}
                className={`border-b border-hairline last:border-0 ${
                  r.user_id === me?.user_id ? "bg-primarySoft/50" : ""
                }`}
              >
                <td className="py-2 pr-3 font-bold text-muted">{i + 1}</td>
                <td className="py-2 pr-3 font-medium text-ink">
                  {r.display_name}
                  {r.user_id === me?.user_id && (
                    <span className="ml-2">
                      <Badge tone="primary">{t("social.you")}</Badge>
                    </span>
                  )}
                </td>
                <td className="py-2 text-right font-semibold text-ink">
                  {fmtValue(metric, r.value)}
                  {meta.unit && r.value !== null && (
                    <span className="ml-1 text-[12px] font-normal text-muted">
                      {meta.unit}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

interface ChallengeRow {
  id: number;
  name: string;
  metric: string;
  period: string;
  starts_at: string | null;
  ends_at: string | null;
  member_count: number;
  created_by_name: string;
}

function Challenges() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [metric, setMetric] = useState("steps");

  const list = useQuery({
    queryKey: ["challenges"],
    queryFn: () => api.get<ChallengeRow[]>("/challenges"),
  });
  const create = useMutation({
    mutationFn: () => api.post("/challenges", { name, metric }),
    onSuccess: () => {
      setCreating(false);
      setName("");
      qc.invalidateQueries({ queryKey: ["challenges"] });
    },
  });
  const join = useMutation({
    mutationFn: (id: number) => api.post(`/challenges/${id}/join`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["challenges"] }),
  });

  return (
    <Card>
      <CardHeader
        eyebrow={t("social.challenges")}
        right={
          <Button
            variant="ghost"
            className="!h-9 !px-2.5 text-[12px]"
            onClick={() => setCreating((v) => !v)}
          >
            {creating ? t("common.cancel") : `+ ${t("social.create")}`}
          </Button>
        }
      />
      {creating && (
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            create.mutate();
          }}
          className="mb-3 flex flex-col gap-3 bg-surface2 p-3"
        >
          <Input
            label={t("social.name")}
            value={name}
            onChange={setName}
            required
          />
          <Select
            label={t("social.metric")}
            value={metric}
            onChange={setMetric}
            options={METRICS.map((m) => ({
              value: m.key,
              label: t(m.labelKey),
            }))}
          />
          <Button
            type="submit"
            disabled={create.isPending}
            className="self-start"
          >
            {t("social.create")}
          </Button>
        </form>
      )}
      {(create.isError || join.isError) && <ErrorNote />}
      {list.isLoading ? (
        <Loading />
      ) : list.isError ? (
        <ErrorNote />
      ) : !list.data || list.data.length === 0 ? (
        <Empty>{t("social.no_data")}</Empty>
      ) : (
        <div className="flex flex-col gap-2">
          {list.data.map((ch) => {
            const meta = METRICS.find((m) => m.key === ch.metric);
            return (
              <div
                key={ch.id}
                className="flex flex-wrap items-center justify-between gap-4 border-b border-hairline py-5"
              >
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-ink">
                    {ch.name}
                  </div>
                  <div className="num text-[12px] text-muted">
                    {meta ? t(meta.labelKey) : ch.metric} ·{" "}
                    {ch.starts_at ? ch.starts_at.slice(0, 10) : "—"} →{" "}
                    {ch.ends_at ? ch.ends_at.slice(0, 10) : "—"} ·{" "}
                    {ch.member_count} {t("social.members").toLowerCase()}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  className="!h-9 !px-2.5 text-[12px]"
                  onClick={() => join.mutate(ch.id)}
                  disabled={join.isPending}
                >
                  {t("social.join")}
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

export default function SocialPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState("challenges");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("social.title")} subtitle={t("social.subtitle")} />
      <Tabs
        value={tab}
        onChange={setTab}
        label={t("social.title")}
        options={[
          { value: "challenges", label: t("social.challenges") },
          { value: "rankings", label: t("social.rankings") },
        ]}
      />
      {tab === "challenges" ? <Challenges /> : <Rankings />}
    </div>
  );
}
