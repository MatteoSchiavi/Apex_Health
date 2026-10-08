import { useId } from "react";
import { useUi } from "../../app/stores/ui";
import { ANATOMY_REGIONS, BODY_OUTLINES, type BodyVariant } from "./anatomyArtwork";
import { useTranslation } from "react-i18next";

const GROUPS = ["legs", "push", "pull", "core", "full_body"] as const;

const HEAT = [
  ["#ffe3be", "#f1b17b"],
  ["#ffd195", "#f49755"],
  ["#ffbd78", "#f67b3f"],
  ["#ffb36b", "#ef5928"],
];

export function StrengthAnatomy({ sets, selected, onSelect }: {
  sets: Record<string, number>;
  selected: string | null;
  onSelect: (group: string) => void;
}) {
  const { t } = useTranslation();
  const profileSex = useUi(state => state.me?.sex);
  const bodyVariant: BodyVariant = profileSex === "female" ? "female" : "male";
  const id = "anatomy-" + useId().replace(/:/g, "");
  const fullBodySets = sets.full_body ?? 0;
  const maximum = Math.max(1, ...GROUPS.map(group => group === "full_body" ? fullBodySets : (sets[group] ?? 0) + fullBodySets));
  const level = (count: number) => count > 0 ? Math.max(1, Math.ceil(count / maximum * 4)) : 0;
  return <div data-body-variant={bodyVariant} className="strength-anatomy rounded-2xl border border-hairline bg-surface2/40 p-4 sm:p-5">
    <div className="flex items-baseline justify-between gap-4">
      <h3 className="text-[15px] font-medium">{t("sportView.body_map")}</h3>
      <span className="text-[11px] text-muted">{t("sportView.recorded_sets")}</span>
    </div>
    <div className="mx-auto mt-2 w-full max-w-[440px]">
    <svg viewBox="0 0 432 525" className="w-full" role="group"
      aria-label={t("sportView.body_map")} aria-describedby={id + "-description"}>
      <desc id={id + "-description"}>{t("sportView.body_map_note")}</desc>
      <defs>
        {HEAT.map(([center, edge], index) => <radialGradient key={index} id={`${id}-heat-${index + 1}`} cx="45%" cy="38%" r="75%">
          <stop offset="0" stopColor={center} />
          <stop offset="1" stopColor={edge} />
        </radialGradient>)}
        <clipPath id={id + "-torso"}><rect x="0" y="91" width="182" height="420" /></clipPath>
      </defs>
      {(["front", "back"] as const).map(side => <g key={side} transform={`translate(${side === "front" ? 26 : 224} 15)`} pointerEvents="none">
        <path data-outline={side} d={BODY_OUTLINES[bodyVariant][side]} fill="var(--anatomy-outline)" fillRule="evenodd" />
      </g>)}
      {GROUPS.map(group => {
        const count = sets[group] ?? 0;
        const illustratedCount = group === "full_body" ? count : count + fullBodySets;
        const intensity = level(illustratedCount);
        const muted = selected !== null && selected !== group && selected !== "full_body";
        return <g key={group} role="button" data-group={group} data-set-count={count} data-intensity={intensity}
          tabIndex={count > 0 ? 0 : -1} aria-label={t("sportView.group_" + group)}
          aria-pressed={selected === group} aria-disabled={count === 0}
          className={`anatomy-group ${count > 0 ? "cursor-pointer" : ""}`}
          onClick={() => count > 0 && onSelect(group)}
          onKeyDown={event => {
            if (count > 0 && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onSelect(group); }
          }}>
          <title>{t("sportView.group_" + group)} · {count} {t("sportView.sets")}</title>
          {ANATOMY_REGIONS.filter(muscle => {
            // A full-body recording owns otherwise unassigned regions, so a
            // coloured region always has the matching enabled filter.
            const owner = (sets[muscle.group] ?? 0) > 0 || fullBodySets === 0 ? muscle.group : "full_body";
            return owner === group;
          }).map((muscle, index) => <g key={muscle.name + index}
            transform={`translate(${muscle.side === "front" ? 26 : 224} 15)`}>
            <path data-muscle={muscle.name} data-view={muscle.side} d={muscle.paths[bodyVariant]}
              fill={intensity ? `url(#${id}-heat-${intensity})` : "var(--anatomy-rest)"}
              opacity={muted && intensity > 0 ? 0.22 : 1}
              stroke={selected === group ? "var(--anatomy-selected)" : "none"}
              strokeWidth="1.4" pointerEvents={count > 0 ? "visiblePainted" : "none"} />
          </g>)}
          {group === "full_body" && count > 0 && (["front", "back"] as const).map(side => <g key={side} transform={`translate(${side === "front" ? 26 : 224} 15)`}>
            <path d={BODY_OUTLINES[bodyVariant][side]} clipPath={`url(#${id}-torso)`}
              fill="var(--anatomy-selected)" fillRule="evenodd" opacity={selected === group ? 1 : 0.6} />
          </g>)}
        </g>;
      })}
    </svg>
    <div className="grid grid-cols-2 text-center text-[11px] text-muted">
      <span>{t("sportView.body_front")}</span>
      <span>{t("sportView.body_back")}</span>
    </div>
    </div>
    <div className="mt-4 flex items-center justify-between gap-3 border-t border-hairline pt-4 text-[11px] text-muted">
      <span>{t("sportView.fewer_sets")}</span>
      <span className="flex items-center gap-1.5" aria-hidden="true">
        <i className="h-2.5 w-5 rounded-sm" style={{ background: "var(--anatomy-rest)" }} />
        {HEAT.map(([center, edge], index) => <i key={index} className="h-2.5 w-5 rounded-sm" style={{ background: `linear-gradient(120deg, ${center}, ${edge})` }} />)}
      </span>
      <span>{t("sportView.more_sets")}</span>
    </div>
    <p className="mt-3 text-[11px] leading-relaxed text-muted">{t("sportView.body_map_note")}</p>
  </div>;
}
