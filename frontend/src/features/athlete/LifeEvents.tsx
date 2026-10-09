import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../../app/api";
import { useUi } from "../../app/stores/ui";
import { localDay } from "../../components/data";
import { Button, Card, CardHeader, ErrorNote, Input, Select } from "../../components/kit";

interface LifeEvent { id: number; kind: string; starts_on: string; ends_on: string; note: string; available_minutes_per_day: number | null }
export function LifeEvents() {
  const { t } = useTranslation();
  const uid = useUi(s => s.me?.user_id);
  const today = localDay(useUi(s => s.me?.timezone));
  const qc = useQueryClient();
  const [kind, setKind] = useState("travel");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [minutes, setMinutes] = useState("");
  const [note, setNote] = useState("");
  const query = useQuery({ queryKey: ["athlete-life", uid], queryFn: () => api.get<LifeEvent[]>("/athlete/life-events") });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["athlete-life"] }); qc.invalidateQueries({ queryKey: ["lab"] }); };
  const add = useMutation({ mutationFn: () => api.post("/athlete/life-events", { kind, starts_on: start, ends_on: end, available_minutes_per_day: minutes === "" ? null : Number(minutes), note }), onSuccess: () => { setNote(""); refresh(); } });
  const remove = useMutation({ mutationFn: (id: number) => api.delete(`/athlete/life-events/${id}`), onSuccess: refresh });
  return <Card><CardHeader title={t("athlete.life_events")} /><p className="text-[13px] text-muted">{t("athlete.life_events_note")}</p>
    <details className="mt-4"><summary className="cursor-pointer text-[13px]">{t("athlete.add_life_event")}</summary><form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); add.mutate(); }}>
      <Select label={t("athlete.life_kind")} value={kind} onChange={setKind} options={["travel", "illness", "short_week", "schedule_disruption"].map(value => ({ value, label: t("athlete.life_"+value) }))} />
      <div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.event_start")} type="date" value={start} onChange={setStart} required /><Input label={t("athlete.event_end")} type="date" value={end} onChange={setEnd} required /></div>
      <Input label={t("athlete.available_minutes")} type="number" min={0} max={1440} value={minutes} onChange={setMinutes} /><Input label={t("athlete.checkin_note")} value={note} onChange={setNote} />
      <Button type="submit" disabled={add.isPending || end < start}>{t("athlete.save_life_event")}</Button>
    </form></details>
    {(query.isError || add.isError || remove.isError) && <ErrorNote />}
    <ul className="mt-4">{query.data?.map(e => <li key={e.id} className="flex justify-between gap-3 border-t border-hairline py-3 text-[13px]"><div><p>{t("athlete.life_"+e.kind)} · {e.starts_on} – {e.ends_on}</p><p className="mt-1 text-muted">{e.note}</p></div><Button variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(e.id)}>{t("training.delete")}</Button></li>)}</ul>
  </Card>;
}
