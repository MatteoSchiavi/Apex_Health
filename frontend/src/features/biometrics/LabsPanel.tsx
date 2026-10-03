import { useState, type FormEvent } from "react";
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
}
const MARKERS = [
  { key: "hemoglobin", unit: "g/dL" },
  { key: "hematocrit", unit: "%" },
  { key: "ferritin", unit: "ng/mL" },
  { key: "iron", unit: "" },
  { key: "wbc", unit: "" },
  { key: "plt", unit: "" },
] as const;
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
    mutationFn: () =>
      api.post("/labs", {
        panel_date: date,
        panel_type: type,
        notes: notes || null,
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
      <div className="flex items-center justify-between gap-4">
        <p className="text-[13px] text-muted">{t("design.lab_note")}</p>
        <Button variant="ghost" onClick={() => setAdding((v) => !v)}>
          {t(adding ? "common.cancel" : "design.add_panel")}
        </Button>
      </div>
      {adding && (
        <Card>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              save.mutate();
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
