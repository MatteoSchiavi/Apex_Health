"""Provider portability rules. Similar numeric scales do not imply equivalence."""
from dataclasses import asdict, dataclass
from typing import Literal

Comparability = Literal['directly_comparable', 'convertible', 'provider_context', 'incompatible', 'unknown']


@dataclass(frozen=True)
class ProviderMetric:
    provider: str
    metric: str
    classification: Comparability
    canonical_metric: str | None
    unit: str
    method: str
    rule: str


RULES = (
    ProviderMetric('garmin', 'hrv', 'directly_comparable', 'hrv_overnight_rmssd', 'ms', 'RMSSD', 'Compare only within the same provider, method, device and overnight context; rebuild baseline on a source change.'),
    ProviderMetric('whoop', 'hrv', 'directly_comparable', 'hrv_overnight_rmssd', 'ms', 'RMSSD', 'Retain WHOOP sleep measurement context; never average into a Garmin baseline.'),
    ProviderMetric('oura', 'hrv', 'directly_comparable', 'hrv_overnight_rmssd', 'ms', 'RMSSD', 'Retain Oura overnight aggregation and its own baseline.'),
    ProviderMetric('apple_healthkit', 'hrv', 'incompatible', None, 'ms', 'SDNN', 'Keep SDNN separately. No valid numeric conversion to overnight RMSSD.'),
    ProviderMetric('apple_health', 'hrv', 'incompatible', None, 'ms', 'SDNN', 'ZIP SDNN stays source-specific; no RMSSD baseline contribution.'),
    ProviderMetric('whoop', 'strain', 'provider_context', None, '0–21', 'proprietary', 'Never write WHOOP Strain into Garmin training load or Apex strain.'),
    ProviderMetric('garmin', 'load', 'provider_context', None, 'Garmin load', 'proprietary', 'One selected method per load window; never sum with Edwards TRIMP or WHOOP Strain.'),
    ProviderMetric('whoop', 'sleep_performance', 'provider_context', None, '%', 'proprietary', 'Sleep need performance is not a generic sleep-quality score.'),
    ProviderMetric('oura', 'readiness', 'provider_context', None, '0–100', 'proprietary', 'Keep Oura identity; never replace Apex readiness.'),
    ProviderMetric('whoop', 'recovery', 'provider_context', None, '%', 'proprietary', 'Keep WHOOP identity; never replace Apex recovery.'),
    ProviderMetric('garmin', 'body_battery', 'provider_context', None, '0–100', 'proprietary', 'Provider context only; no Apex energy equivalence.'),
    ProviderMetric('garmin', 'stress', 'provider_context', None, '0–100', 'proprietary', 'Provider context only; vendor stress scales are not merged.'),
    ProviderMetric('garmin', 'recovery_time', 'provider_context', None, 'min', 'proprietary', 'Recorded provider estimate; no guaranteed recovery prediction.'),
    ProviderMetric('all', 'sleep_stages', 'provider_context', None, 's', 'vendor_estimate', 'Select one coherent night/source; do not mix vendor stage proportions or claim clinical architecture.'),
    ProviderMetric('all', 'vo2max', 'provider_context', None, 'ml/kg/min', 'vendor_estimate', 'Same units do not establish interchangeable calibration; keep provider identity.'),
    ProviderMetric('whoop', 'energy_kj', 'convertible', 'calories', 'kJ', 'recorded_estimate', 'Convert kJ to kcal with 4.184 kJ/kcal; conversion changes units, not estimator validity.'),
)


def provider_semantics(provider: str, metric: str) -> ProviderMetric:
    return next((r for r in RULES if r.provider == provider and r.metric == metric),
        next((r for r in RULES if r.provider == 'all' and r.metric == metric),
             ProviderMetric(provider, metric, 'unknown', None, '', 'unknown', 'Unknown semantics cannot feed a generic Apex score.')))


def semantic_catalog():
    return [asdict(r) for r in RULES]
