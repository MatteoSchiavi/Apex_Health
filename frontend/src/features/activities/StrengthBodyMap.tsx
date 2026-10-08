import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ActivityDetail } from "../../app/api";
import { Card, CardHeader, Empty, StatPod, fmtNum } from "../../components/kit";
import { useUnits } from "../../components/data";
import { StrengthAnatomy } from "./StrengthAnatomy";

export function StrengthBodyMap({ activity }: { activity: ActivityDetail }) {
  const { t } = useTranslation();
  const units = useUnits();
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => setSelected(null), [activity.id]);
  const exercises = activity.presentation?.strength ?? [];
  const totalSets = exercises.reduce((total, exercise) => total + exercise.sets, 0);
  const totalReps = exercises.reduce((total, exercise) => total + exercise.reps, 0);
  const weightedSets = exercises.reduce((total, exercise) => total + exercise.weighted_sets, 0);
  const knownVolumes = exercises.flatMap(exercise => exercise.volume_kg == null ? [] : [exercise.volume_kg]);
  const totalVolume = knownVolumes.length ? knownVolumes.reduce((total, volume) => total + volume, 0) : null;
  const groups = new Set(exercises.map(e => e.muscle_group));
  const setsByGroup = exercises.reduce<Record<string, number>>((totals, exercise) => {
    const group = exercise.muscle_group ?? "unknown";
    totals[group] = (totals[group] ?? 0) + exercise.sets;
    return totals;
  }, {});
  const visible = selected == null ? exercises : exercises.filter(e => (e.muscle_group ?? "unknown") === selected);
  const label = (group: string | null) => t("sportView.group_" + (group ?? "unknown"));
  const choose = (group: string) => setSelected(selected === group ? null : group);
  const delta = (value: number | null | undefined) => value == null ? "—" : (value > 0 ? "+" : "") + fmtNum(value);
  return <Card>
    <CardHeader title={t("sportView.recorded_exercises")} />
    {!exercises.length ? <Empty>{t("sportView.no_exercises")}</Empty> : <>
      <div className="mb-6 border-b border-hairline pb-5">
        <h3 className="section-label mb-3">{t("sportView.total")}</h3>
        <div className="grid grid-cols-3 gap-4">
          <StatPod label={t("sportView.sets")} value={fmtNum(totalSets)} />
          <StatPod label={t("sportView.reps")} value={fmtNum(totalReps)} />
          <StatPod label={t("sportView.volume")} value={fmtNum(units.weight(totalVolume))} unit={units.weightUnit} />
        </div>
        {weightedSets < totalSets && <p className="mt-3 text-[12px] text-muted">{t("sportView.partial_volume", { known: weightedSets, total: totalSets })}</p>}
      </div>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <StrengthAnatomy sets={setsByGroup} selected={selected} onSelect={choose} />
        <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label={t("sportView.body_map")}>
          <button className={`min-h-10 rounded-full border px-3 py-2 text-[12px] transition-colors ${selected === null ? "border-primary/40 bg-primarySoft text-primaryText" : "border-hairline text-muted hover:text-ink"}`} aria-pressed={selected == null} onClick={() => setSelected(null)}>{t("sportView.all_groups")}</button>
          {Array.from(groups).map(group => <button key={group ?? "unknown"}
            className={`min-h-10 rounded-full border px-3 py-2 text-[12px] transition-colors ${selected === (group ?? "unknown") ? "border-primary/40 bg-primarySoft text-primaryText" : "border-hairline text-muted hover:text-ink"}`}
            aria-pressed={selected === (group ?? "unknown")} onClick={() => choose(group ?? "unknown")}>
            {label(group)} <span className="num ml-1.5 opacity-70">{setsByGroup[group ?? "unknown"]}</span>
          </button>)}
        </div>
      </div>
      <div className="min-w-0">
        {visible.map((exercise, i) => <div key={exercise.exercise_id ?? exercise.name + i} className="border-t border-hairline py-4">
          <h3 className="text-[15px] font-medium">{exercise.name}</h3>
          <p className="mt-1 text-[12px] text-muted">{label(exercise.muscle_group)}</p>
          <dl className="mt-4 grid grid-cols-3 gap-4 text-[13px]">
            <div><dt className="text-muted">{t("sportView.sets")}</dt><dd className="num mt-1">{exercise.sets}</dd></div>
            <div><dt className="text-muted">{t("sportView.reps")}</dt><dd className="num mt-1">{exercise.reps}</dd></div>
            <div><dt className="text-muted">{t("sportView.volume")}</dt><dd className="num mt-1">{fmtNum(units.weight(exercise.volume_kg))} {units.weightUnit}</dd></div>
          </dl>
          {exercise.weighted_sets < exercise.sets && <p className="mt-3 text-[12px] text-muted">{t("sportView.partial_volume", { known: exercise.weighted_sets, total: exercise.sets })}</p>}
          {!!exercise.recorded_sets?.length && <details className="mt-4 text-[12px]">
            <summary className="cursor-pointer text-muted">{t("sportView.set_details")}</summary>
            <div className="table-scroll mt-3">
              <table className="data-table" aria-label={exercise.name + " · " + t("sportView.set_details")}>
                <thead><tr><th>{t("sportView.sets")}</th><th>{t("sportView.reps")}</th><th>{t("sportView.weight")}</th></tr></thead>
                <tbody>{exercise.recorded_sets.map((set, index) => <tr key={index}>
                  <td>{index + 1}</td><td>{set.reps}</td><td>{fmtNum(units.weight(set.weight_kg), 1)} {units.weightUnit}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </details>}
          {exercise.previous ? <div className="mt-4 text-[12px] text-muted">
            <p>{t("sportView.previous")} · {exercise.previous.date}: {exercise.previous.sets} {t("sportView.sets")} · {exercise.previous.reps} {t("sportView.reps")} · {fmtNum(units.weight(exercise.previous.volume_kg))} {units.weightUnit}</p>
            {exercise.previous.weighted_sets != null && exercise.previous.weighted_sets < exercise.previous.sets && <p className="mt-2">{t("sportView.partial_volume", { known: exercise.previous.weighted_sets, total: exercise.previous.sets })}</p>}
            <p className="mt-2">{t("sportView.delta")}: {delta(exercise.delta_sets)} {t("sportView.sets")} · {delta(exercise.delta_reps)} {t("sportView.reps")} · {delta(units.weight(exercise.delta_volume_kg))} {units.weightUnit}</p>
          </div> : <p className="mt-4 text-[12px] text-muted">{t("sportView.no_previous")}</p>}
        </div>)}
      </div>
    </div></>}
  </Card>;
}
