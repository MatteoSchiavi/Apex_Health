import { useId } from "react";
import { useTranslation } from "react-i18next";

const GROUPS = ["legs", "push", "pull", "core", "full_body"] as const;
type MovementGroup = typeof GROUPS[number];
type MuscleShape = {
  name: string;
  group: MovementGroup;
  side: "front" | "back";
  path: string;
  paired?: boolean;
};

// Original vector artwork. Regions illustrate the existing broad movement
// groups, not individually measured muscle recruitment or physiological load.
const SILHOUETTE = `M91 10
  C76 10 65 21 65 39 C65 54 69 68 78 73 L77 84
  C75 93 64 95 53 98 C39 102 28 111 26 125
  C24 137 25 146 23 157 L16 195 C11 212 11 225 9 239
  L3 282 C1 292 0 303 5 314 L10 323 C14 329 19 324 15 318
  L11 307 C9 300 11 295 13 294 L15 305 C16 311 20 309 20 303
  L18 287 L28 254 C33 237 36 220 39 205 L46 173
  C47 196 44 214 42 234 C40 252 40 268 43 284 L45 313
  C44 339 49 360 49 381 C49 403 52 423 56 443 L58 467
  C57 477 50 485 49 491 C48 498 58 500 69 501
  C75 501 79 498 79 491 L78 473 C81 456 79 440 81 423
  C85 405 85 392 83 379 L83 353 C85 330 88 310 89 293
  L93 293 C94 310 97 330 99 353 L99 379
  C97 392 97 405 101 423 C103 440 101 456 104 473 L103 491
  C103 498 107 501 113 501 C124 500 134 498 133 491
  C132 485 125 477 124 467 L126 443 C130 423 133 403 133 381
  C133 360 138 339 137 313 L139 284 C142 268 142 252 140 234
  C138 214 135 196 136 173 L143 205 C146 220 149 237 154 254
  L164 287 L162 303 C162 309 166 311 167 305 L169 294
  C171 295 173 300 171 307 L167 318 C163 324 168 329 172 323
  L177 314 C182 303 181 292 179 282 L173 239
  C171 225 171 212 166 195 L159 157 C157 146 158 137 156 125
  C154 111 143 102 129 98 C118 95 107 93 105 84 L104 73
  C113 68 117 54 117 39 C117 21 106 10 91 10 Z`;

const MUSCLES: MuscleShape[] = [
  { name: "deltoids", group: "push", side: "front", paired: true,
    path: "M49 105 C37 108 30 117 30 130 L31 142 C39 139 46 132 48 124 C49 117 54 111 57 109 C57 105 53 104 49 105 Z" },
  { name: "pectorals", group: "push", side: "front", paired: true,
    path: "M59 114 C68 110 80 110 87 115 L87 145 C86 154 66 157 56 151 C50 147 49 137 51 127 C52 121 55 117 59 114 Z" },
  { name: "biceps", group: "pull", side: "front", paired: true,
    path: "M32 150 C27 155 25 165 26 176 L28 189 C29 195 33 193 36 183 L42 160 C45 149 38 145 32 150 Z" },
  { name: "forearms", group: "pull", side: "front", paired: true,
    path: "M21 202 C17 214 15 233 12 252 C11 259 15 261 19 252 L29 224 C32 214 30 204 26 200 C24 198 22 199 21 202 Z" },
  { name: "upper_abs", group: "core", side: "front", paired: true,
    path: "M78 161 C81 159 85 159 87 161 L87 181 C83 184 74 184 73 179 L73 169 C73 164 75 162 78 161 Z" },
  { name: "middle_abs", group: "core", side: "front", paired: true,
    path: "M76 188 C80 187 85 187 87 189 L87 204 C85 208 76 208 74 204 L73 194 C73 191 74 189 76 188 Z" },
  { name: "lower_abs", group: "core", side: "front", paired: true,
    path: "M76 212 C81 211 85 212 87 214 L87 250 C84 254 80 251 79 246 L74 221 C73 216 73 214 76 212 Z" },
  { name: "obliques", group: "core", side: "front", paired: true,
    path: "M53 160 C57 156 62 159 63 165 L65 204 C63 211 59 208 57 202 L51 171 C50 166 50 162 53 160 Z M51 211 C55 208 61 215 66 224 L71 242 C71 249 66 247 61 240 L51 226 C48 219 48 215 51 211 Z" },
  { name: "adductors", group: "legs", side: "front", paired: true,
    path: "M75 267 C80 265 86 273 85 285 L80 320 C79 332 76 343 73 349 C70 346 71 333 70 320 L66 285 C66 276 69 270 75 267 Z" },
  { name: "quads", group: "legs", side: "front", paired: true,
    path: "M53 263 C59 266 64 280 64 294 L66 334 C67 349 65 366 61 370 C57 373 53 365 52 355 L47 320 C44 300 46 276 50 266 C51 264 52 263 53 263 Z" },
  { name: "tibialis", group: "legs", side: "front", paired: true,
    path: "M55 387 C58 381 62 386 62 398 L65 432 C66 441 65 450 63 452 C59 444 55 426 54 410 C53 398 53 391 55 387 Z M75 389 C79 385 81 391 80 402 L76 432 C75 441 73 450 71 451 C70 442 71 422 72 409 C72 398 73 392 75 389 Z" },
  { name: "rear_deltoids", group: "push", side: "back", paired: true,
    path: "M49 105 C37 108 30 117 30 131 L32 142 C40 139 46 132 48 124 C50 117 54 112 59 109 C57 105 53 104 49 105 Z" },
  { name: "triceps", group: "push", side: "back", paired: true,
    path: "M32 150 C27 155 25 165 26 176 L28 190 C29 196 34 193 37 183 L42 158 C44 150 37 146 32 150 Z" },
  { name: "back_forearms", group: "pull", side: "back", paired: true,
    path: "M21 202 C17 214 15 233 12 252 C11 259 15 261 19 252 L29 224 C32 214 30 204 26 200 C24 198 22 199 21 202 Z" },
  { name: "trapezius", group: "pull", side: "back",
    path: "M91 91 C81 100 71 105 61 109 C66 115 77 118 84 126 L85 166 C86 173 96 173 97 166 L98 126 C105 118 116 115 121 109 C111 105 101 100 91 91 Z" },
  { name: "lats", group: "pull", side: "back", paired: true,
    path: "M59 120 C68 117 76 122 79 133 L81 173 C80 188 73 201 72 214 L63 236 C59 241 51 239 50 233 C55 214 52 204 48 185 L47 143 C47 132 51 124 59 120 Z" },
  { name: "lower_back", group: "core", side: "back", paired: true,
    path: "M79 208 C83 206 87 211 87 220 L87 249 C81 254 70 251 66 244 L72 222 C74 215 76 210 79 208 Z" },
  { name: "glutes", group: "legs", side: "back", paired: true,
    path: "M63 256 C73 250 81 251 86 257 L87 283 C84 296 74 304 63 299 C51 295 46 283 50 272 C53 264 57 259 63 256 Z" },
  { name: "hamstrings", group: "legs", side: "back", paired: true,
    path: "M54 310 C62 304 76 307 81 316 C82 329 78 345 76 355 L71 374 C66 380 57 373 55 365 L49 330 C47 320 49 314 54 310 Z" },
  { name: "calves", group: "legs", side: "back", paired: true,
    path: "M63 387 C69 380 77 382 79 394 C82 408 77 429 73 444 C71 452 66 452 63 444 C60 432 58 419 58 408 C58 398 59 391 63 387 Z" },
];

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
  const id = "anatomy-" + useId().replace(/:/g, "");
  const fullBodySets = sets.full_body ?? 0;
  const maximum = Math.max(1, ...GROUPS.map(group => group === "full_body" ? fullBodySets : (sets[group] ?? 0) + fullBodySets));
  const level = (count: number) => count > 0 ? Math.max(1, Math.ceil(count / maximum * 4)) : 0;
  return <div className="strength-anatomy rounded-2xl border border-hairline bg-surface2/40 p-4 sm:p-5">
    <div className="flex items-baseline justify-between gap-4">
      <h3 className="text-[15px] font-medium">{t("sportView.body_map")}</h3>
      <span className="text-[11px] text-muted">{t("sportView.recorded_sets")}</span>
    </div>
    <svg viewBox="0 0 432 550" className="mx-auto mt-2 w-full max-w-[440px]" role="group"
      aria-label={t("sportView.body_map")} aria-describedby={id + "-description"}>
      <desc id={id + "-description"}>{t("sportView.body_map_note")}</desc>
      <defs>
        <linearGradient id={id + "-body"} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="var(--anatomy-body-edge)" />
          <stop offset="0.5" stopColor="var(--anatomy-body)" />
          <stop offset="1" stopColor="var(--anatomy-body-edge)" />
        </linearGradient>
        {HEAT.map(([center, edge], index) => <radialGradient key={index} id={`${id}-heat-${index + 1}`} cx="45%" cy="38%" r="75%">
          <stop offset="0" stopColor={center} />
          <stop offset="1" stopColor={edge} />
        </radialGradient>)}
        <clipPath id={id + "-torso"}><rect x="0" y="91" width="182" height="420" /></clipPath>
      </defs>
      {[26, 224].map(x => <g key={x} transform={`translate(${x} 15)`} pointerEvents="none">
        <path d={SILHOUETTE} fill={`url(#${id}-body)`} stroke="var(--anatomy-outline)" strokeWidth="1.5" />
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
          {MUSCLES.filter(muscle => {
            // A full-body recording owns otherwise unassigned regions, so a
            // coloured region always has the matching enabled filter.
            const owner = (sets[muscle.group] ?? 0) > 0 || fullBodySets === 0 ? muscle.group : "full_body";
            return owner === group;
          }).map(muscle => <g key={muscle.name}
            transform={`translate(${muscle.side === "front" ? 26 : 224} 15)`}>
            {(muscle.paired ? [false, true] : [false]).map(mirror => <path key={String(mirror)}
              data-muscle={muscle.name} data-view={muscle.side} d={muscle.path}
              transform={mirror ? "translate(182 0) scale(-1 1)" : undefined}
              fill={intensity ? `url(#${id}-heat-${intensity})` : "var(--anatomy-rest)"}
              opacity={muted && intensity > 0 ? 0.22 : 1}
              stroke={selected === group ? "var(--anatomy-selected)" : "none"}
              strokeWidth="1.4" pointerEvents={count > 0 ? "visiblePainted" : "none"} />)}
          </g>)}
          {group === "full_body" && [26, 224].map(x => <g key={x} transform={`translate(${x} 15)`}>
            <path d={SILHOUETTE} clipPath={`url(#${id}-torso)`} fill="none"
              stroke={count > 0 ? "var(--anatomy-selected)" : "none"}
              strokeWidth={selected === group ? 2.5 : 1.5} pointerEvents={count > 0 ? "stroke" : "none"} />
          </g>)}
        </g>;
      })}
      <text x="117" y="541" textAnchor="middle" className="fill-muted text-[11px]">{t("sportView.body_front")}</text>
      <text x="315" y="541" textAnchor="middle" className="fill-muted text-[11px]">{t("sportView.body_back")}</text>
    </svg>
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
