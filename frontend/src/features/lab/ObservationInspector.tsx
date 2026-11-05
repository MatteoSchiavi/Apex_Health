import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { Button, Loading } from "../../components/kit";
import { ReadError } from "../../components/ReadError";
import { Field, Form, str, useAction, useToday, Value } from "./shared";
import type { Observation } from "./types";

function observationId(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const match = value.match(/^observation:(\d+):\d+$/);
  const id = match ? Number(match[1]) : null;
  return id != null && Number.isSafeInteger(id) && id > 0 ? id : null;
}

function EvidenceEditor({ evidence, onState }: {
  evidence: Record<string, unknown>;
  onState: (dirty: boolean, saving: boolean) => void;
}) {
  const { t } = useTranslation();
  const today = useToday();
  const save = useAction();
  const [dirty, setDirty] = useState(false);
  useEffect(() => onState(dirty, save.isPending), [dirty, save.isPending, onState]);
  return <details open className="mt-4 text-[12px]">
    <summary>{t("lab.provenance")}</summary>
    <div className="mt-4"><Value value={evidence} /></div>
    <Form pending={save.isPending} error={save.error} label={t("lab.annotate")}
      onChange={() => { setDirty(true); save.reset(); }}
      onSave={fields => save.mutate({ path: "/lab/entries", body: { entry: {
        kind: "observation_annotation", date: today, observation_id: observationId(evidence.id),
        exclude_from_analysis: fields.get("exclude") === "on", notes: str(fields, "reason"),
      } } }, { onSuccess: () => setDirty(false) })}>
      <label className="mt-4 flex gap-2"><input type="checkbox" name="exclude" defaultChecked />{t("lab.exclude_analysis")}</label>
      <Field name="reason" label={t("lab.reason")} required />
    </Form>
    {save.isSuccess && <p role="status" className="mt-3 text-muted">{t("dataRecovery.annotation_saved")}</p>}
  </details>;
}

type Selection = {
  observation: Observation;
  version: number;
  loading: boolean;
  error: boolean;
  evidence: Record<string, unknown> | null;
};

function InspectorPanel({ selection, saving, retry, close, onState }: {
  selection: Selection; saving: boolean;
  retry: () => void; close: () => void;
  onState: (dirty: boolean, saving: boolean) => void;
}) {
  const { t } = useTranslation();
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    panel.current?.focus({ preventScroll: true });
    panel.current?.scrollIntoView({ block: "nearest" });
  }, []);
  return <section ref={panel} tabIndex={-1} aria-label={t("dataRecovery.selected_evidence")} className="mt-5 min-w-0 border-t border-hairline pt-4 outline-none">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-[13px] font-medium">{t("lab.metrics." + selection.observation.metric, { defaultValue: selection.observation.metric.replaceAll("_", " ") })} · {selection.observation.local_date}</p>
      <Button variant="ghost" disabled={saving} onClick={close}>{t("common.close")}</Button>
    </div>
    {selection.loading ? <Loading /> : selection.error ? <ReadError label={t("dataRecovery.retry_evidence")} pending={false} retry={retry} />
      : selection.evidence && <EvidenceEditor evidence={selection.evidence} onState={onState} />}
  </section>;
}

/** Inspect and annotate one canonical observation; late reads cannot change the target. */
export function useObservationInspector() {
  const { t } = useTranslation();
  const uid = useUi(state => state.me?.user_id);
  const sequence = useRef(0);
  const opener = useRef<HTMLElement | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [form, setForm] = useState({ dirty: false, saving: false });
  const onState = useCallback((dirty: boolean, saving: boolean) => setForm({ dirty, saving }), []);
  function canReplace() {
    return !form.saving && (!form.dirty || window.confirm(t("dataRecovery.discard_annotation")));
  }
  async function inspect(observation: Observation, button?: HTMLElement) {
    if (!canReplace()) return;
    const request = ++sequence.current;
    if (button) opener.current = button;
    setForm({ dirty: false, saving: false });
    setSelection({ observation, version: request, loading: true, error: false, evidence: null });
    try {
      const id = observationId(observation.id);
      if (id == null) throw new Error("Invalid observation identity");
      const evidence = await api.get<Record<string, unknown>>(`/lab/evidence/${id}`);
      if (observationId(evidence.id) !== id) throw new Error("Observation identity mismatch");
      if (sequence.current === request && useUi.getState().me?.user_id === uid)
        setSelection({ observation, version: request, loading: false, error: false, evidence });
    } catch {
      if (sequence.current === request && useUi.getState().me?.user_id === uid)
        setSelection({ observation, version: request, loading: false, error: true, evidence: null });
    }
  }
  function clear() {
    sequence.current++;
    setSelection(null);
    setForm({ dirty: false, saving: false });
    if (opener.current?.isConnected) opener.current.focus();
  }
  return {
    inspect,
    saving: form.saving,
    clearSource: (source: string) => { if (selection?.observation.origin === source) clear(); },
    panel: selection && <InspectorPanel key={selection.version} selection={selection} saving={form.saving}
      retry={() => void inspect(selection.observation)} close={() => { if (canReplace()) clear(); }} onState={onState} />,
  };
}
