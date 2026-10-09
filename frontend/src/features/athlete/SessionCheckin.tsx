import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../app/api";
import { Badge, Button, Input, Select } from "../../components/kit";
import type { Checkin } from "./types";

export function SessionCheckin({ activityId, plannedSessionId, checkin }: { activityId?: number; plannedSessionId?: number; checkin?: Checkin | null }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [status, setStatus] = useState(checkin?.status ?? "completed");
  const [rpe, setRpe] = useState(String(checkin?.rpe ?? ""));
  const [pain, setPain] = useState(checkin?.pain == null ? "" : checkin.pain ? "yes" : "no");
  const [unwell, setUnwell] = useState(checkin?.felt_unwell == null ? "" : checkin.felt_unwell ? "yes" : "no");
  const [note, setNote] = useState(checkin?.note ?? "");
  useEffect(() => { if (checkin) { setStatus(checkin.status); setRpe(String(checkin.rpe ?? "")); setPain(checkin.pain == null ? "" : checkin.pain ? "yes" : "no"); setUnwell(checkin.felt_unwell == null ? "" : checkin.felt_unwell ? "yes" : "no"); setNote(checkin.note); } }, [checkin?.revision]);
  const save = useMutation({ mutationFn: () => api.put<Checkin>("/athlete/checkins", {
    activity_id: activityId, planned_session_id: plannedSessionId, expected_revision: checkin?.revision ?? 0,
    status, rpe: status === "skipped" || rpe === "" ? null : Number(rpe), pain: pain === "" ? null : pain === "yes", felt_unwell: unwell === "" ? null : unwell === "yes", note,
  }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["athlete-day"] }); qc.invalidateQueries({ queryKey: ["endurance"] }); qc.invalidateQueries({ queryKey: ["lab"] }); } });
  const choices = [{ value: "", label: t("design.not_specified") }, { value: "yes", label: t("athlete.yes") }, { value: "no", label: t("athlete.no") }];
  return <details className="mt-3 border-t border-hairline pt-3 text-[13px]">
    <summary className="cursor-pointer text-ink2">{t("athlete.checkin_title")}</summary>
    <form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-2"><Select label={t("athlete.session_status")} value={status} onChange={setStatus} options={(activityId ? ["completed", "partial"] : ["completed", "partial", "skipped"]).map(value => ({ value, label: t("athlete.state_"+value) }))} />
      {status !== "skipped" && <Input label={t("athlete.rpe")} type="number" min={0} max={10} step={1} value={rpe} onChange={setRpe} />}
      <Select label={t("athlete.pain")} value={pain} onChange={setPain} options={choices} /><Select label={t("athlete.felt_unwell")} value={unwell} onChange={setUnwell} options={choices} /></div>
      <Input label={t("athlete.checkin_note")} value={note} onChange={setNote} />
      <p className="text-[12px] text-muted">{t("athlete.checkin_limits")}</p>
      {save.isError && <p role="alert" className="text-alertText">{t(save.error instanceof ApiError && save.error.status === 409 ? "athlete.conflict" : "athlete.save_error")}</p>}
      <div className="flex items-center gap-3"><Button type="submit" disabled={save.isPending}>{t("athlete.save_checkin")}</Button>{save.isSuccess && <Badge tone="positive">{t("settings.saved")}</Badge>}</div>
    </form>
  </details>;
}
