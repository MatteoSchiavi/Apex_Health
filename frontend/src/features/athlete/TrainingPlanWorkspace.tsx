import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, Card, CardHeader, Loading } from "../../components/kit";
import type { Doc } from "../lab/types";
import type { AthleteImport, AthleteTemplate, PlanDraft } from "./importTypes";
import { AthleteInformationImport } from "./AthleteInformationImport";
import { PlanDocumentPanel } from "./PlanDocumentPanel";
import { planReadiness } from "./planReadiness";

const planUrl = (anchor: string, date: string | null) => {
  const params = new URLSearchParams({ tab: "planning" });
  if (date !== null) params.set("date", date);
  return `/app/training?${params}${anchor ? `#${anchor}` : ""}`;
};

/** Planning is a training workflow. Its source documents remain available in Lab. */
export function TrainingPlanWorkspace() {
  const { t } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const location = useLocation();
  const selectedDate = new URLSearchParams(location.search).get("date");
  const navigate = useNavigate();
  const documents = useQuery({ queryKey: ["lab", uid, "/lab/documents"], queryFn: () => api.get<Doc[]>("/lab/documents") });
  const drafts = useQuery({ queryKey: ["plan-drafts", uid], queryFn: () => api.get<PlanDraft[]>("/lab/plan-drafts") });
  const imports = useQuery({ queryKey: ["athlete-imports", uid], queryFn: () => api.get<AthleteImport[]>("/lab/athlete-imports") });
  const templates = useQuery({ queryKey: ["athlete-templates", uid], queryFn: () => api.get<AthleteTemplate[]>("/athlete/templates") });
  const loading = documents.isLoading || drafts.isLoading || imports.isLoading || templates.isLoading;
  const failed = documents.isError || drafts.isError || imports.isError || templates.isError;
  // A failed refresh still has usable account-scoped data. Keep the review
  // mounted so retrying a read cannot discard corrections in its editor.
  const available = documents.data !== undefined && drafts.data !== undefined && imports.data !== undefined && templates.data !== undefined;
  const retrying = [documents, drafts, imports, templates].some(query => query.isError && query.isFetching);
  function retryFailed() {
    for (const query of [documents, drafts, imports, templates]) if (query.isError) void query.refetch();
  }
  const latestImports = (imports.data ?? []).filter((item, index, all) => all.findIndex(other => other.document_id === item.document_id) === index);
  const planDocs = (documents.data ?? []).filter(doc => drafts.data?.some(draft => draft.document_id === doc.id) || latestImports.some(item => item.document_id === doc.id));
  const selectedDocument = location.hash.match(/^#(?:import-)?document-(\d+)$/)?.[1];
  const selectedTemplate = location.hash.match(/^#template-(\d+)$/)?.[1];
  const selectedDoc = planDocs.find(doc => doc.id === Number(selectedDocument));
  const selectedDraft = drafts.data?.find(item => item.document_id === Number(selectedDocument));
  const selectedImport = latestImports.find(item => item.document_id === Number(selectedDocument));
  const reviewDocumentDraft = !!selectedDraft && !location.hash.startsWith("#import-document-") && selectedImport?.receipts.dated_plan?.draft_id !== selectedDraft.id;
  const template = templates.data?.find(item => item.id === Number(selectedTemplate));
  const hasPlans = !!planDocs.length || !!templates.data?.length;
  useEffect(() => {
    if (location.hash || loading || failed || !hasPlans) return;
    const draft = drafts.data?.find(item => item.status === "draft" && (planDocs.some(doc => doc.id === item.document_id) || templates.data?.some(row => row.id === item.template_id)));
    const anchor = draft?.template_id ? `template-${draft.template_id}` : draft?.document_id ? `document-${draft.document_id}` : planDocs.length ? `document-${planDocs[0].id}` : `template-${templates.data![0].id}`;
    navigate(planUrl(anchor, selectedDate), { replace: true });
  }, [location.hash, selectedDate, loading, failed, hasPlans, drafts.data, planDocs, templates.data, navigate]);
  const importing = location.hash === "#import" || (!hasPlans && !location.hash);
  const unknownSelection = !!location.hash && !importing && !selectedDoc && !template;
  return <div className="space-y-6">
    <Card>
      <CardHeader title={<h2>{t("v01Plan.title")}</h2>} right={<Link className="text-link text-[13px]" to={planUrl("import", selectedDate)}>{t("v01Plan.import_plan")}</Link>} />
      <p className="max-w-2xl text-[14px] text-muted">{t("v01Plan.intro")}</p>
      <ol className="mt-5 grid gap-3 text-[13px] sm:grid-cols-3">{["step_import", "step_dates", "step_activate"].map((key, index) => <li key={key} className="flex gap-2"><span className="font-medium text-ink">{index + 1}.</span><span>{t(`v01Plan.${key}`)}</span></li>)}</ol>
    </Card>
    {failed && <Card><p role="alert" className="text-[13px]">{t(available ? "workflowReview.plan.refresh_error" : "v01Plan.load_error")}</p><Button className="mt-4" variant="ghost" disabled={retrying} onClick={retryFailed}>{t("common.retry")}</Button></Card>}
    {!available && loading && <Loading />}
    {available && <>
      {hasPlans && <section aria-label={t("v01Plan.saved_plans")} className="space-y-3">
        <h3 className="text-[15px] font-medium">{t("v01Plan.saved_plans")}</h3>
        <div className="grid gap-3 lg:grid-cols-2">{planDocs.map(doc => {
          const draft = drafts.data?.find(item => item.document_id === doc.id);
          const imported = latestImports.find(item => item.document_id === doc.id);
          const readiness = draft ? planReadiness(draft.structure) : null;
          return <Card key={doc.id} className={selectedDoc?.id === doc.id ? "ring-1 ring-primary" : ""}>
            <div className="flex flex-wrap items-start justify-between gap-2"><h4 className="min-w-0 break-words text-[14px] font-medium">{draft?.structure.title || imported?.proposal.weekly?.title || imported?.proposal.dated?.title || doc.filename}</h4><Badge tone={draft?.status === "confirmed" ? "positive" : "warning"}>{t(draft?.status === "confirmed" ? "athlete.structure_confirmed" : "v01Plan.draft_not_active")}</Badge></div>
            <p className="mt-2 text-[13px] text-muted">{t(draft?.status === "confirmed" ? "v01Plan.confirmed_note" : readiness?.ready ? "v01Plan.ready_review" : draft ? "v01Plan.draft_needs_dates" : imported?.receipts.profile ? "v01Plan.profile_only" : "v01Plan.import_needs_review")}</p>
            {draft && <p className="mt-2 text-[12px] text-muted">{t("v01Plan.workout_count", { count: draft.structure.sessions.length })}{readiness?.missingDates.length ? ` · ${t("v01Plan.undated_count", { count: readiness.missingDates.length })}` : ""}</p>}
            <Link to={planUrl(`document-${doc.id}`, selectedDate)} aria-current={selectedDoc?.id === doc.id ? "true" : undefined} className="mt-4 inline-flex min-h-10 items-center text-link">{t(draft?.status === "confirmed" ? "v01Plan.view_plan" : "v01Plan.continue_review")}</Link>
          </Card>;
        })}{templates.data?.map(item => <Card key={`template-${item.id}`} className={template?.id === item.id ? "ring-1 ring-primary" : ""}>
          <h4 className="text-[14px] font-medium">{item.structure.title || t("athleteImport.weekly_template")}</h4><p className="mt-2 text-[13px] text-muted">{t("v01Plan.template_note", { count: item.structure.rows.length })}</p>
          <Link to={planUrl(`template-${item.id}`, selectedDate)} aria-current={template?.id === item.id ? "true" : undefined} className="mt-4 inline-flex min-h-10 items-center text-link">{t("athleteImport.choose_dates")}</Link>
        </Card>)}</div>
      </section>}
      {unknownSelection && <Card><p role="alert" className="text-[13px]">{t("v01Plan.not_found")}</p><Link className="mt-3 inline-block text-link" to={planUrl("", selectedDate)}>{t("v01Plan.saved_plans")}</Link></Card>}
      {selectedDoc && (!selectedImport || reviewDocumentDraft) && <Card>
        <CardHeader title={<h3>{selectedDoc.filename}</h3>} />
        <details><summary className="cursor-pointer text-[13px]">{t("athleteImport.review_source")}</summary><blockquote className="mt-3 whitespace-pre-wrap break-words text-[13px] text-muted">{selectedDoc.excerpt}</blockquote></details>
        <PlanDocumentPanel key={`${uid}:${selectedDoc.id}`} document={selectedDoc} />
        {selectedImport && <Link to={planUrl(`import-document-${selectedDoc.id}`, selectedDate)} className="mt-5 inline-flex min-h-10 items-center text-link">{t("v01Plan.review_import_separately")}</Link>}
      </Card>}
      {(importing || (selectedImport && !reviewDocumentDraft) || template) && <AthleteInformationImport key={`${uid}:${location.hash || "new-import"}`} planning />}
    </>}
  </div>;
}
