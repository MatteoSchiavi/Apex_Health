import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { Button } from "../../components/kit";

type Deployment = { version: string; stage: string; commit: string };

export default function DeploymentFooter() {
  const { t } = useTranslation();
  const release = useQuery({
    queryKey: ["deployment-version"],
    queryFn: async () => {
      const value = await api.get<Deployment>("/version");
      if (!value || typeof value.version !== "string" || typeof value.stage !== "string" || typeof value.commit !== "string")
        throw new Error("Invalid deployment version");
      return value;
    },
    staleTime: 0,
    refetchInterval: 60_000,
  });
  const commit = release.data?.commit;
  return <footer aria-label={t("adminRelease.title")} className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-5 text-[12px] text-muted">
    <div className="min-w-0 space-y-1">
      {release.data && <>
        <p>{t("adminRelease.version")} {release.data.version} · {release.data.stage}</p>
        <p className="break-all">{t("adminRelease.commit")} {commit && /^[a-f0-9]{40}$/i.test(commit)
          ? <a href={`https://github.com/MatteoSchiavi/Apex_Health/commit/${commit}`} target="_blank" rel="noreferrer" className="text-link"><code>{commit}</code></a>
          : <code>{commit}</code>}</p>
      </>}
      {release.isLoading && <p role="status">{t("common.loading")}</p>}
      {release.isError && <p role="status">{t(release.data ? "adminRelease.stale" : "adminRelease.unavailable")}</p>}
    </div>
    <Button variant="ghost" disabled={release.isFetching} onClick={() => void release.refetch()}>{t("adminRelease.refresh")}</Button>
  </footer>;
}
