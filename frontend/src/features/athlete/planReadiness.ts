import type { PlanStructure } from "./importTypes";

/** The same date and sport requirements used when the API activates a plan. */
export function planReadiness(structure: PlanStructure, disciplines?: readonly string[]) {
  const missingDates = structure.sessions.flatMap((session, index) => session.date ? [] : [index]);
  const invalidSports = structure.sessions.flatMap((session, index) => !session.discipline || (disciplines && !disciplines.includes(session.discipline)) ? [index] : []);
  const reversedRange = !!structure.starts_on && !!structure.ends_on && structure.ends_on < structure.starts_on;
  const rangeTooLong = !!structure.starts_on && !!structure.ends_on && (Date.parse(structure.ends_on) - Date.parse(structure.starts_on)) / 86400000 > 366;
  const outsideRange = structure.sessions.flatMap((session, index) => session.date && ((structure.starts_on && session.date < structure.starts_on) || (structure.ends_on && session.date > structure.ends_on)) ? [index] : []);
  return {
    missingDates, invalidSports, reversedRange, rangeTooLong, outsideRange,
    ready: !!structure.starts_on && !!structure.ends_on && structure.sessions.length > 0 && !missingDates.length && !invalidSports.length && !reversedRange && !rangeTooLong && !outsideRange.length,
    // Incomplete dates can be retained as a draft. Invalid ranges and unknown sports cannot.
    saveable: !invalidSports.length && !reversedRange && !rangeTooLong && !(structure.starts_on && structure.ends_on && outsideRange.length),
  };
}
