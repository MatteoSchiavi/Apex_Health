import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { api, ApiError, type Me } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Badge, Button, Card, CardHeader, Input, Loading } from "../../components/kit";
import { useAiState } from "./AiConsentPanel";
import { availabilityError, type AvailabilityEntry } from "./AvailabilityEditor";
import { ImportProfileReview, ImportEvidence } from "./ImportProfileReview";
import { CalendarPreview, ImportPlanReview } from "./ImportPlanReview";
import type { AthleteProfile } from "./types";
import type { Doc } from "../lab/types";
import type { AthleteImport, AthleteTemplate, ImportProposal, PlanDraft } from "./importTypes";

type SourceDoc = Doc & { coach_eligible?: boolean; extraction_state?: string };
interface RetainedReview {
  current: AthleteImport; proposal: ImportProposal; selected: string[]; expectedProfileRevision: number | null; entry: AvailabilityEntry; planOpen: boolean;
}
// Preserve corrections across SPA browser-back navigation without persisting
// private source material in localStorage or changing canonical server facts.
const retainedReviews = new Map<number, RetainedReview>();
const emptyEntry = (): AvailabilityEntry => ({ selected: [0, 1, 2, 3, 4], start: "", end: "" });
const proposedFields = (proposal: ImportProposal) => [...(proposal.profile.training_focus !== null ? ["training_focus"] : []), ...Object.keys(proposal.profile.context).filter(key => !["ftp", "hr_zones", "power_zones", "onboarding_step"].includes(key)).map(key => "context." + key)];

export function AthleteInformationImport() {
  const { t } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const location = useLocation();
  const [anchor, setAnchor] = useState(window.location.hash);
  useEffect(() => { setAnchor(location.hash); }, [location.hash]);
  useEffect(() => { const update = () => setAnchor(window.location.hash); window.addEventListener("hashchange", update); return () => window.removeEventListener("hashchange", update); }, []);
  const qc = useQueryClient();
  const retained = uid == null ? undefined : retainedReviews.get(uid);
  const ai = useAiState();
  const imports = useQuery({ queryKey: ["athlete-imports", uid], queryFn: () => api.get<AthleteImport[]>("/lab/athlete-imports") });
  const documents = useQuery({ queryKey: ["lab", uid, "/lab/documents"], queryFn: () => api.get<SourceDoc[]>("/lab/documents") });
  const profile = useQuery({ queryKey: ["athlete-profile", uid], queryFn: () => api.get<AthleteProfile>("/athlete/profile") });
  const planDrafts = useQuery({ queryKey: ["plan-drafts", uid], queryFn: () => api.get<PlanDraft[]>("/lab/plan-drafts") });
  const handledAnchor = useRef("");
  const templates = useQuery({ queryKey: ["athlete-templates", uid], queryFn: () => api.get<AthleteTemplate[]>("/athlete/templates") });
  const [source, setSource] = useState<SourceDoc | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const fileReadSequence = useRef(0);
  const [sourceText, setSourceText] = useState("");
  const [useAi, setUseAi] = useState(false);
  const [current, setCurrent] = useState<AthleteImport | null>(retained?.current ?? null);
  const [proposal, setProposal] = useState<ImportProposal | null>(retained?.proposal ?? null);
  const [selected, setSelected] = useState<string[]>(retained?.selected ?? []);
  const [expectedProfileRevision, setExpectedProfileRevision] = useState<number | null>(retained?.expectedProfileRevision ?? null);
  const [entry, setEntry] = useState<AvailabilityEntry>(retained?.entry ?? emptyEntry());
  const [planOpen, setPlanOpen] = useState(retained?.planOpen ?? false);
  const [message, setMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [chosenTemplate, setChosenTemplate] = useState<AthleteTemplate | null>(null);
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [preview, setPreview] = useState<PlanDraft | null>(null);
  const reviewRoot = useRef<HTMLDivElement>(null);
  const dirty = !!proposal && !!current && JSON.stringify(proposal) !== JSON.stringify(current.proposal);
  const aiAvailable = !!ai.data && ai.data.effective_access !== "disabled" && !ai.data.budget.exhausted;
  const incompleteAvailability = Boolean(entry.start || entry.end) || !!availabilityError(proposal?.profile.context.availability ?? []);
  const invalidSelection = selected.some(field => field === "training_focus" ? proposal?.profile.training_focus === null : !Object.hasOwn(proposal?.profile.context ?? {}, field.replace("context.", "")));
  const requiredProfileIssues = proposal?.issues.some(issue => issue.required && selected.some(field => { const key = issue.field.replace(/^profile\./, ""); return key === field || key.startsWith(field + ".") || field.startsWith(key + ".") || key === "profile"; }));
  const requiredWeeklyIssues = proposal?.issues.some(issue => issue.required && (issue.field === "weekly" || issue.field.startsWith("weekly.")));
  const requiredDatedIssues = proposal?.issues.some(issue => issue.required && (issue.field === "dated" || issue.field.startsWith("dated.")));
  async function invalidate() {
    await Promise.all(["athlete-imports", "athlete-profile", "me", "athlete-day", "athlete-templates", "plan-drafts", "lab", "context-docs"].map(key => qc.invalidateQueries({ queryKey: [key] })));
    void api.get<Me>("/me").then(me => useUi.getState().setMe(me)).catch(() => {});
  }
  function open(next: AthleteImport, skipGuard = false) {
    if (!skipGuard && (dirty || entry.start || entry.end) && !window.confirm(t("athlete.leave_unsaved"))) return;
    setCurrent(next); setProposal(structuredClone(next.proposal)); setSelected(next.receipts.profile?.fields ?? proposedFields(next.proposal));
    setExpectedProfileRevision(profile.data?.revision ?? null); setEntry(emptyEntry());
    const savedDraft = planDrafts.data?.find(draft => draft.id === next.receipts.dated_plan?.draft_id);
    setPlanOpen(!!savedDraft); setPreview(savedDraft ?? null); setChosenTemplate(null); setMessage(null); setLocalError(null);
    action.reset(); previewTemplate.reset(); activate.reset();
    requestAnimationFrame(() => reviewRoot.current?.focus());
  }
  useEffect(() => {
    if (uid == null) return;
    if (current && proposal && (dirty || entry.start || entry.end)) retainedReviews.set(uid, { current, proposal, selected, expectedProfileRevision, entry, planOpen });
    else retainedReviews.delete(uid);
  }, [uid, current, proposal, selected, expectedProfileRevision, entry, planOpen, dirty]);
  useEffect(() => () => { if (uid != null && useUi.getState().me?.user_id !== uid) retainedReviews.delete(uid); }, [uid]);
  useEffect(() => {
    if (!dirty && !entry.start && !entry.end) return;
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const click = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      const link = target?.closest<HTMLAnchorElement>("a[href]");
      const button = target?.closest<HTMLButtonElement>("button[aria-pressed]");
      const leavesPage = link && link.origin === window.location.origin && link.target !== "_blank" && !link.download && link.href !== window.location.href && link.pathname.startsWith("/app");
      const leavesLabTab = button && !button.closest("[data-athlete-import]") && button.getAttribute("aria-pressed") === "false";
      if (leavesPage || leavesLabTab) {
        if (!window.confirm(t("athlete.leave_unsaved"))) { event.preventDefault(); event.stopImmediatePropagation(); }
        else if (uid != null) retainedReviews.delete(uid);
      }
    };
    window.addEventListener("beforeunload", guard); document.addEventListener("click", click, true);
    return () => { window.removeEventListener("beforeunload", guard); document.removeEventListener("click", click, true); };
  }, [dirty, entry]);
  function edit(next: ImportProposal) { setProposal(next); setMessage(null); setPreview(null); }
  async function saveReview(forceVersion = false) {
    if (!current || !proposal) throw new Error(t("athleteImport.review_missing"));
    if (incompleteAvailability) throw new Error(t("athlete.availability_apply_first"));
    if (!dirty && !forceVersion) return current;
    const next = await api.put<AthleteImport>(`/lab/athlete-imports/${current.id}`, { payload_hash: current.payload_hash, proposal });
    setCurrent(next); setProposal(structuredClone(next.proposal));
    return next;
  }
  const preparePdf = useMutation({ mutationFn: async (next: File) => {
    const form = new FormData(); form.append("file", next);
    return api.post<SourceDoc>("/lab/documents?for_athlete_import=true", form);
  }, onSuccess: doc => { setSource(doc); setSourceText(doc.excerpt ?? ""); void qc.invalidateQueries({ queryKey: ["lab"] }); } });
  const analyze = useMutation({ mutationFn: async () => {
    setLocalError(null); setMessage(null);
    let doc = source;
    if (!doc) {
      if (!sourceText.trim()) throw new Error(t(file?.name.toLowerCase().endsWith(".pdf") ? "athleteImport.pdf_paste" : "athleteImport.source_required"));
      const form = new FormData(); form.append("file", file ?? new File([sourceText], "athlete-information.txt", { type: "text/plain" }));
      doc = await api.post<SourceDoc>("/lab/documents?for_athlete_import=true", form);
      setSource(doc);
    }
    if (!sourceText.trim()) throw new Error(t("athleteImport.pdf_paste"));
    if (doc.status !== "confirmed" || doc.excerpt !== sourceText) {
      doc = await api.post<SourceDoc>(`/lab/documents/${doc.id}/confirm`, { content_hash: doc.content_hash, reviewed_text: sourceText }); setSource(doc);
    }
    return api.post<AthleteImport>("/lab/athlete-imports", { document_id: doc.id, expected_document_revision: doc.revision, use_ai: useAi && aiAvailable });
  }, onSuccess: next => { open(next, true); void invalidate(); } });
  const action = useMutation({ mutationFn: async (kind: "review" | "profile" | "template" | "dated") => {
    setMessage(null); setLocalError(null);
    const changedApprovedFields = !!current?.receipts.profile && JSON.stringify([...current.receipts.profile.fields].sort()) !== JSON.stringify([...selected].sort());
    const reviewed = await saveReview(kind === "profile" && changedApprovedFields);
    if (kind === "review") return { kind, reviewed };
    if (kind === "profile") {
      if (expectedProfileRevision === null) throw new Error(t("athleteImport.profile_unavailable"));
      const response = await api.post<{ import: AthleteImport; profile: AthleteProfile }>(`/lab/athlete-imports/${reviewed.id}/profile-confirm`, { payload_hash: reviewed.payload_hash, expected_profile_revision: expectedProfileRevision, fields: selected });
      setExpectedProfileRevision(response.profile.revision); qc.setQueryData(["athlete-profile", uid], response.profile);
      return { kind, reviewed: response.import };
    }
    if (kind === "template") {
      const response = await api.post<{ import: AthleteImport; template: AthleteTemplate }>(`/lab/athlete-imports/${reviewed.id}/template-confirm`, { payload_hash: reviewed.payload_hash });
      setChosenTemplate(response.template); setStartsOn(""); setEndsOn(""); setPreview(null);
      return { kind, reviewed: response.import };
    }
    const draft = await api.post<PlanDraft>(`/lab/athlete-imports/${reviewed.id}/dated-plan`, { payload_hash: reviewed.payload_hash }); setPreview(draft);
    return { kind, reviewed: { ...reviewed, receipts: { ...reviewed.receipts, dated_plan: { draft_id: draft.id } } } };
  }, onSuccess: response => { setCurrent(response.reviewed); setProposal(structuredClone(response.reviewed.proposal)); setMessage("athleteImport.saved_" + response.kind); void invalidate(); } });
  const previewTemplate = useMutation({ mutationFn: () => api.post<PlanDraft>(`/athlete/templates/${chosenTemplate!.id}/preview`, { expected_revision: chosenTemplate!.revision, starts_on: startsOn, ends_on: endsOn }), onSuccess: next => { setPreview(next); activate.reset(); void invalidate(); } });
  const activate = useMutation({ mutationFn: () => api.post<{ draft: PlanDraft }>(`/lab/plan-drafts/${preview!.id}/confirm`, { payload_hash: preview!.payload_hash, ambiguities_reviewed: true }), onSuccess: next => { setPreview(next.draft); setMessage("athleteImport.plan_activated"); void invalidate(); } });
  const pending = preparePdf.isPending || analyze.isPending || action.isPending || previewTemplate.isPending || activate.isPending;
  function errorText(error: Error | null) { return error instanceof ApiError && error.status === 409 ? t("athleteImport.conflict") : error?.message ?? null; }
  const error = localError ?? errorText(preparePdf.error) ?? errorText(analyze.error);
  function chooseTemplate(next: AthleteTemplate, resume = false) {
    const savedDraft = resume ? planDrafts.data?.find(draft => draft.template_id === next.id && draft.template_revision === next.revision && draft.status === "draft") : null;
    setChosenTemplate(next); setStartsOn(savedDraft?.structure.starts_on ?? ""); setEndsOn(savedDraft?.structure.ends_on ?? ""); setPreview(savedDraft ?? null); previewTemplate.reset(); activate.reset();
  }
  useEffect(() => {
    const hash = anchor;
    if (!hash || hash === handledAnchor.current || !profile.data || !planDrafts.data || dirty || entry.start || entry.end) return;
    const templateId = hash.match(/^#template-(\d+)$/)?.[1];
    const documentId = hash.match(/^#document-(\d+)$/)?.[1];
    if (templateId) {
      const template = templates.data?.find(item => item.id === Number(templateId));
      if (!template) return;
      handledAnchor.current = hash; chooseTemplate(template, true);
    } else if (documentId) {
      const item = imports.data?.find(item => item.document_id === Number(documentId));
      if (!item) return;
      handledAnchor.current = hash; open(item);
    } else return;
    requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" }));
  }, [anchor, templates.data, imports.data, planDrafts.data, profile.data]);
  function selectFile(next: File | null) {
    if (pending) return;
    const sequence = ++fileReadSequence.current;
    setLocalError(null); setFile(next); setSource(null); setSourceText(""); preparePdf.reset(); analyze.reset();
    if (!next) return;
    if (!/\.(txt|md|pdf)$/i.test(next.name)) { setLocalError(t("lab.document_wrong_type")); setFile(null); return; }
    if (next.size > 5 * 1024 * 1024) { setLocalError(t("lab.document_too_large")); setFile(null); return; }
    if (/\.pdf$/i.test(next.name)) { preparePdf.mutate(next); return; }
    void next.text().then(text => { if (fileReadSequence.current !== sequence) return; if (text.length > 16000) { setLocalError(t("athleteImport.source_too_long")); setFile(null); } else setSourceText(text); }).catch(() => setLocalError(t("athleteImport.read_error")));
  }
  return <div data-athlete-import className="space-y-6">
    <Card><CardHeader title={<h2>{t("athleteImport.title")}</h2>} /><p className="mb-5 max-w-2xl text-[14px] text-muted">{t("athleteImport.intro")}</p>
      <fieldset disabled={pending} className="space-y-4">
        <label className="flex min-h-24 cursor-pointer flex-col items-center justify-center gap-2 border border-dashed border-hairline2 p-4 text-center focus-within:outline focus-within:outline-2" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); selectFile(e.dataTransfer.files[0] ?? null); }}><span>{source?.filename ?? file?.name ?? t("lab.document_drop")}</span><span className="text-[12px] text-muted">{t("lab.document_rules")}</span><input ref={fileInput} type="file" className="sr-only" accept=".txt,.md,.pdf" aria-label={t("athleteImport.source_file")} onChange={e => selectFile(e.target.files?.[0] ?? null)} /></label>
        {(source?.extraction_state === "manual_paste_required") && <p className="text-[13px] text-muted">{t("athleteImport.pdf_paste")}</p>}
        <label className="flex flex-col gap-2 text-[13px]"><span>{t("athleteImport.source_text")}</span><textarea aria-label={t("athleteImport.source_text")} className="min-h-32 w-full border border-hairline bg-transparent px-3 py-2" value={sourceText} maxLength={16000} onChange={e => setSourceText(e.target.value)} /></label>
        <p className="text-[12px] text-muted">{t("athleteImport.source_scope")}</p>
        {preparePdf.isPending && <p role="status" className="text-[13px]">{t("athleteImport.reading_pdf")}</p>}
        {aiAvailable ? <label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={useAi} onChange={e => setUseAi(e.target.checked)} />{t("athleteImport.ai_assistance")}</label> : <p className="text-[13px] text-muted">{t("athleteImport.manual_available")}</p>}
        <div className="flex flex-wrap gap-3"><Button disabled={pending || !!localError || !sourceText.trim() || profile.isLoading || profile.isError} onClick={() => { if ((dirty || entry.start || entry.end) && !window.confirm(t("athlete.leave_unsaved"))) return; analyze.mutate(); }}>{t(analyze.isPending ? "athleteImport.analyzing" : "athleteImport.analyze")}</Button>{source && <Button variant="ghost" onClick={() => { setSource(null); setFile(null); setSourceText(""); if (fileInput.current) fileInput.current.value = ""; }}>{t("athleteImport.new_source")}</Button>}</div>
      </fieldset>{analyze.isSuccess && <p role="status" className="mt-3 text-[13px]">{t("athleteImport.analyzed")}</p>}{error && <p role="alert" className="mt-3 text-[13px] text-alertText">{error}</p>}
    </Card>
    {(imports.isLoading || templates.isLoading) && <Loading />}
    {(imports.isError || documents.isError || templates.isError || profile.isError) && <p role="alert" className="text-[13px]">{t("athleteImport.load_error")}</p>}
    {(documents.data?.some(doc => doc.coach_eligible === false) || !!imports.data?.length) && <Card><CardHeader title={<h2>{t("athleteImport.import_history")}</h2>} /><div className="space-y-4">{documents.data?.filter(doc => doc.coach_eligible === false).map(doc => {
      const latest = imports.data?.find(item => item.document_id === doc.id);
      return <section id={`document-${doc.id}`} key={doc.id} className="border-t border-hairline pt-3"><h3 className="text-[14px] font-medium">{doc.filename}</h3><p className="mt-1 text-[12px] text-muted">{t(imports.data?.some(item => item.document_id === doc.id && item.receipts.profile) ? "athleteImport.profile_receipt" : latest ? "athleteImport.review_receipt" : "athleteImport.source_receipt")}</p><Button variant="ghost" className="mt-3" disabled={pending} onClick={() => { if (latest) open(latest); else { setSource(doc); setFile(null); setSourceText(doc.excerpt ?? ""); setMessage(null); } }}>{t(latest ? "athleteImport.continue_review" : "athleteImport.analyze_source")}</Button></section>;
    })}{imports.data?.filter(item => !documents.data?.some(doc => doc.id === item.document_id && doc.coach_eligible === false)).map(item => <section key={item.id} className="border-t border-hairline pt-3"><p className="text-[13px]">{documents.data?.find(doc => doc.id === item.document_id)?.filename ?? t("athleteImport.review_title")}</p><Button variant="ghost" disabled={pending} onClick={() => open(item)}>{t("athleteImport.continue_review")}</Button></section>)}</div></Card>}
    {current && proposal && <Card><div ref={reviewRoot} tabIndex={-1} className="outline-none"><CardHeader title={<h2>{t("athleteImport.review_title")}</h2>} right={<Badge>{t(current.extraction_method.startsWith("ai") ? "athleteImport.ai_review" : "athleteImport.manual_review")}</Badge>} />
      <p className="mb-4 text-[13px] text-muted">{t("athleteImport.review_note")}</p>
      {!!current.category_hints?.length && <p className="mb-4 text-[13px]">{t("athleteImport.contains")} {current.category_hints.map(category => t("athleteImport.category_" + category)).join(" · ")}</p>}
      <details className="mb-5"><summary className="cursor-pointer text-[13px]">{t("athleteImport.review_source")}</summary><blockquote className="mt-3 whitespace-pre-wrap break-words text-[13px]">{current.source_text}</blockquote></details>
      <fieldset disabled={pending}><ImportProfileReview proposal={proposal} onChange={edit} selected={selected} onSelected={setSelected} entry={entry} onEntry={setEntry} revision={current.version} /></fieldset>
      <p role="status" className="mt-5 text-[13px] font-medium">{t(action.isPending ? "athleteImport.saving" : dirty ? "athlete.unsaved_changes" : message ?? (current.receipts.profile ? "athleteImport.profile_receipt" : "athleteImport.profile_scope"))}</p>
      {requiredProfileIssues && <p className="mt-2 text-[13px] text-muted">{t("athleteImport.required_profile_note")}</p>}
      {invalidSelection && <p role="alert" className="mt-2 text-[13px]">{t("athleteImport.enter_selected_fields")}</p>}
      <div className="mt-4 flex flex-wrap gap-3"><Button disabled={pending || !selected.length || incompleteAvailability || invalidSelection || !!requiredProfileIssues || expectedProfileRevision === null} onClick={() => action.mutate("profile")}>{t("athleteImport.save_profile")}</Button><Button variant="ghost" disabled={pending || incompleteAvailability} onClick={() => action.mutate("review")}>{t("athleteImport.save_review")}</Button><Button variant="ghost" disabled={pending} onClick={() => setPlanOpen(!planOpen)}>{t("athleteImport.review_plan")}</Button></div>
      {current.receipts.profile && <Link to="/app/settings?tab=profile" className="mt-3 inline-block text-link">{t("athleteImport.view_profile")}</Link>}
      {planOpen && <section className="mt-6 space-y-4 border-t border-hairline pt-5"><fieldset disabled={pending}><ImportPlanReview proposal={proposal} onChange={edit} /></fieldset><div className="flex flex-wrap gap-3">
        {proposal.weekly && <Button disabled={pending || incompleteAvailability || !proposal.weekly.rows.length || proposal.weekly.rows.some(row => !row.discipline) || !!requiredWeeklyIssues} onClick={() => action.mutate("template")}>{t("athleteImport.save_template")}</Button>}
        {proposal.dated && <Button variant="ghost" disabled={pending || incompleteAvailability || !proposal.dated.starts_on || !proposal.dated.ends_on || !proposal.dated.sessions.length || proposal.dated.sessions.some(row => !row.date || !row.discipline) || !!proposal.dated.ambiguities.length || !!requiredDatedIssues} onClick={() => { setChosenTemplate(null); action.mutate("dated"); }}>{t("athleteImport.preview_dated")}</Button>}
      </div></section>}
      {!!proposal.issues.filter(issue => !/^(profile\.)?(training_focus|context\.)/.test(issue.field) && !/^(weekly|dated)(\.|$)/.test(issue.field)).length && <section className="mt-5 space-y-3"><h3>{t("athlete.ambiguities")}</h3>{proposal.issues.filter(issue => !/^(profile\.)?(training_focus|context\.)/.test(issue.field) && !/^(weekly|dated)(\.|$)/.test(issue.field)).map(issue => <ImportEvidence key={issue.field} field={issue.field} proposal={proposal} onResolve={(field, defer) => { if (!defer || !issue.required) edit({ ...proposal, issues: proposal.issues.filter(old => old.field !== field) }); }} />)}</section>}
      {action.isError && <p role="alert" className="mt-4 text-[13px] text-alertText">{errorText(action.error)}</p>}
    </div></Card>}
    {!!templates.data?.length && <Card><CardHeader title={<h2>{t("athleteImport.saved_templates")}</h2>} /><p className="mb-4 text-[13px] text-muted">{t("athleteImport.template_scope")}</p><div className="space-y-3">{templates.data.map(template => <div id={`template-${template.id}`} key={template.id} className="border-t border-hairline pt-3"><h3 className="text-[14px] font-medium">{template.structure.title || t("athlete.untitled_plan")}</h3><Button variant="ghost" disabled={pending} onClick={() => chooseTemplate(template)}>{t("athleteImport.choose_dates")}</Button>{planDrafts.data?.some(draft => draft.template_id === template.id && draft.template_revision === template.revision && draft.status === "draft") && <Button variant="ghost" disabled={pending} onClick={() => chooseTemplate(template, true)}>{t("athleteImport.resume_calendar")}</Button>}</div>)}</div></Card>}
    {chosenTemplate && <Card><CardHeader title={chosenTemplate.structure.title || t("athleteImport.weekly_template")} /><p className="mb-4 text-[13px] text-muted">{t("athleteImport.explicit_dates_note")}</p><div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.event_start")} type="date" value={startsOn} onChange={v => { setStartsOn(v); setPreview(null); }} /><Input label={t("athlete.event_end")} type="date" value={endsOn} onChange={v => { setEndsOn(v); setPreview(null); }} /></div><Button className="mt-4" disabled={pending || !startsOn || !endsOn || endsOn < startsOn || (Date.parse(endsOn) - Date.parse(startsOn)) / 86400000 > 366} onClick={() => previewTemplate.mutate()}>{t("athleteImport.preview_calendar")}</Button>{previewTemplate.isError && <p role="alert" className="mt-3 text-[13px] text-alertText">{errorText(previewTemplate.error)}</p>}</Card>}
    {preview && <Card><CalendarPreview draft={preview} pending={activate.isPending} error={errorText(activate.error)} onActivate={() => activate.mutate()} /></Card>}
  </div>;
}
