"use client";

/**
 * Apex Health — Documents page.
 *
 * The page's job: upload any health/performance document (lab tests, medical
 * reports, training plans, dietary plans, prescriptions, blood work) and have
 * the AI extract structured data from it.
 *
 * Re-skinned per ui-language/RULES.md (9 principles):
 *   1. One answer: the upload dropzone is the hero.
 *   2. Hero is 2× anything else.
 *   3. No outlines on cards (the dashed dropzone border is an input affordance).
 *   4. Sentence-case labels, 13px minimum.
 *   5. Numbers stay white; status = dot + word (StatusDot).
 *   6. Accent (orange) for the upload affordance + actions.
 *   7. Plain words ("Documents", not "DOCUMENTS").
 *   8. Charts: n/a on this page.
 *   9. Document list is rows, not one card per doc. Parsed data is flat
 *      sections, no nested bordered tiles.
 *
 * Supported file types: PDF, JPG, PNG, TXT, CSV (max 10MB).
 * PDFs are parsed via pdf-parse → text → LLM; images via VLM.
 */

import { Fragment, useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import {
  FileText,
  Image as ImageIcon,
  Upload,
  Trash2,
  Sparkles,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  Loader2,
  FlaskConical,
  Dumbbell,
  Utensils,
  Pill,
  ClipboardList,
  Droplet,
  File as FileIcon,
} from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import {
  ApexButton,
  Card,
  ConfirmPopover,
  Empty,
  ErrorNote,
  Loading,
  PageSentence,
  Section,
  StatusDot,
  rangeTone,
} from "@/components/apex/kit";
import { useToast } from "@/hooks/use-toast";
import type { DocCategory, ParsedDocument, UploadedDocument } from "@/lib/apex/types";

const CATEGORIES: { value: DocCategory; labelKey: string; icon: typeof FlaskConical }[] = [
  { value: "lab_test", labelKey: "documents.cat_lab_test", icon: FlaskConical },
  { value: "blood_work", labelKey: "documents.cat_blood_work", icon: Droplet },
  { value: "medical_report", labelKey: "documents.cat_medical_report", icon: ClipboardList },
  { value: "training_plan", labelKey: "documents.cat_training_plan", icon: Dumbbell },
  { value: "dietary_plan", labelKey: "documents.cat_dietary_plan", icon: Utensils },
  { value: "prescription", labelKey: "documents.cat_prescription", icon: Pill },
  { value: "other", labelKey: "documents.cat_other", icon: FileText },
];

function fileIcon(type: string) {
  if (["jpg", "jpeg", "png"].includes(type)) return ImageIcon;
  if (type === "pdf") return FileText;
  return FileIcon;
}

function statusDotFor(
  status: string,
  t: (p: string) => string,
): { tone: "neutral" | "ok" | "watch" | "alert"; label: string } {
  switch (status) {
    case "pending": return { tone: "neutral", label: t("documents.status_pending") };
    case "parsing": return { tone: "watch", label: t("documents.status_parsing") };
    case "parsed":  return { tone: "ok", label: t("documents.status_parsed") };
    case "error":   return { tone: "alert", label: t("documents.status_error") };
    default:        return { tone: "neutral", label: status };
  }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentsPage() {
  const t = useT();
  const { toast } = useToast();
  const [docs, setDocs] = useState<UploadedDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<DocCategory>("lab_test");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [parsingId, setParsingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/upload", { cache: "no-store" });
      const j = await r.json();
      if (j?.ok) {
        setDocs(
          j.documents.map((d: Record<string, unknown>) => ({
            id: d.id as number,
            fileName: d.fileName as string,
            fileType: d.fileType as string,
            fileSize: d.fileSize as number,
            category: (d.category as DocCategory) || "other",
            source: (d.source as string) || "manual",
            status: d.status as UploadedDocument["status"],
            parsedData: d.parsedData ? (JSON.parse(d.parsedData as string) as ParsedDocument) : null,
            uploadedAt: d.uploadedAt as string,
          })),
        );
      } else {
        setError(j?.error || "Failed to load");
      }
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (expandedId !== null && !docs.some((d) => d.id === expandedId)) {
      setExpandedId(null);
    }
  }, [docs, expandedId]);

  const uploadFile = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("category", category);
        const r = await fetch("/api/upload", { method: "POST", body: fd });
        const j = await r.json();
        if (j?.ok) {
          toast({ title: `Uploaded ${file.name}`, description: t("documents.status_pending") });
          await refresh();
          if (j.documentId) {
            parseDocument(j.documentId);
          }
        } else {
          setError(j?.error || "Upload failed");
          toast({ title: "Upload failed", description: j?.error, variant: "destructive" });
        }
      } catch {
        setError("Network error during upload");
        toast({ title: "Upload failed", description: "Network error", variant: "destructive" });
      } finally {
        setUploading(false);
      }
    },
    [category, refresh, toast, t],
  );

  const parseDocument = useCallback(
    async (id: number) => {
      setParsingId(id);
      try {
        const r = await fetch("/api/parse-document", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ documentId: id }),
        });
        const j = await r.json();
        if (j?.ok) {
          toast({ title: "Document parsed", description: "Structured data extracted" });
          await refresh();
          setExpandedId(id);
        } else {
          toast({ title: "Parsing failed", description: j?.error, variant: "destructive" });
          await refresh();
        }
      } catch {
        toast({ title: "Parsing failed", description: "Network error", variant: "destructive" });
      } finally {
        setParsingId(null);
      }
    },
    [refresh, toast],
  );

  const deleteDoc = useCallback(
    async (id: number) => {
      try {
        const r = await fetch(`/api/upload?id=${id}`, { method: "DELETE" });
        const j = await r.json();
        if (j?.ok) {
          toast({ title: "Document deleted" });
          await refresh();
        } else {
          toast({ title: "Delete failed", description: j?.error, variant: "destructive" });
        }
      } catch {
        toast({ title: "Delete failed", description: "Network error", variant: "destructive" });
      }
    },
    [refresh, toast],
  );

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadFile(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    e.target.value = "";
  };

  return (
    <div className="mx-auto max-w-[1100px] space-y-8 px-6 py-8">
      {/* ===== Title + page sentence ===== */}
      <div>
        <h1 className="page-title">Documents</h1>
        <PageSentence className="mt-2">
          Upload any health or performance document — the AI reads it and extracts the
          markers, sessions, meals, or medications inside.
        </PageSentence>
      </div>

      {/* ===== Hero — Upload dropzone + category selector (borderless card) ===== */}
      <Card>
        <Section label={t("documents.select_category")}>
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map((c) => {
              const Icon = c.icon;
              const active = category === c.value;
              return (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setCategory(c.value)}
                  className={`num inline-flex items-center gap-1.5 rounded-[var(--radius-control)] px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
                    active
                      ? "bg-surface2 text-ink"
                      : "text-ink2 hover:bg-surface2 hover:text-ink"
                  }`}
                  aria-pressed={active}
                >
                  <Icon size={14} />
                  {t(c.labelKey)}
                </button>
              );
            })}
          </div>
        </Section>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`mt-4 cursor-pointer rounded-[var(--radius-card)] border-2 border-dashed px-6 py-12 text-center transition-colors ${
            dragging
              ? "border-primary bg-primarySoft/30"
              : "border-hairline2 hover:border-hairline hover:bg-surface2"
          }`}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.jpg,.jpeg,.png,.txt,.csv"
            onChange={onFileChange}
          />
          {uploading ? (
            <div className="flex flex-col items-center gap-3">
              <Loader2 size={32} className="animate-spin text-primaryText" />
              <div className="text-[14px] font-semibold text-ink2">{t("documents.uploading")}</div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primarySoft text-primaryText">
                <Upload size={26} />
              </div>
              <div className="text-[16px] font-semibold text-ink">{t("documents.drop_title")}</div>
              <div className="max-w-md text-[14px] text-ink2">{t("documents.drop_body")}</div>
              <ApexButton
                variant="secondary"
                size="sm"
                icon={<FileText size={13} />}
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
                className="mt-1"
              >
                {t("documents.browse")}
              </ApexButton>
              <div className="num text-[13px] text-ink2">{t("documents.supported_types")}</div>
            </div>
          )}
        </div>
      </Card>

      {/* ===== Document list — rows, not cards ===== */}
      {loading ? (
        <Card>
          <Loading label="Loading documents…" />
        </Card>
      ) : error ? (
        <ErrorNote message={error} onRetry={refresh} />
      ) : docs.length === 0 ? (
        <Empty title={t("documents.no_documents")} body={t("documents.no_documents_body")} />
      ) : (
        <Card pad={false}>
          <div className="p-6 pb-3">
            <div className="text-[14px] font-medium text-ink2">Your documents</div>
          </div>
          <div className="px-7">
            <div className="divide-y divide-[var(--c-divider)]">
              {docs.map((doc) => {
                const Icon = fileIcon(doc.fileType);
                const isParsing = parsingId === doc.id;
                const isExpanded = expandedId === doc.id;
                const cat = CATEGORIES.find((c) => c.value === doc.category);
                const CatIcon = cat?.icon || FileText;
                const dot = statusDotFor(doc.status, t);
                return (
                  <Fragment key={doc.id}>
                    {/* Row: icon · name · category · status · actions */}
                    <div className="flex items-center gap-3 py-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-surface2 text-ink2">
                        <Icon size={16} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[14px] font-semibold text-ink">{doc.fileName}</div>
                        <div className="num mt-0.5 flex items-center gap-2 text-[13px] text-ink2">
                          <span className="inline-flex items-center gap-1">
                            <CatIcon size={11} /> {cat ? t(cat.labelKey) : doc.category}
                          </span>
                          <span className="text-faint">·</span>
                          <span>{doc.fileType.toUpperCase()}</span>
                          <span className="text-faint">·</span>
                          <span>{fmtSize(doc.fileSize)}</span>
                          <span className="text-faint">·</span>
                          <span>{new Date(doc.uploadedAt).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <div className="shrink-0">
                        <StatusDot tone={dot.tone} label={dot.label} />
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        {doc.status === "pending" && (
                          <ApexButton
                            variant="secondary"
                            size="sm"
                            icon={isParsing ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                            onClick={() => parseDocument(doc.id)}
                            disabled={isParsing}
                          >
                            {t("documents.parse")}
                          </ApexButton>
                        )}
                        {doc.status === "parsed" && (
                          <ApexButton
                            variant="ghost"
                            size="sm"
                            icon={isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            onClick={() => setExpandedId(isExpanded ? null : doc.id)}
                          >
                            {isExpanded ? t("documents.hide") : t("documents.view_parsed")}
                          </ApexButton>
                        )}
                        {doc.status === "error" && (
                          <ApexButton
                            variant="ghost"
                            size="sm"
                            icon={<Sparkles size={12} />}
                            onClick={() => parseDocument(doc.id)}
                            disabled={isParsing}
                          >
                            {t("documents.re_parse")}
                          </ApexButton>
                        )}
                        <ConfirmPopover
                          message={t("documents.delete_confirm")}
                          onConfirm={() => deleteDoc(doc.id)}
                          onCancel={() => {}}
                          confirmLabel={t("documents.delete")}
                          cancelLabel="Cancel"
                        >
                          <button
                            type="button"
                            className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-control)] text-faint transition-colors hover:bg-alertSoft hover:text-alertText"
                            aria-label={t("documents.delete")}
                          >
                            <Trash2 size={14} />
                          </button>
                        </ConfirmPopover>
                      </div>
                    </div>

                    {/* Inline error message */}
                    {doc.status === "error" && doc.parsedData?.error && (
                      <div className="flex items-start gap-2 pb-3 text-[13px] text-alertText">
                        <AlertCircle size={14} className="mt-0.5 shrink-0" />
                        <span>{doc.parsedData.error}</span>
                      </div>
                    )}

                    {/* Inline parsed data viewer (flat sections, no nested bordered tiles) */}
                    {isExpanded && doc.status === "parsed" && (
                      <div className="pb-4">
                        <ParsedDataView doc={doc} t={t} />
                      </div>
                    )}
                  </Fragment>
                );
              })}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Parsed data viewer */

function ParsedDataView({
  doc,
  t,
}: {
  doc: UploadedDocument;
  t: (p: string) => string;
}) {
  const data = doc.parsedData;
  if (!data) return null;

  if (data.error) {
    return (
      <div className="text-[14px] text-alertText">
        <AlertCircle size={14} className="mr-1.5 inline" />
        {data.error}
      </div>
    );
  }

  if (data.raw_extraction && !data.document_type) {
    return (
      <div>
        <div className="mb-1 text-[13px] text-ink2">{t("documents.no_extractable_data")}</div>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-[13px] text-ink2">{data.raw_extraction}</pre>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Document type + date */}
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink2">
        <StatusDot tone="neutral" label={data.document_type?.replace(/_/g, " ") ?? "Document"} />
        {data.date && <span>· {data.date}</span>}
        {data.date_range && (
          <span>
            · {data.date_range.start} → {data.date_range.end}
          </span>
        )}
      </div>

      {/* Lab results / biometric report — markers table */}
      {data.markers && data.markers.length > 0 && (
        <ParsedSection title={t("documents.parsed_markers")}>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-hairline text-left text-ink2">
                  <th className="py-1.5 pr-3 font-medium">Marker</th>
                  <th className="py-1.5 pr-3 font-medium">Value</th>
                  <th className="py-1.5 pr-3 font-medium">Unit</th>
                  <th className="py-1.5 pr-3 font-medium">Ref</th>
                  <th className="py-1.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.markers.map((m, i) => {
                  const tone = rangeTone(m.value, m.ref_low, m.ref_high);
                  const dotTone =
                    tone === "positive" ? "ok" : tone === "warning" ? "watch" : tone === "alert" ? "alert" : "neutral";
                  const statusLabel =
                    m.status === "normal" ? "In range" : m.status === "low" ? "Low" : m.status === "high" ? "High" : "—";
                  return (
                    <tr key={i} className="border-b border-hairline/50">
                      <td className="py-1.5 pr-3 font-medium text-ink">{m.name}</td>
                      <td className="num py-1.5 pr-3 text-ink">{m.value ?? "—"}</td>
                      <td className="num py-1.5 pr-3 text-ink2">{m.unit || "—"}</td>
                      <td className="num py-1.5 pr-3 text-ink2">
                        {m.ref_low ?? "—"}–{m.ref_high ?? "—"}
                      </td>
                      <td className="py-1.5">
                        <StatusDot tone={dotTone} label={statusLabel} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </ParsedSection>
      )}

      {/* Medical report — findings */}
      {data.findings && data.findings.length > 0 && (
        <ParsedSection title={t("documents.parsed_findings")}>
          <ul className="space-y-1.5">
            {data.findings.map((f, i) => {
              const dotTone =
                f.severity === "alert" ? "alert" : f.severity === "warning" ? "watch" : "ok";
              return (
                <li key={i} className="flex items-start gap-2">
                  <StatusDot tone={dotTone} label={f.category} />
                  <span className="text-[14px] text-ink2">{f.detail}</span>
                </li>
              );
            })}
          </ul>
        </ParsedSection>
      )}

      {/* Training plan — sessions */}
      {data.sessions && data.sessions.length > 0 && (
        <ParsedSection title={t("documents.parsed_sessions")}>
          <ul className="space-y-1">
            {data.sessions.map((s, i) => (
              <li key={i} className="flex items-center gap-2 text-[13px]">
                <span className="num w-20 shrink-0 text-ink2">{s.day}</span>
                <span className="w-20 shrink-0 font-medium text-ink">{s.discipline}</span>
                <span className="num w-16 shrink-0 text-ink2">{s.duration_min ? `${s.duration_min}m` : "—"}</span>
                <span className="w-20 shrink-0 text-ink2">{s.intensity || "—"}</span>
                <span className="min-w-0 flex-1 truncate text-ink2">{s.title || s.notes}</span>
              </li>
            ))}
          </ul>
        </ParsedSection>
      )}

      {/* Dietary plan — targets + meals */}
      {data.daily_targets && (
        <ParsedSection title={t("documents.parsed_targets")}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            <TargetStat label="Calories" value={data.daily_targets.calories} unit="kcal" />
            <TargetStat label="Protein" value={data.daily_targets.protein_g} unit="g" />
            <TargetStat label="Carbs" value={data.daily_targets.carbs_g} unit="g" />
            <TargetStat label="Fat" value={data.daily_targets.fat_g} unit="g" />
            <TargetStat label="Water" value={data.daily_targets.water_ml} unit="ml" />
          </div>
        </ParsedSection>
      )}
      {data.meals && data.meals.length > 0 && (
        <ParsedSection title={t("documents.parsed_meals")}>
          <ul className="space-y-1">
            {data.meals.map((m, i) => (
              <li key={i} className="text-[13px]">
                <span className="font-medium text-ink">{m.name}</span>
                <span className="mx-1.5 text-faint">·</span>
                <span className="num text-ink2">{m.calories ? `${m.calories} kcal` : "—"}</span>
                {m.foods.length > 0 && <span className="ml-1.5 text-ink2">— {m.foods.join(", ")}</span>}
              </li>
            ))}
          </ul>
        </ParsedSection>
      )}

      {/* Prescription — medications */}
      {data.medications && data.medications.length > 0 && (
        <ParsedSection title={t("documents.parsed_medications")}>
          <ul className="space-y-1">
            {data.medications.map((m, i) => (
              <li key={i} className="text-[13px]">
                <span className="font-medium text-ink">{m.name}</span>
                <span className="mx-1.5 text-faint">·</span>
                <span className="text-ink2">{m.dosage}</span>
                <span className="mx-1.5 text-faint">·</span>
                <span className="text-ink2">{m.frequency}</span>
                {m.duration && (
                  <>
                    <span className="mx-1.5 text-faint">·</span>
                    <span className="text-ink2">{m.duration}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </ParsedSection>
      )}

      {/* Recommendations */}
      {data.recommendations && data.recommendations.length > 0 && (
        <ParsedSection title="Recommendations">
          <ul className="list-disc space-y-1 pl-5 text-[14px] text-ink2">
            {data.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </ParsedSection>
      )}

      {/* Notes */}
      {data.notes && (
        <ParsedSection title={t("documents.parsed_notes")}>
          <p className="text-[14px] text-ink2">{data.notes}</p>
        </ParsedSection>
      )}
    </div>
  );
}

/** A local section used inside the parsed-data viewer. Sentence-case 14px
 *  label, no border, no eyebrow. (The kit's Section would work too, but this
 *  keeps the parsed-data block self-contained.) */
function ParsedSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-[14px] font-medium text-ink2">{title}</div>
      {children}
    </div>
  );
}

function TargetStat({ label, value, unit }: { label: string; value: number | null; unit: string }) {
  return (
    <div>
      <div className="text-[13px] text-ink2">{label}</div>
      <div className="num mt-0.5 text-[18px] font-semibold text-ink">
        {value ?? "—"}
        {value !== null && <span className="ml-1 text-[12px] font-medium text-ink2">{unit}</span>}
      </div>
    </div>
  );
}
