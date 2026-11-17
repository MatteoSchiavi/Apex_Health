import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Card } from "../../components/kit";
import { StepSummary, type StructuredWorkout } from "./StructuredWorkoutSteps";

/** Reading progress only. Uses the approved version and never writes a result. */
export function WorkoutGuide({ workout }: { workout: StructuredWorkout }) {
  const { t } = useTranslation();
  const [index, setIndex] = useState<number | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const start = useRef<HTMLButtonElement>(null);
  function move(next: number) { setIndex(next); requestAnimationFrame(() => heading.current?.focus()); }
  if (!workout.steps.length) return null;
  return <Card>
    <h2 className="mb-2 text-[16px] font-medium">{t("workflowFlow.approved_guide")}</h2>
    <p className="mb-4 text-[13px] text-muted">{workout.title}</p>
    {index === null ? <><p className="mb-4 text-[13px] text-muted">{t("workflowFlow.guide_note")}</p><button ref={start} className="inline-flex min-h-11 items-center justify-center rounded-control bg-ink px-3 text-[13px] font-medium text-canvas hover:opacity-85" onClick={() => move(0)}>{t("workflowFlow.follow")}</button></> : <>
      <h2 ref={heading} tabIndex={-1} className="text-[16px] font-medium" aria-live="polite">{t("workflowFlow.step",{current:index+1,total:workout.steps.length})}</h2>
      <ol className="my-5"><StepSummary step={workout.steps[index]} number={String(index+1)} /></ol>
      <div className="flex flex-wrap gap-3"><Button variant="ghost" disabled={index === 0} onClick={() => move(index-1)}>{t("workflowFlow.previous")}</Button>
        {index+1 < workout.steps.length ? <Button onClick={() => move(index+1)}>{t("workflowFlow.next")}</Button> : <Button onClick={() => { const completion = document.getElementById("workout-completion"); completion?.scrollIntoView({behavior:"smooth",block:"start"}); completion?.focus({preventScroll:true}); }}>{t("workflowFlow.finish")}</Button>}
        <Button variant="ghost" onClick={() => {setIndex(null); requestAnimationFrame(() => start.current?.focus());}}>{t("workflowFlow.stop")}</Button>
      </div>
    </>}
  </Card>;
}
