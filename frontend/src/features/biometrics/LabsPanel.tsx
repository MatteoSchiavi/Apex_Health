import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import {
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorNote,
  Input,
  Loading,
  fmtNum,
} from "../../components/kit";
import { localDay } from "../../components/data";
import { useUi } from "../../app/stores/ui";
import { LabReferenceRanges, LabReferenceInterval, readLabReferenceRanges } from "../../components/LabReferenceRanges";
interface Panel {
  id: number;
  panel_date: string;
  panel_type: string;
  hemoglobin: number | null;
  hematocrit: number | null;
  ferritin: number | null;
  iron: number | null;
  wbc: number | null;
  plt: number | null;
  donation_type: string | null;
  next_eligible_date: string | null;
  source: string | null;
  notes: string | null;
  markers?: { marker: string; value: number | null; unit: string | null; ref_low: number | null; ref_high: number | null }[];
}
const MARKERS = [
  { key: "hemoglobin", unit: "g/dL" },
  { key: "hematocrit", unit: "%" },
  { key: "ferritin", unit: "ng/mL" },
  { key: "iron", unit: "µg/dL" },
  { key: "wbc", unit: "10³/µL" },
  { key: "plt", unit: "10³/µL" },
] as const;

interface LabFile {
  id: number;
  filename: string;
  media_type: string;
  content_hash: string;
  status: string;
  created_at: string;
}

function LabFiles() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useUi((s) => s.me?.user_id);
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const files = useQuery({
    queryKey: ["lab-files", uid],
    queryFn: () => api.get<LabFile[]>("/lab/documents"),
  });
  const upload = useMutation({
    mutationFn: (selected: File) => {
      const body = new FormData();
      body.append("file", selected);
      return api.post<LabFile>("/lab/documents", body);
    },
    onSuccess: () => {
      setFile(null);
      if (input.current) input.current.value = "";
      qc.invalidateQueries({ queryKey: ["lab-files", uid] });
      qc.invalidateQueries({ queryKey: ["lab"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/lab/documents/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lab-files", uid] });
      qc.invalidateQueries({ queryKey: ["lab"] });
    },
  });
  return (
    <Card>
      <CardHeader title={t("nutrition.lab_files_title")} />
      <p className="mb-4 text-[13px] text-muted">{t("nutrition.lab_files_note")}</p>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (file) upload.mutate(file);
        }}
      >
        <label className="flex flex-col gap-2 text-[12px] text-muted">
          {t("nutrition.choose_file")}
          <input
            ref={input}
            type="file"
            accept=".txt,.md,.pdf"
            required
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="max-w-full text-[13px] text-ink"
          />
        </label>
        <Button type="submit" disabled={!file || upload.isPending}>
          {t("nutrition.upload_file")}
        </Button>
      </form>
      {upload.isError && <p role="alert" className="mt-3 text-[13px] text-red-600">{upload.error.message}</p>}
      {remove.isError && <p role="alert" className="mt-3 text-[13px] text-red-600">{remove.error.message}</p>}
      <div className="mt-5 border-t border-hairline">
        {files.isLoading ? <Loading /> : files.isError ? <ErrorNote /> : !files.data?.length ? (
          <Empty>{t("nutrition.no_lab_files")}</Empty>
        ) : files.data.map((item) => (
          <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline py-3 text-[13px]">
            <div className="min-w-0">
              <p className="break-all font-medium">{item.filename}</p>
              <p className="text-[12px] text-muted">{new Date(item.created_at).toLocaleDateString()} · {item.media_type}</p>
            </div>
            <div className="flex items-center gap-3">
              <a className="text-link" href={`/lab/documents/${item.id}/original`} download>
                {t("nutrition.download_file")}
              </a>
              <Button variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(item.id)}>
                {t("training.delete")}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
export function LabsPanel() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [date, setDate] = useState(localDay());
  const [type, setType] = useState("");
  const [notes, setNotes] = useState("");
  const [markers, setMarkers] = useState<Record<string, string>>({});
  const list = useQuery({
    queryKey: ["labs"],
    queryFn: () => api.get<Panel[]>("/labs"),
  });
  const save = useMutation({
    mutationFn: (form: FormData) =>
      api.post("/labs", {
        panel_date: date,
        panel_type: type,
        notes: notes || null,
        reference_ranges: readLabReferenceRanges(form),
        ...Object.fromEntries(
          MARKERS.map((m) => [
            m.key,
            markers[m.key] ? Number(markers[m.key]) : null,
          ]),
        ),
      }),
    onSuccess: () => {
      setAdding(false);
      setMarkers({});
      setType("");
      setNotes("");
      qc.invalidateQueries({ queryKey: ["labs"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
  return (
    <div className="flex flex-col gap-6">
      <LabFiles />
      <div className="flex items-center justify-between gap-4">
        <p className="text-[13px] text-muted">{t("design.lab_note")}</p>
        <Button variant="ghost" onClick={() => setAdding((v) => !v)}>
          {t(adding ? "common.cancel" : "design.add_panel")}
        </Button>
      </div>
      {adding && (
        <Card>
          <form
            onSubmit={(e: FormEvent<HTMLFormElement>) => {
              e.preventDefault();
              save.mutate(new FormData(e.currentTarget));
            }}
            className="grid gap-4 md:grid-cols-2"
          >
            <Input
              label={t("training.event_date")}
              type="date"
              value={date}
              onChange={setDate}
              required
            />
            <Input
              label={t("design.panel_type")}
              value={type}
              onChange={setType}
              required
            />
            {MARKERS.map((m) => (
              <Input
                key={m.key}
                label={
                  t("design.lab_" + m.key) + (m.unit ? " · " + m.unit : "")
                }
                type="number"
                min={0}
                step={0.01}
                value={markers[m.key] ?? ""}
                onChange={(v) =>
                  setMarkers((prev) => ({ ...prev, [m.key]: v }))
                }
              />
            ))}
            <Input
              label={t("training.notes")}
              value={notes}
              onChange={setNotes}
              className="md:col-span-2"
            />
            <LabReferenceRanges />
            <div className="md:col-span-2">
              <Button type="submit" disabled={save.isPending}>
                {t("common.save")}
              </Button>
              {save.isError && <ErrorNote />}
            </div>
          </form>
        </Card>
      )}
      {list.isLoading ? (
        <Loading />
      ) : list.isError ? (
        <ErrorNote />
      ) : !list.data?.length ? (
        <Card>
          <Empty>{t("design.no_labs")}</Empty>
        </Card>
      ) : (
        list.data.map((panel) => (
          <Card key={panel.id}>
            <CardHeader
              title={panel.panel_type}
              right={
                <span className="text-[13px] text-muted">
                  {panel.panel_date}
                </span>
              }
            />
            <div className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3">
              {MARKERS.map((m) => (
                <div key={m.key} className="border-t border-hairline pt-4">
                  <p className="text-[13px] text-muted">
                    {t("design.lab_" + m.key)}
                  </p>
                  <p className="num mt-2 text-[24px]">
                    {fmtNum(panel[m.key], 1)}
                    <span className="ml-2 text-[12px] text-muted">
                      {m.unit}
                    </span>
                  </p>
                  {panel.markers?.filter(marker => marker.marker === m.key).map((marker, i) =>
                    <LabReferenceInterval key={i} low={marker.ref_low} high={marker.ref_high} unit={marker.unit} />)}
                </div>
              ))}
            </div>
            {(panel.donation_type || panel.next_eligible_date) && (
              <p className="mt-5 text-[13px] text-muted">
                {panel.donation_type}{" "}
                {panel.next_eligible_date &&
                  t("design.next_donation", { date: panel.next_eligible_date })}
              </p>
            )}
            {panel.notes && (
              <p className="mt-5 border-t border-hairline pt-4 text-[13px] whitespace-pre-wrap">
                {panel.notes}
              </p>
            )}
            {panel.source && (
              <p className="mt-4 text-[12px] text-muted">
                {t("activities.sources")}: {panel.source}
              </p>
            )}
          </Card>
        ))
      )}
    </div>
  );
}
