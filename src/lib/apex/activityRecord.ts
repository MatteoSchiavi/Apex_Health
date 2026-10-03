import type { Activity } from "@prisma/client";
import type { ActivityCard, ActivityDetail } from "./types";

export function activityCard(a: Activity): ActivityCard {
  return {
    id: a.id, start_time: a.startTime.replace(" ", "T"), local_date: a.localDate,
    discipline: a.discipline as ActivityCard["discipline"], title: a.title,
    duration_s: a.durationS, distance_m: a.distanceM, elevation_gain_m: a.elevationGainM,
    avg_hr: a.avgHr, max_hr: a.maxHr, avg_power: a.avgPower, np_power: a.npPower,
    avg_speed_mps: a.avgSpeedMps, calories: a.calories, training_load: a.trainingLoad,
    data_completeness: a.dataCompleteness as ActivityCard["data_completeness"],
    sources: a.sources.split(",").map((s) => s.trim()).filter(Boolean),
  };
}
export function activityDetail(a: Activity): ActivityDetail {
  // This store records summaries only: never invent time-series, GPS or provenance.
  return { ...activityCard(a), has_streams: false, stream_types: [], laps: [], route: null,
    weather: null, gear: [], source_metrics: {} };
}
