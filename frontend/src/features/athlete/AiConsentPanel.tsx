import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, Card, CardHeader, ErrorNote, Loading } from "../../components/kit";
import type { AiState } from "./types";

export function useAiState() {
  const uid = useUi(s => s.me?.user_id);
  return useQuery({ queryKey: ["athlete-ai", uid], queryFn: () => api.get<AiState>("/athlete/ai"), staleTime: 15000 });
}

export function AiConsentPanel() {
  const { t, i18n } = useTranslation();
  const state = useAiState();
  const qc = useQueryClient();
  const [agree, setAgree] = useState(false);
  const mutation = useMutation({
    mutationFn: (active: boolean) => api.put<AiState>("/athlete/ai/consent", {
      active, policy_version: state.data!.policy_version, provider_identity: state.data!.provider_identity,
    }),
    onSuccess: () => { setAgree(false); qc.invalidateQueries({ queryKey: ["athlete-ai"] }); qc.invalidateQueries({ queryKey: ["me"] }); },
  });
  if (state.isLoading) return <Loading />;
  if (!state.data || state.isError) return <ErrorNote />;
  const data = state.data;
  const active = data.consent?.active;
  return <Card>
    <CardHeader title={t("athlete.ai_title")} right={<Badge>{t("athlete.ai_" + data.effective_access)}</Badge>} />
    <p className="text-[13px] text-ink2">{t("athlete.ai_disclosure")}</p>
    <p className="mt-3 text-[13px] text-muted">{t("athlete.ai_withdrawal_note")}</p>
    <Link to="/legal/privacy" className="text-link mt-3 inline-block">{t("athlete.privacy_notice")}</Link>
    <details className="mt-3 text-[12px] text-muted"><summary className="cursor-pointer">{t("athlete.configured_provider")}</summary><p className="mt-2 break-all">{data.provider_identity}</p></details>
    {mutation.isError && <ErrorNote />}
    {active ? <Button className="mt-4" variant="ghost" disabled={mutation.isPending} onClick={() => mutation.mutate(false)}>{t("athlete.withdraw_ai")}</Button> : <div className="mt-4">
      <label className="flex items-start gap-3 text-[13px]"><input className="mt-1 h-4 w-4 shrink-0" type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} /><span>{t("athlete.ai_agreement")}</span></label>
      <Button className="mt-4" disabled={!agree || mutation.isPending} onClick={() => mutation.mutate(true)}>{t("athlete.enable_ai")}</Button>
      {data.consent?.withdrawn_at && <p className="mt-3 text-[12px] text-muted">{t("athlete.consent_withdrawn")}</p>}
    </div>}
    <div className="mt-5 border-t border-hairline pt-4 text-[12px] text-muted">
      <p>{t(data.budget.exhausted ? "athlete.budget_exhausted" : "athlete.budget_remaining", { count: Math.max(0, data.budget.limit_tokens - data.budget.used_tokens) })}</p>
      <p className="mt-1">{t("athlete.budget_reset")}</p>
      <details className="mt-2"><summary className="cursor-pointer">{t("athlete.budget_categories")}</summary><ul className="mt-2 space-y-1">{Object.entries(data.budget.categories).map(([key, value]) => <li key={key}>{t("athlete.category_" + key)} · {Math.max(0, value.limit_tokens-value.used_tokens).toLocaleString(i18n.language)}</li>)}</ul></details>
    </div>
  </Card>;
}
