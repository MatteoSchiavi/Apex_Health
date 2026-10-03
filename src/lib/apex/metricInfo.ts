/**
 * Metric explanations — the four-section content for every metric's InfoButton.
 * Used by the Biometrics metric page (and any KPI tile that wants inline context).
 *
 * Keep each field short (1–3 sentences). The InfoButton popover is ~280px wide.
 */
export interface MetricExplanation {
  whatItMeasures: string;
  whyItMatters: string;
  whatInfluencesIt: string;
  howToReadIt: string;
}

export const METRIC_EXPLANATIONS: Record<string, MetricExplanation> = {
  readiness: {
    whatItMeasures: "A 0–100 synthesis score combining your sleep, HRV, resting heart rate and recent training load into a single 'how ready are you' number.",
    whyItMatters: "It's the headline answer to 'should I train hard today or back off?'. A low score means your body is still recovering; a high score means you're primed.",
    whatInfluencesIt: "Sleep quality and duration, HRV vs your baseline, resting HR, how hard you trained yesterday, illness, stress, alcohol, travel.",
    howToReadIt: "≥75 good to train hard · 50–74 moderate — prefer easy work · <50 prioritise recovery. Watch the 7-day trend, not just today.",
  },
  recovery: {
    whatItMeasures: "A 0–100 score reflecting how recovered your body is, based mainly on overnight autonomic signals (HRV, resting HR) versus your personal baseline.",
    whyItMatters: "It tells you whether last night's rest actually repaired you — independent of how hard you plan to train today.",
    whatInfluencesIt: "Sleep depth and duration, HRV, resting HR, late-night alcohol or food, stress, illness onset.",
    howToReadIt: "Higher is better. A 7-day drop below your norm is an early warning sign before readiness collapses.",
  },
  strain: {
    whatItMeasures: "A 0–100 score of how much load you've asked of your body over the last 24 hours — across all activities.",
    whyItMatters: "Pair it with recovery: high strain + low recovery = accumulating fatigue; high strain + high recovery = a productive day.",
    whatInfluencesIt: "Total training load, activity duration, intensity, non-exercise stress, how much you moved outside workouts.",
    howToReadIt: "There's no 'good' or 'bad' strain in isolation — read it against recovery. A strain that's normal for you may be too much when recovery is low.",
  },
  sleep_score: {
    whatItMeasures: "A 0–100 score for last night's sleep, computed from total duration and the deep+REM ratio (the most restorative stages).",
    whyItMatters: "Sleep is the single biggest recovery lever. A low score usually predicts a lower readiness the next morning.",
    whatInfluencesIt: "Bedtime consistency, total duration, alcohol/caffeine late in the day, room temperature, screen time before bed, training load.",
    howToReadIt: "≥75 good · 50–74 fair · <50 poor. The trend matters more than any single night — one bad night is normal.",
  },
  hrv_ms: {
    whatItMeasures: "Heart Rate Variability — the millisecond variation between heartbeats, measured overnight. Higher generally means a more recovered autonomic nervous system.",
    whyItMatters: "HRV is an early-warning signal: it often drops a day or two before you feel overtired or get sick.",
    whatInfluencesIt: "Sleep, stress, alcohol, training intensity, illness, heat, dehydration, genetics (your baseline is personal).",
    howToReadIt: "Compare to YOUR baseline, not population norms. A drop of more than ~1 SD (≈8ms for most) is meaningful; small daily noise is normal.",
  },
  hrv_deviation: {
    whatItMeasures: "How far today's HRV sits from your 30-day rolling baseline, as a percentage. Negative = below baseline (more fatigue), positive = above (more ready).",
    whyItMatters: "Raw HRV is personal; the deviation tells you the direction and magnitude of change in a way you can compare across days.",
    whatInfluencesIt: "Same as HRV: sleep, stress, training, alcohol, illness onset.",
    howToReadIt: "Within ±1 SD is normal noise. A sustained drop below baseline for 3+ days is an early warning to prioritise recovery.",
  },
  resting_hr: {
    whatItMeasures: "Your resting heart rate — the lowest sustained HR overnight or just before waking, in beats per minute.",
    whyItMatters: "A lower RHR generally means better cardiovascular fitness. A sudden rise above your baseline often signals fatigue, stress or impending illness.",
    whatInfluencesIt: "Fitness level, sleep, stress, dehydration, alcohol, caffeine, illness, overtraining.",
    howToReadIt: "Track against YOUR baseline. A rise of >5 bpm for several days is meaningful; single-day jumps are noise.",
  },
  spo2_avg: {
    whatItMeasures: "Average blood oxygen saturation (SpO₂) overnight, as a percentage. Normal is 95–100%.",
    whyItMatters: "Low SpO₂ during sleep can indicate breathing issues (apnea, altitude, respiratory illness) that hurt recovery without you noticing.",
    whatInfluencesIt: "Altitude, respiratory conditions, sleep position, asthma, smoking, alcohol.",
    howToReadIt: "≥95% normal · 90–94% mild desaturation, worth watching · <90% talk to a doctor, especially if recurring.",
  },
  respiration_avg: {
    whatItMeasures: "Average breathing rate overnight, in breaths per minute. Normal adult range is 12–20.",
    whyItMatters: "Elevated overnight breathing can signal stress, illness onset, or poor sleep quality; very low rates can occur in deep sleep.",
    whatInfluencesIt: "Stress, illness, fever, anxiety, sleep stage, alcohol, fitness level.",
    howToReadIt: "Compare to your baseline. A sustained rise of more than ~2 breaths/min can be an early fatigue or illness marker.",
  },
  weight_kg: {
    whatItMeasures: "Body weight, in kilograms. Best taken in the morning after waking, before eating or drinking.",
    whyItMatters: "Useful for tracking body composition trends (muscle gain, fat loss, hydration). Daily fluctuations are mostly water.",
    whatInfluencesIt: "Hydration, glycogen, sodium intake, time of day, menstrual cycle, bowel contents, recent training.",
    howToReadIt: "Ignore day-to-day noise. Look at the 7-day and 28-day averages — a trend over weeks is real signal, a 1kg jump in a day is water.",
  },
  vo2max: {
    whatItMeasures: "Estimated maximal oxygen uptake (mL/kg/min) — the gold-standard measure of cardiorespiratory fitness, estimated by your watch from running/cycling performance.",
    whyItMatters: "Higher VO₂max is strongly associated with longevity and endurance performance. It's one of the most actionable fitness markers.",
    whatInfluencesIt: "Consistent endurance training (especially intervals), total training volume, body weight, genetics, age, altitude exposure.",
    howToReadIt: "Higher is better. Trends over months matter — a sustained decline without a training change warrants attention.",
  },
  acute_load: {
    whatItMeasures: "Your training load over the last 7 days (weighted TRIMP). Represents the short-term fatigue you're carrying right now.",
    whyItMatters: "It's the numerator of the ACWR — the 'acute' side. Combined with chronic load, it tells you if you're pushing too much or too little.",
    whatInfluencesIt: "All training sessions in the last 7 days (duration × intensity), plus any non-exercise physical stress.",
    howToReadIt: "Read it relative to chronic load, not in isolation. A number that's normal for you might be too much if chronic load just dropped.",
  },
  chronic_load: {
    whatItMeasures: "Your training load over the last 28 days divided by four, in weekly units. Represents the fitness base you've built.",
    whyItMatters: "It's the denominator of the ACWR — the 'chronic' side. Higher chronic load means more capacity to absorb acute work.",
    whatInfluencesIt: "Consistent training over the last 4 weeks. Takes ~4 weeks to meaningfully change.",
    howToReadIt: "Rises slowly with consistent training. A sudden drop (injury, travel) means you can no longer safely absorb the same acute load.",
  },
  acwr: {
    whatItMeasures: "Acute:Chronic Workload Ratio — the 7-day load divided by the weekly average of the last 28 days. Steady training gives a ratio near 1.",
    whyItMatters: "A ratio in the 0.8–1.3 'sweet spot' balances fitness and freshness. Above 1.5 dramatically increases injury risk.",
    whatInfluencesIt: "Sudden increases in training volume/intensity, returning from a break, racing spikes, reduced recovery.",
    howToReadIt: "0.8–1.3 optimal · 1.3–1.5 elevated — ease back · >1.5 high injury-risk zone · <0.8 undertraining (detraining risk).",
  },
  steps: {
    whatItMeasures: "Total step count for the day, from your watch or phone.",
    whyItMatters: "Daily movement (even outside workouts) supports recovery, metabolism and longevity. Consistent low step counts on rest days can actually slow recovery.",
    whatInfluencesIt: "Workouts, walking, occupation, transport choices, weather, motivation.",
    howToReadIt: "8,000–10,000/day is a good general target. On rest days, light walking (3,000–5,000) aids recovery better than total inactivity.",
  },

  /* --- Catalog-key aliases. The `metricCatalog` in lib/apex/data.ts uses
   *     short keys (hrv, spo2, respiration, weight) while the legacy
   *     explanations above used the suffixed backend keys (hrv_ms, spo2_avg,
   *     respiration_avg, weight_kg). Add aliases so getMetricExplanation()
   *     resolves either form. Existing entries are NOT overwritten. */

  hrv: {
    whatItMeasures: "Heart Rate Variability (RMSSD) — the millisecond variation between heartbeats, measured overnight. Higher generally means a more recovered autonomic nervous system.",
    whyItMatters: "HRV is an early-warning signal: it often drops a day or two before you feel overtired or get sick.",
    whatInfluencesIt: "Sleep, stress, alcohol, training intensity, illness, heat, dehydration, genetics (your baseline is personal).",
    howToReadIt: "Compare to YOUR baseline, not population norms. A drop of more than ~1 SD (≈8ms for most) is meaningful; small daily noise is normal.",
  },
  spo2: {
    whatItMeasures: "Average blood oxygen saturation (SpO₂) overnight, as a percentage. Normal is 95–100%.",
    whyItMatters: "Low SpO₂ during sleep can indicate breathing issues (apnea, altitude, respiratory illness) that hurt recovery without you noticing.",
    whatInfluencesIt: "Altitude, respiratory conditions, sleep position, asthma, smoking, alcohol.",
    howToReadIt: "≥95% normal · 90–94% mild desaturation, worth watching · <90% talk to a doctor, especially if recurring.",
  },
  respiration: {
    whatItMeasures: "Average breathing rate overnight, in breaths per minute. Normal adult range is 12–20.",
    whyItMatters: "Elevated overnight breathing can signal stress, illness onset, or poor sleep quality; very low rates can occur in deep sleep.",
    whatInfluencesIt: "Stress, illness, fever, anxiety, sleep stage, alcohol, fitness level.",
    howToReadIt: "Compare to your baseline. A sustained rise of more than ~2 breaths/min can be an early fatigue or illness marker.",
  },
  weight: {
    whatItMeasures: "Body weight, in kilograms. Best taken in the morning after waking, before eating or drinking.",
    whyItMatters: "Useful for tracking body composition trends (muscle gain, fat loss, hydration). Daily fluctuations are mostly water.",
    whatInfluencesIt: "Hydration, glycogen, sodium intake, time of day, menstrual cycle, bowel contents, recent training.",
    howToReadIt: "Ignore day-to-day noise. Look at the 7-day and 28-day averages — a trend over weeks is real signal, a 1kg jump in a day is water.",
  },

  /* --- New metrics present in the catalog but not in the original list. */

  skin_temp: {
    whatItMeasures: "Skin temperature variance — the deviation of overnight skin temperature from your personal baseline, in °C.",
    whyItMatters: "Skin temp deviations can flag illness onset (a rise often precedes a fever by 1–2 days), menstrual cycle phase, or a too-warm bedroom degrading sleep.",
    whatInfluencesIt: "Room temperature, bedding, menstrual cycle, illness, alcohol, hot showers before bed, fever.",
    howToReadIt: "Small nightly swings (±0.3 °C) are normal. A sustained rise of >0.5 °C for several nights, especially with HRV dropping, can be an early illness signal.",
  },
  sleep_efficiency: {
    whatItMeasures: "Sleep efficiency — time asleep divided by time in bed, as a percentage.",
    whyItMatters: "Even with 8h in bed, low efficiency (lots of tossing or wake-ups) means less restorative sleep. It's a quick quality signal beyond raw duration.",
    whatInfluencesIt: "Stress, caffeine late in the day, alcohol, irregular schedule, screen time, room temperature, sleep disorders.",
    howToReadIt: "≥85% good · 75–84% fair · <75% poor. Track the trend — one bad night is normal, a week below 80% means look at sleep hygiene.",
  },
  deep_sleep: {
    whatItMeasures: "Total time spent in deep (N3 / slow-wave) sleep per night, in hours. Deep sleep is the most physically restorative stage.",
    whyItMatters: "Deep sleep is when growth hormone peaks and the body repairs muscle and clears metabolic waste. Low deep sleep impairs physical recovery.",
    whatInfluencesIt: "Total sleep duration, intense training (increases deep sleep demand), alcohol (suppresses it), age (declines with age), heat exposure.",
    howToReadIt: "Adults typically get 1–2h. There's no single 'good' number — track against YOUR baseline. A sustained drop after heavy training can mean under-recovery.",
  },
  rem_sleep: {
    whatItMeasures: "Total time spent in REM (rapid eye movement) sleep per night, in hours. REM is the mentally restorative stage tied to memory and emotion.",
    whyItMatters: "REM consolidates memory, learning and emotional regulation. Chronic low REM affects cognition and mood.",
    whatInfluencesIt: "Total sleep duration (REM dominates the second half of the night), alcohol, antidepressants, stress, irregular wake times.",
    howToReadIt: "Adults typically get 1.5–2h. If you're cutting sleep short you're cutting REM disproportionately. Watch the trend, not single nights.",
  },
  total_sleep: {
    whatItMeasures: "Total sleep per night — the sum of all sleep stages (deep, REM, light), in hours.",
    whyItMatters: "Sleep is the single biggest recovery lever. Chronic short sleep degrades HRV, raises resting HR, lowers readiness, and increases injury risk.",
    whatInfluencesIt: "Bedtime consistency, screen time before bed, caffeine timing, room environment, schedule, stress, training load.",
    howToReadIt: "Most adults need 7–9h. The trend matters more than any single night — if 7-day average drops below ~7h, prioritise an earlier bedtime.",
  },
  hrv_norm: {
    whatItMeasures: "HRV 30-day norm — your rolling 30-day average HRV (ms). It's your personal autonomic baseline, not today's reading.",
    whyItMatters: "Single-night HRV is noisy. The 30-day norm is the reference point against which today's HRV deviation makes sense.",
    whatInfluencesIt: "Consistent sleep, training habits, stress baseline, age, genetics. Changes slowly (weeks) with sustained lifestyle shifts.",
    howToReadIt: "Use it as YOUR baseline — compare today's HRV (or hrv_deviation) against this. A rising 30-day norm over months reflects improving fitness/recovery capacity.",
  },
};

/** Get an explanation for a metric key, with a graceful fallback. */
export function getMetricExplanation(key: string): MetricExplanation {
  return (
    METRIC_EXPLANATIONS[key] ?? {
      whatItMeasures: "This metric is tracked by your connected device.",
      whyItMatters: "Tracking the trend over time is more useful than any single day's value.",
      whatInfluencesIt: "Sleep, stress, training, nutrition, hydration and illness all play a role.",
      howToReadIt: "Compare each value to your personal baseline, not to population norms. Watch the 7-day and 28-day trends.",
    }
  );
}
