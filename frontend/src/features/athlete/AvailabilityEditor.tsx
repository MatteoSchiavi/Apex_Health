import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Select } from "../../components/kit";
import type { AthleteContext } from "./types";

type Window = NonNullable<AthleteContext["availability"]>[number];
export interface AvailabilityEntry { selected: number[]; start: string; end: string }
const minutes = (time: string) => {
  const [hours, mins] = time.split(":").map(Number);
  return hours * 60 + mins;
};

export function availabilityError(windows: Window[]): string | null {
  if (windows.some(w => !w.start || !w.end)) return "athlete.complete_window";
  if (windows.some(w => minutes(w.start) >= minutes(w.end))) return "athlete.availability_overnight";
  if (windows.length > 28) return "athlete.availability_limit";
  if (windows.some((a, i) => windows.slice(i + 1).some(b => a.day === b.day && minutes(a.start) < minutes(b.end) && minutes(b.start) < minutes(a.end)))) return "athlete.availability_overlap";
  return null;
}

export function AvailabilityEditor({ value, onChange, entry, onEntryChange, revision }: {
  value: Window[]; onChange: (value: Window[]) => void; entry: AvailabilityEntry; onEntryChange: (entry: AvailabilityEntry) => void; revision: number;
}) {
  const { t, i18n } = useTranslation();
  const { selected, start, end } = entry;
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => setMessage(null), [revision]);
  const days = Array.from({ length: 7 }, (_, day) => ({ value: String(day), label: new Intl.DateTimeFormat(i18n.language, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1 + day))) }));
  const pending = Boolean(start || end);
  const error = availabilityError(value);
  function apply() {
    const additions = selected.map(day => ({ day, start, end }));
    const invalid = availabilityError(additions);
    if (!selected.length || invalid) { setMessage(invalid ?? "athlete.availability_choose_days"); return; }
    const next = [...value];
    for (const window of additions) {
      if (!next.some(old => old.day === window.day && minutes(old.start) === minutes(window.start) && minutes(old.end) === minutes(window.end))) next.push(window);
    }
    const conflict = availabilityError(next);
    if (conflict) { setMessage(conflict); return; }
    if (next.length === value.length) { onEntryChange({ ...entry, start: "", end: "" }); setMessage("athlete.availability_already_added"); return; }
    onChange(next.sort((a, b) => a.day - b.day || minutes(a.start) - minutes(b.start)));
    onEntryChange({ ...entry, start: "", end: "" }); setMessage("athlete.availability_applied");
  }
  return <div className="space-y-4">
    <p className="text-[13px] text-muted">{t("athlete.availability_note")}</p>
    <fieldset className="space-y-3 border border-hairline p-4">
      <legend className="px-1 text-[14px] font-medium">{t("athlete.availability_bulk")}</legend>
      <div className="flex flex-wrap gap-2"><Button variant="ghost" onClick={() => onEntryChange({ ...entry, selected: [0, 1, 2, 3, 4] })}>{t("athlete.weekdays")}</Button><Button variant="ghost" onClick={() => onEntryChange({ ...entry, selected: [5, 6] })}>{t("athlete.weekend")}</Button></div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">{days.map(day => <label className="flex min-h-11 items-center gap-2 text-[13px]" key={day.value}><input type="checkbox" checked={selected.includes(Number(day.value))} onChange={event => onEntryChange({ ...entry, selected: event.target.checked ? [...selected, Number(day.value)] : selected.filter(d => d !== Number(day.value)) })} />{day.label}</label>)}</div>
      <div className="grid gap-3 sm:grid-cols-2"><Input label={t("athlete.bulk_start_time")} type="time" value={start} onChange={start => { onEntryChange({ ...entry, start }); setMessage(null); }} /><Input label={t("athlete.bulk_end_time")} type="time" value={end} onChange={end => { onEntryChange({ ...entry, end }); setMessage(null); }} /></div>
      <div className="flex flex-wrap gap-3"><Button variant="ghost" onClick={apply}>{t("athlete.apply_window")}</Button>{pending && <Button variant="ghost" onClick={() => { onEntryChange({ ...entry, start: "", end: "" }); setMessage(null); }}>{t("athlete.cancel_window")}</Button>}</div>
      {pending && <p className="text-[12px] text-muted">{t("athlete.availability_apply_first")}</p>}
      {message && <p role={["athlete.availability_applied", "athlete.availability_already_added"].includes(message) ? "status" : "alert"} className="text-[13px]">{t(message)}</p>}
    </fieldset>
    {!!value.length && <section aria-label={t("athlete.weekly_schedule")}><h4 className="mb-3 text-[14px] font-medium">{t("athlete.weekly_schedule")}</h4><p className="mb-3 text-[12px] text-muted">{t("athlete.availability_exceptions")}</p><div className="space-y-3">{value.map((window, index) => <div key={index} className="grid items-end gap-3 border-t border-hairline pt-3 sm:grid-cols-4">
      <Select label={t("athlete.window_day", { count: index + 1 })} value={String(window.day)} options={days} onChange={day => onChange(value.map((old, i) => i === index ? { ...old, day: Number(day) } : old))} />
      <Input label={t("athlete.window_start", { count: index + 1 })} type="time" value={window.start.slice(0, 5)} onChange={start => onChange(value.map((old, i) => i === index ? { ...old, start } : old))} />
      <Input label={t("athlete.window_end", { count: index + 1 })} type="time" value={window.end.slice(0, 5)} onChange={end => onChange(value.map((old, i) => i === index ? { ...old, end } : old))} />
      <Button variant="ghost" onClick={() => onChange(value.filter((_, i) => i !== index))}>{t("athlete.remove_window")}</Button>
    </div>)}</div></section>}
    {error && <p role="alert" className="text-[13px] text-alertText">{t(error)}</p>}
  </div>;
}
