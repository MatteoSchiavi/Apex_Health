import { useTranslation } from "react-i18next";
import { Badge, Card, CardHeader, ErrorNote, Loading } from "../../components/kit";
import { useUi } from "../../app/stores/ui";
import { human } from "./shared";
import { useSyncHealth } from "./syncHealth";

export default function SyncHealthPanel() {
  const { t, i18n } = useTranslation();
  const timezone = useUi(s => s.me?.timezone);
  const query = useSyncHealth();
  const feeds = query.data?.feeds ?? [];
  const accounts = query.data?.accounts ?? [];
  const timestamp = (value: string | null) => value ? new Date(value).toLocaleString(i18n.language, { timeZone: timezone }) : t("lab.syncHealth.timeUnknown");
  const issue = (error: string) => t(`lab.syncHealth.errors.${error}`, { defaultValue: t("lab.syncHealth.errors.unknown") });

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
      {query.isLoading && <Loading />}
      {query.isError && <ErrorNote message={t("lab.syncHealth.unavailable")} />}
      {!query.isLoading && !query.isError && feeds.length === 0 && accounts.length === 0 && (
        <p className="text-[13px] text-muted">{t("lab.syncHealth.empty")}</p>
      )}
      {!!accounts.length && <div className="mb-6 grid gap-4">{accounts.map(account => {
        const provider = t(`lab.providers.${account.provider}`, { defaultValue: human(account.provider) });
        return <section key={account.provider} aria-label={t("lab.syncHealth.accountRegion", { provider })} className="border-t border-hairline pt-4">
          <div className="mb-3 flex flex-wrap items-center gap-3"><h3 className="text-[14px] font-medium">{provider}</h3><Badge tone={account.state === "successful" ? "positive" : account.state === "failed" || account.state === "auth_required" ? "alert" : account.state === "partial" || account.state === "delayed" ? "warning" : "neutral"}>{t("lab.syncHealth.accountStates." + account.state)}</Badge></div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[12px] sm:grid-cols-3">
            <div><dt className="text-muted">{t("lab.syncHealth.lastAttempt")}</dt><dd>{timestamp(account.last_attempt_at)}</dd></div>
            <div><dt className="text-muted">{t("lab.syncHealth.accountLastSuccess")}</dt><dd>{timestamp(account.last_success_at)}</dd>{account.has_successful_sync && !account.last_success_at && <dd className="mt-1 text-muted">{t("lab.syncHealth.successTimeUnknown")}</dd>}</div>
            <div><dt className="text-muted">{t("lab.syncHealth.measurement")}</dt><dd>{timestamp(account.latest_measurement_at)}</dd></div>
            <div><dt className="text-muted">{t("lab.syncHealth.dataFreshness")}</dt><dd>{t("lab.syncHealth.freshness." + account.data_freshness)}</dd></div>
            <div><dt className="text-muted">{t("lab.syncHealth.credentials")}</dt><dd>{t("lab.syncHealth.credentialsStates." + account.credentials_state)}</dd></div>
            <div><dt className="text-muted">{t("lab.syncHealth.failedAttempts")}</dt><dd className="num">{account.failed_attempts}</dd></div>
            {account.error_class && <div><dt className="text-muted">{t("lab.syncHealth.error")}</dt><dd>{issue(account.error_class)}</dd></div>}
          </dl>
          {account.state === "partial" && <p className="mt-3 text-[13px] text-muted">{t("lab.syncHealth.partialCounts", { streams: account.streams_failed, records: account.unprocessed })}</p>}
          {account.data_freshness === "stale" && <p className="mt-3 text-[12px] text-muted">{t("lab.syncHealth.oldMeasurementsNote", { hours: account.stale_after_hours })}</p>}
        </section>;
      })}</div>}
      {!!feeds.length && (
        <div className="grid gap-3">
          {feeds.map((feed) => (
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
                      {issue(feed.error_class)}
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
