import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ApiError, api } from "../../app/api";
import { Button, Card, CardHeader, Input, Loading, Select } from "../../components/kit";
import { ReadError } from "../../components/ReadError";
import { useUi } from "../../app/stores/ui";

type Context = {
  route_id: string;
  terrain: string;
  indoor: boolean;
  time_convention: "elapsed" | "moving";
  effort_type: "easy" | "steady";
};
type ContextResponse = {
  activity_id: number;
  revision: string;
  providers: string[];
  assertions: { provider: string; context: Context; provenance: { asserted_at: string; verified: false } }[];
  recorded_context_providers: string[];
  outdoor_weather_available: boolean;
};

function ProviderEditor({ data, provider, onDraftState, onSaved, stale }: {
  data: ContextResponse; provider: string;
  onDraftState: (active: boolean, pending: boolean, conflict: boolean) => void;
  onSaved: () => void;
  stale: boolean;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useUi(state => state.me?.user_id);
  const saved = data.assertions.find(row => row.provider === provider);
  const [route, setRoute] = useState(saved?.context.route_id ?? "");
  const [terrain, setTerrain] = useState(saved?.context.terrain ?? "");
  const [setting, setSetting] = useState(saved ? (saved.context.indoor ? "indoor" : "outdoor") : "");
  const [convention, setConvention] = useState(saved?.context.time_convention ?? "");
  const [effort, setEffort] = useState(saved?.context.effort_type ?? "");
  const [review, setReview] = useState<{ context: Context | null } | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const mutation = useMutation({
    mutationFn: (context: Context | null) => api.put<ContextResponse>(`/activities/${data.activity_id}/comparison-context`, {
      provider, expected_revision: data.revision, context, reviewed: true,
    }),
    onSuccess: response => {
      qc.setQueryData(["activity-comparison-context", uid, data.activity_id], response);
      ["activity", "athlete-sport-overview", "endurance", "gear-comparison"].forEach(key => qc.invalidateQueries({ queryKey: [key] }));
      setReview(null);
      setAcknowledged(false);
      onSaved();
    },
  });
  const dirty = route !== (saved?.context.route_id ?? "") || terrain !== (saved?.context.terrain ?? "")
    || setting !== (saved ? (saved.context.indoor ? "indoor" : "outdoor") : "")
    || convention !== (saved?.context.time_convention ?? "") || effort !== (saved?.context.effort_type ?? "");
  const active = dirty || !!review || mutation.isPending;
  const conflict = mutation.error instanceof ApiError && mutation.error.status === 409;
  useEffect(() => onDraftState(active, mutation.isPending, conflict), [active, mutation.isPending, conflict, onDraftState]);
  const options = (keys: string[]) => [{ value: "", label: t("activityComparison.choose") }, ...keys.map(value => ({ value, label: t("activityComparison." + value) }))];
  const valid = route.trim().length > 0 && route.trim().length <= 120 && terrain && setting && convention && effort;
  function beginReview(context: Context | null) {
    mutation.reset();
    setAcknowledged(false);
    setReview({ context });
  }
  if (review) return <div className="space-y-4">
    <h3 className="text-[15px] font-medium">{t("activityComparison.review")}</h3>
    {review.context ? <dl className="grid gap-2 text-[13px]">
      <div><dt className="inline text-muted">{t("activityComparison.route")}: </dt><dd className="inline break-words">{review.context.route_id}</dd></div>
      <div><dt className="inline text-muted">{t("activityComparison.terrain")}: </dt><dd className="inline">{t("activityComparison." + review.context.terrain)}</dd></div>
      <div><dt className="inline text-muted">{t("activityComparison.setting")}: </dt><dd className="inline">{t("activityComparison." + (review.context.indoor ? "indoor" : "outdoor"))}</dd></div>
      <div><dt className="inline text-muted">{t("activityComparison.time")}: </dt><dd className="inline">{t("activityComparison." + review.context.time_convention)}</dd></div>
      <div><dt className="inline text-muted">{t("activityComparison.effort")}: </dt><dd className="inline">{t("activityComparison." + review.context.effort_type)}</dd></div>
    </dl> : <p className="text-[13px]">{t("activityComparison.remove_review")}</p>}
    <p className="text-[12px] text-muted">{t("activityComparison.provenance")}</p>
    <label className="flex items-start gap-2 text-[13px]"><input type="checkbox" checked={acknowledged} disabled={mutation.isPending} onChange={event => setAcknowledged(event.target.checked)} />{t("activityComparison.acknowledge")}</label>
    <div className="flex flex-wrap gap-3"><Button disabled={!acknowledged || mutation.isPending || conflict || stale} onClick={() => mutation.mutate(review.context)}>{t("activityComparison.save")}</Button><Button variant="ghost" disabled={mutation.isPending} onClick={() => setReview(null)}>{t("activityComparison.back")}</Button></div>
    {mutation.isError && <p role="alert" className="text-[13px]">{t(mutation.error instanceof ApiError && mutation.error.status === 409 ? "activityComparison.conflict" : "activityComparison.error")}</p>}
  </div>;
  return <form className="space-y-4" onSubmit={event => {
    event.preventDefault();
    if (valid) beginReview({ route_id: route.trim(), terrain, indoor: setting === "indoor", time_convention: convention as Context["time_convention"], effort_type: effort as Context["effort_type"] });
  }}>
    {saved && <p className="text-[12px] text-muted">{t("activityComparison.saved", { date: new Date(saved.provenance.asserted_at).toLocaleString() })}</p>}
    <div className="grid gap-4 sm:grid-cols-2">
      <Input label={t("activityComparison.route")} value={route} onChange={setRoute} required maxLength={120} />
      <Select label={t("activityComparison.terrain")} value={terrain} onChange={setTerrain} options={options(["paved", "trail", "track", "treadmill", "gravel", "mixed", "other"])} />
      <Select label={t("activityComparison.setting")} value={setting} onChange={setSetting} options={options(["indoor", "outdoor"])} />
      <Select label={t("activityComparison.time")} value={convention} onChange={setConvention} options={options(["elapsed", "moving"])} />
      <Select label={t("activityComparison.effort")} value={effort} onChange={setEffort} options={options(["easy", "steady"])} />
    </div>
    <p className="text-[12px] text-muted">{t("activityComparison.route_help")}</p>
    {setting === "outdoor" && !data.outdoor_weather_available && <p className="text-[13px] text-muted">{t("activityComparison.weather_missing")}</p>}
    {data.recorded_context_providers.length > 0 && <p className="text-[12px] text-muted">{t("activityComparison.recorded_context")}</p>}
    <div className="flex flex-wrap gap-3"><Button disabled={!valid} onClick={() => {
      if (valid) beginReview({ route_id: route.trim(), terrain, indoor: setting === "indoor", time_convention: convention as Context["time_convention"], effort_type: effort as Context["effort_type"] });
    }}>{t("activityComparison.review")}</Button>{saved && <Button variant="ghost" onClick={() => beginReview(null)}>{t("activityComparison.remove")}</Button>}</div>
  </form>;
}

export function ComparisonContextEditor({ activityId }: { activityId: number }) {
  const { t } = useTranslation();
  const uid = useUi(state => state.me?.user_id);
  const [provider, setProvider] = useState("");
  const scope = `${uid}:${activityId}`;
  const [retained, setRetained] = useState<{ scope: string; data: ContextResponse } | null>(null);
  const [pending, setPending] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const query = useQuery({ queryKey: ["activity-comparison-context", uid, activityId], queryFn: () => api.get<ContextResponse>(`/activities/${activityId}/comparison-context`), refetchOnWindowFocus: false });
  const snapshot = retained?.scope === scope ? retained.data : null;
  const data = snapshot ?? query.data;
  const selected = data?.providers.includes(provider) ? provider : data?.providers[0] ?? "";
  const draftState = useCallback((active: boolean, saving: boolean, conflicted: boolean) => {
    setPending(saving);
    setConflict(conflicted);
    setRetained(previous => active && query.data
      ? previous?.scope === scope ? previous : { scope, data: query.data }
      : null);
  }, [query.data, scope]);
  const saved = useCallback(() => setRetained(null), []);
  async function reload() {
    const result = await query.refetch();
    if (result.isSuccess && useUi.getState().me?.user_id === uid) {
      setRetained(null);
      setReloadVersion(value => value + 1);
    }
  }
  return <Card>
    <CardHeader title={t("activityComparison.title")} />
    <p className="mb-4 text-[13px] text-muted">{t("activityComparison.description")}</p>
    {query.isError && <ReadError label={t("activityComparison.retry_context")} stale={!!data} pending={query.isFetching} retry={() => void query.refetch()} />}
    {(conflict || (snapshot && query.data && snapshot.revision !== query.data.revision)) && <div className="mb-4 space-y-3"><p role="status" className="text-[13px] text-muted">{t("activityComparison.newer_context")}</p><p className="text-[12px] text-muted">{t("activityComparison.reload_replaces")}</p><Button variant="ghost" disabled={pending || query.isFetching} onClick={() => void reload()}>{t("activityComparison.reload")}</Button></div>}
    {query.isLoading ? <Loading /> : !data ? null : selected ? <>
      <fieldset disabled={pending}><Select className="mb-4" label={t("activityComparison.provider")} value={selected} onChange={value => {
        if (value === selected || (snapshot && !window.confirm(t("activityComparison.discard_provider")))) return;
        setRetained(null);
        setProvider(value);
      }} options={data.providers.map(value => ({ value, label: value }))} /></fieldset>
      <ProviderEditor key={`${scope}:${selected}:${data.revision}:${reloadVersion}`} data={data} provider={selected} onDraftState={draftState} onSaved={saved} stale={!!query.data && data.revision !== query.data.revision} />
    </> : <p className="text-[13px] text-muted">{t("activityComparison.no_provider")}</p>}
    <p className="mt-4 text-[12px] text-muted">{t("activityComparison.eligibility")}</p>
    <p className="mt-2 text-[12px] text-muted">{t("activityComparison.climbs")}</p>
  </Card>;
}
