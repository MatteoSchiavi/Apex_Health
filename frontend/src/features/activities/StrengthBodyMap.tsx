import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ActivityDetail } from "../../app/api";
import { Card, CardHeader, Empty, StatPod, fmtNum } from "../../components/kit";
import { useUnits } from "../../components/data";

const GROUPS = ["legs", "push", "pull", "core", "full_body"];
const PATHS: Record<string, string> = {
  push: "M64 46 L82 42 L96 52 L114 42 L132 46 L136 66 L112 77 L84 77 L60 66 Z",
  pull: "M63 80 L82 75 L98 83 L114 75 L133 80 L120 101 L76 101 Z",
  core: "M77 103 L119 103 L115 129 L81 129 Z",
  legs: "M79 133 L96 133 L94 195 L77 195 L72 163 Z M100 133 L117 133 L124 163 L119 195 L102 195 Z",
  full_body: "M90 8 L106 8 L112 20 L106 33 L90 33 L84 20 Z M57 70 L70 75 L58 122 L44 117 Z M126 75 L139 70 L152 117 L138 122 Z",
};

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
      <div className="grid gap-6 md:grid-cols-[220px_1fr]">
      <div>
        <svg viewBox="0 0 196 210" className="mx-auto h-64 w-full" role="group" aria-label={t("sportView.body_map")}>
          <path d="M89 4 L107 4 L116 18 L110 37 L130 40 L144 68 L160 120 L141 130 L126 91 L124 130 L130 165 L123 204 L100 204 L98 160 L96 204 L73 204 L66 165 L72 130 L70 91 L55 130 L36 120 L52 68 L66 40 L86 37 L80 18 Z" className="fill-surface stroke-hairline" strokeWidth="2" pointerEvents="none" />
          {GROUPS.map(group => <g key={group}
            role="button" tabIndex={groups.has(group) ? 0 : -1} aria-label={label(group)}
            aria-pressed={selected === group} aria-disabled={!groups.has(group)}
            onClick={() => groups.has(group) && choose(group)}
            onKeyDown={e => { if (groups.has(group) && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); choose(group); } }}
            className={groups.has(group) ? "group cursor-pointer focus:outline-none" : "group"}>
            {group === "legs" && <rect x="72" y="133" width="52" height="62" fill="transparent" pointerEvents="all" />}
            <path d={PATHS[group]}
              className={groups.has(group) ? "fill-ink/30 stroke-ink group-focus:fill-ink/60" : "fill-hairline stroke-hairline"}
              style={{ fillOpacity: selected === group ? 1 : 0.5 }} strokeWidth="1.2" />
          </g>)}
        </svg>
        <p className="text-[12px] text-muted">{t("sportView.body_map_note")}</p>
        <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label={t("sportView.body_map")}>
          <button className="text-link text-[12px]" aria-pressed={selected == null} onClick={() => setSelected(null)}>{t("sportView.all_groups")}</button>
          {Array.from(groups).map(group => <button key={group ?? "unknown"} className="text-link text-[12px]" aria-pressed={selected === (group ?? "unknown")} onClick={() => choose(group ?? "unknown")}>{label(group)}</button>)}
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
