import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Card, CardHeader, ErrorNote, Loading } from "../../components/kit";

interface AlphaUsage {
  window_days: number;
  weekly_active_alpha_users: number;
  ai_users: number;
  proposals: number;
  acceptance_rate: number | null;
  edit_rate: number | null;
  rejection_rate: number | null;
  decision_influence_rate: number | null;
  decision_feedback_responses: number;
  provider_failure_counts: Record<string, number>;
  events: Record<string, number>;
  formula: string;
}

function rate(value: number | null) {
  return value === null
    ? "—"
    : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value * 100)}%`;
}

function label(value: string) {
  return value.replaceAll("_", " ");
}

export default function AlphaUsagePanel() {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["admin", "alpha", 28],
    queryFn: () => api.get<AlphaUsage>("/api/admin/alpha?days=28"),
    refetchInterval: 60_000,
  });
  const data = query.data;
  const metrics: [string, string | number][] = data
    ? [
        ["weeklyActiveUsers", data.weekly_active_alpha_users],
        ["aiUsers", data.ai_users],
        ["proposals", data.proposals],
        ["acceptanceRate", rate(data.acceptance_rate)],
        ["editRate", rate(data.edit_rate)],
        ["rejectionRate", rate(data.rejection_rate)],
        ["decisionInfluenceRate", rate(data.decision_influence_rate)],
        ["decisionFeedback", data.decision_feedback_responses],
      ]
    : [];
  const failures = Object.entries(data?.provider_failure_counts ?? {}).sort(
    ([providerA, countA], [providerB, countB]) =>
      countB - countA || providerA.localeCompare(providerB),
  );
  const events = Object.entries(data?.events ?? {}).sort(
    ([eventA, countA], [eventB, countB]) => countB - countA || eventA.localeCompare(eventB),
  );

  return (
    <Card>
      <CardHeader
        title={<h2>{t("admin.alphaUsage.title")}</h2>}
        right={
          data && (
            <span className="text-xs text-muted">
              {t("admin.alphaUsage.window", { days: data.window_days })}
            </span>
          )
        }
      />
      {query.isLoading ? (
        <Loading />
      ) : query.isError ? (
        <ErrorNote
          message={
            query.error instanceof Error
              ? query.error.message
              : t("admin.alphaUsage.loadError")
          }
        />
      ) : data ? (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {metrics.map(([key, value]) => (
              <div key={key} className="border border-hairline p-3">
                <div className="text-xs uppercase text-muted">
                  {t(`admin.alphaUsage.metrics.${key}`)}
                </div>
                <div className="num mt-1 text-lg font-medium">{value}</div>
              </div>
            ))}
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <section aria-labelledby="alpha-provider-failures">
              <h3 id="alpha-provider-failures" className="mb-2 text-sm font-medium">
                {t("admin.alphaUsage.providerFailures")}
              </h3>
              {failures.length ? (
                <ul className="divide-y divide-hairline border-y border-hairline text-sm">
                  {failures.map(([provider, count]) => (
                    <li key={provider} className="flex justify-between py-2">
                      <span>{t(`providers.${provider}`, { defaultValue: label(provider) })}</span>
                      <span className="num">{count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">{t("admin.alphaUsage.noProviderFailures")}</p>
              )}
            </section>

            <section aria-labelledby="alpha-events">
              <h3 id="alpha-events" className="mb-2 text-sm font-medium">
                {t("admin.alphaUsage.events")}
              </h3>
              {events.length ? (
                <ul className="divide-y divide-hairline border-y border-hairline text-sm">
                  {events.map(([event, count]) => (
                    <li key={event} className="flex justify-between gap-4 py-2">
                      <span>{t(`admin.alphaUsage.eventNames.${event}`, { defaultValue: label(event) })}</span>
                      <span className="num">{count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">{t("admin.alphaUsage.noEvents")}</p>
              )}
            </section>
          </div>

          <div className="border-t border-hairline pt-4 text-xs text-muted">
            <p className="font-medium text-ink">
              {t("admin.alphaUsage.influenceCaveat")}
            </p>
            <p className="mt-1">{data.formula}</p>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
