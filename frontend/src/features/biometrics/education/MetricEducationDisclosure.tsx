import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useUnits } from "../../../components/data";
import { fmtHours, fmtNum } from "../../../components/kit";
import type { EducationFact, EducationText, MetricExplanation } from "./contract";

/** Renders the explanation contract only; knows no metric formulas or metadata source. */
export function MetricEducationDisclosure({ education }: { education: MetricExplanation }) {
  const { t } = useTranslation();
  const units = useUnits();
  const id = useId();
  const [open, setOpen] = useState(false);
  const localize = (text: EducationText) => t(text.key, text.values);
  const display = (fact: EducationFact) => {
    const value = fact.display;
    if ("key" in value) return localize(value);
    const converted = units.metric(value.metric, value.value)!;
    const formatted = value.unit === "h"
      ? `${converted < 0 ? "−" : ""}${fmtHours(Math.abs(converted) * 3600)}`
      : `${fmtNum(converted, ["steps", "floors"].includes(value.metric) ? 0 : 1)} ${units.metricUnit(value.metric, value.unit)}`;
    return value.signed && converted > 0 ? `+${formatted}` : formatted;
  };
  const contributors = education.semanticType === "apex_derived" ? education.actualCalculation?.contributors : undefined;
  const facts = contributors?.length ? contributors : education.context;
  const contextHeading = contributors?.length ? "metricEducation.why_today" : "metricEducation.your_context";
  const methodologyHeading = {
    measured: "metricEducation.how_interpreted",
    apex_derived: "metricEducation.how_calculated",
    provider_proprietary: "metricEducation.about_calculation",
  }[education.semanticType];
  const headingClass = "mb-3 text-[11px] font-medium uppercase tracking-[0.08em] text-muted";
  return (
    <details className="mb-6 border-y border-hairline" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary aria-expanded={open} aria-controls={id} className="cursor-pointer py-4 text-[14px] font-medium">
        {t("metricEducation.understand")}
      </summary>
      <div id={id} className="grid min-w-0 grid-cols-1 gap-x-12 gap-y-7 break-words pb-6 text-[13px] leading-relaxed md:grid-cols-2">
        {facts.length > 0 && <section aria-labelledby={`${id}-context`} className="min-w-0">
          <h2 id={`${id}-context`} className={headingClass}>{t(contextHeading)}</h2>
          {contributors?.length && education.actualCalculation && <p className="mb-3 text-[12px] text-muted">{t("metricEducation.calculation_date", { date: education.actualCalculation.asOf })}</p>}
          <dl className="space-y-2">
            {facts.map((fact, index) => <div key={index} className="flex flex-wrap justify-between gap-x-4 gap-y-1">
              <dt className="text-muted">{localize(fact.label)}</dt>
              <dd className="num max-w-full break-words">{display(fact)}</dd>
            </div>)}
          </dl>
        </section>}
        <section aria-labelledby={`${id}-definition`} className="min-w-0">
          <h2 id={`${id}-definition`} className={headingClass}>{t("metricEducation.what_is_it")}</h2>
          <p>{localize(education.definition)}</p>
          {education.whyItMatters && <p className="mt-2 text-muted">{localize(education.whyItMatters)}</p>}
        </section>
        {education.knownInfluences.length > 0 && <section aria-labelledby={`${id}-influences`} className="min-w-0">
          <h2 id={`${id}-influences`} className={headingClass}>{t("metricEducation.what_affects_it")}</h2>
          <p>{education.knownInfluences.map(localize).join(" · ")}</p>
          <p className="mt-2 text-muted">{t("metricEducation.influences_note")}</p>
        </section>}
        {education.actionableFactors.length > 0 && <section aria-labelledby={`${id}-actions`} className="min-w-0">
          <h2 id={`${id}-actions`} className={headingClass}>{t("metricEducation.what_you_can_influence")}</h2>
          {education.actionableFactors.map((action, index) => <p key={index} className={index ? "mt-2" : undefined}>{localize(action)}</p>)}
        </section>}
        {(education.methodology.length > 0 || education.provenance.length > 0 || education.limitations.length > 0) && <section aria-labelledby={`${id}-methodology`} className="min-w-0 border-t border-hairline pt-4 md:col-span-2">
          <h2 id={`${id}-methodology`} className={headingClass}>{t(methodologyHeading)}</h2>
          <p className="mb-2 text-muted">{t(`metricEducation.semantics.${education.semanticType}`)}</p>
          {education.methodology.map((method, index) => <p key={index} className={index ? "mt-2" : undefined}>{localize(method)}</p>)}
          {education.provenance.length > 0 && <p className="mt-2 text-muted">{t("metricEducation.source")} · {education.provenance.map(localize).join(" · ")}</p>}
          {education.limitations.map((limit, index) => <p key={index} className="mt-2 text-muted">{localize(limit)}</p>)}
        </section>}
      </div>
    </details>
  );
}
