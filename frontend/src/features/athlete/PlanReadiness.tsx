import { useTranslation } from "react-i18next";
import { friendlyDiscipline } from "../../components/kit";
import type { PlanStructure } from "./importTypes";
import { planReadiness } from "./planReadiness";

export function PlanReadiness({ structure, disciplines, showReady = true }: { structure: PlanStructure; disciplines?: readonly string[]; showReady?: boolean }) {
  const { t } = useTranslation();
  const state = planReadiness(structure, disciplines);
  if (state.ready) return showReady ? <p role="status" className="text-[13px] text-positive">{t("v01Plan.dates_ready")}</p> : null;
  const sessionNames = (indices: number[]) => indices.map(index => t("v01Plan.session_name", { number: index + 1, sport: friendlyDiscipline(structure.sessions[index].discipline, t) })).join(", ");
  return <section aria-label={t("v01Plan.before_activation")} className="space-y-2 border-l-2 border-warning pl-3 text-[13px]">
    <h4 className="font-medium">{t("v01Plan.before_activation")}</h4>
    <ul className="list-disc space-y-2 pl-5">
      {!structure.starts_on && <li>{t("v01Plan.start_required")}</li>}
      {!structure.ends_on && <li>{t("v01Plan.end_required")}</li>}
      {!structure.sessions.length && <li>{t("v01Plan.workout_required")}</li>}
      {!!state.missingDates.length && <li>{t("v01Plan.dates_missing", { count: state.missingDates.length })}<p className="mt-1 break-words text-muted">{sessionNames(state.missingDates)}</p></li>}
      {!!state.invalidSports.length && <li>{t("v01Plan.sports_missing", { sessions: state.invalidSports.map(index => index + 1).join(", ") })}</li>}
      {state.reversedRange && <li>{t("v01Plan.range_reversed")}</li>}
      {state.rangeTooLong && <li>{t("v01Plan.range_too_long")}</li>}
      {!!state.outsideRange.length && <li>{t("v01Plan.outside_range", { sessions: state.outsideRange.map(index => index + 1).join(", ") })}</li>}
    </ul>
    <p className="text-muted">{t("v01Plan.choose_actual_dates")}</p>
  </section>;
}
