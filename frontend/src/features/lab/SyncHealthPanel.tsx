import { useTranslation } from "react-i18next";
import { Badge, Card, CardHeader } from "../../components/kit";
import { human, QueryState, useLab } from "./shared";

interface SyncFeed {
  provider: string;
  feed: string;
  state: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  latest_measurement_at: string | null;
  stale_after_hours: number;
  error_class: string | null;
  retry_state: "unknown" | "scheduled" | "reconnect_required" | "idle";
  has_checkpoint: boolean;
  failed_attempts: number;
  credentials_state:
    | "unknown"
    | "configured"
    | "reconnect_required"
    | "not_required";
}

interface SyncHealth {
  feeds: SyncFeed[];
}

function timestamp(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function SyncHealthPanel() {
  const { t } = useTranslation();
  const query = useLab<SyncHealth>("/lab/sync-health");

  return (
    <Card>
      <CardHeader
        title={t("lab.syncHealth.title")}
        right={
          <span className="text-[12px] text-muted">
            {t("lab.syncHealth.staleWindow", { hours: 48 })}
          </span>
        }
      />
      <p className="mb-4 text-[12px] text-muted">
        {t("lab.syncHealth.subtitle")}
      </p>
      <QueryState loading={query.isLoading} error={query.isError} />
      {!query.isLoading && !query.isError && query.data?.feeds.length === 0 && (
        <p className="text-[13px] text-muted">{t("lab.syncHealth.empty")}</p>
      )}
      {!!query.data?.feeds.length && (
        <div className="grid gap-3">
          {query.data.feeds.map((feed) => (
            <section
              key={`${feed.provider}:${feed.feed}`}
              className="grid gap-3 border-t border-hairline pt-4 first:border-0 first:pt-0 md:grid-cols-[minmax(120px,1fr)_minmax(0,2fr)]"
              aria-label={`${human(feed.provider)} ${human(feed.feed)}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[13px] font-medium">
                  {t(`lab.providers.${feed.provider}`, {
                    defaultValue: human(feed.provider),
                  })}
                </h3>
                <Badge
                  tone={
                    feed.state === "available" || feed.state === "complete"
                      ? "positive"
                      : feed.state === "fetch_failed"
                        ? "alert"
                        : "warning"
                  }
                >
                  {t(`lab.syncHealth.states.${feed.state}`, {
                    defaultValue: human(feed.state),
                  })}
                </Badge>
                <span className="text-[12px] text-muted">
                  {t(`lab.metrics.${feed.feed}`, {
                    defaultValue: human(feed.feed),
                  })}
                </span>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12px] sm:grid-cols-3">
                <div>
                  <dt className="text-muted">{t("lab.syncHealth.lastAttempt")}</dt>
                  <dd>{timestamp(feed.last_attempt_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted">{t("lab.syncHealth.lastSuccess")}</dt>
                  <dd>{timestamp(feed.last_success_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted">{t("lab.syncHealth.measurement")}</dt>
                  <dd>{timestamp(feed.latest_measurement_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted">{t("lab.syncHealth.credentials")}</dt>
                  <dd>
                    {t(`lab.syncHealth.credentialsStates.${feed.credentials_state}`, {
                      defaultValue: human(feed.credentials_state),
                    })}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">{t("lab.syncHealth.retry")}</dt>
                  <dd>
                    {t(`lab.syncHealth.retryStates.${feed.retry_state}`, {
                      defaultValue: human(feed.retry_state),
                    })}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">{t("lab.syncHealth.checkpoint")}</dt>
                  <dd>
                    {t(feed.has_checkpoint ? "common.yes" : "common.no", {
                      defaultValue: feed.has_checkpoint ? "Yes" : "No",
                    })}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">{t("lab.syncHealth.failedAttempts")}</dt>
                  <dd className="num">{feed.failed_attempts}</dd>
                </div>
                {feed.error_class && (
                  <div>
                    <dt className="text-muted">{t("lab.syncHealth.error")}</dt>
                    <dd>
                      {t(`lab.syncHealth.errors.${feed.error_class}`, {
                        defaultValue: human(feed.error_class),
                      })}
                    </dd>
                  </div>
                )}
              </dl>
            </section>
          ))}
        </div>
      )}
    </Card>
  );
}
