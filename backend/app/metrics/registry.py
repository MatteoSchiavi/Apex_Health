"""Authoritative metric semantics; localized education remains a presentation adapter.

A formula's existence is not evidence of predictive or clinical validation.
Versions identify the implemented functional form, independent of selected
feature_weights versions. Observed personal ranges are not clinical cutoffs.
"""
from dataclasses import asdict, dataclass, replace as _replace
from typing import Literal

MetricKind = Literal["measured", "provider", "derived", "heuristic"]


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    display_name: str
    category: str
    description: str
    unit: str
    kind: MetricKind
    validation_level: str
    formula_version: str | None
    formula: str
    input_metrics: tuple[str, ...]
    minimum_data_requirements: str
    missing_data_behavior: str
    baseline_requirements: str
    source_requirements: str
    interpretation: str
    limitations: tuple[str, ...]
    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]
    model: str | None = None
    column: str | None = None
    scale: float = 1.0
    direction: str = "band"
    display_type: str = "trend"
    catalog: bool = True
    sex_handling: str = "Shared descriptive arithmetic; no sex-specific coefficient or population normal range."

    @property
    def semantic_type(self) -> str:
        return {"measured": "measured", "provider": "provider_proprietary",
                "derived": "apex_derived", "heuristic": "apex_heuristic"}[self.kind]

    def to_dict(self) -> dict:
        return {**asdict(self), "semantic_type": self.semantic_type}


_NO_CLINICAL = ("Diagnoses disease", "Predicts individual injury or illness probability",
                "Defines a universal healthy target", "Proves a causal physiological change")
_MISSING = "Absent inputs stay absent. Weighted composites renormalize available, configured components; no usable components yields null."
_BASELINE = "Prior 28 local days, excluding today; arithmetic mean of observed days, minimum 7 observations. Missing days are excluded, never zero-filled."
_SOURCE = "Use persisted canonical observations; disclose unavailable provider attribution. No inferred provider, clinical confidence, or retrospective constituents."
_HEURISTIC_LIMITS = ("Heuristic functional constants and blends have no prospective individual clinical validation.",
                     "Missing components change the effective weights and comparability across days.",
                     "Sensor method, vendor, and measurement context can change the result.")


def _derived(key, name, column, unit, formula, inputs, *, kind="derived", category="training",
             baseline="None.", minimum="All formula operands must be available.", missing="Unavailable operands yield null.",
             limitations=(), direction="band", catalog=True, model="feature", validation=None):
    return MetricDefinition(
        id=key, display_name=name, category=category, description=formula, unit=unit,
        kind=kind, validation_level=validation or ("heuristic" if kind == "heuristic" else "deterministic_derived"),
        formula_version=f"{key}-v1", formula=formula, input_metrics=tuple(inputs),
        minimum_data_requirements=minimum, missing_data_behavior=missing,
        baseline_requirements=baseline, source_requirements=_SOURCE,
        interpretation="Descriptive comparison within the recorded method and context; interpret alongside coverage and history.",
        limitations=tuple(limitations) + (_HEURISTIC_LIMITS if kind == "heuristic" else ("Derived arithmetic is descriptive; method compatibility, capture coverage and sensor quality limit interpretation.",)),
        allowed_claims=("Describes the persisted inputs under the stated formula and method",),
        prohibited_claims=_NO_CLINICAL, model=model, column=column, direction=direction, catalog=catalog,
        sex_handling=("Shared heuristic using personal inputs; no validated male/female, cycle or pregnancy calibration."
                      if kind == "heuristic" else "Shared descriptive arithmetic; no sex-specific coefficient or population normal range."),
    )


def _observed(key, name, model, column, unit, *, provider=False, scale=1., direction="band", display_type="trend", catalog=True):
    return MetricDefinition(
        id=key, display_name=name, category="wellness", description=f"Recorded {name.lower()} observation.",
        unit=unit, kind="provider" if provider else "measured",
        validation_level="experimental" if provider else "measured", formula_version=None,
        formula="Provider-specific calculation is unavailable." if provider else "Recorded value; any display conversion is declared by scale.",
        input_metrics=(), minimum_data_requirements="A finite, eligible recorded observation on the assessed date.",
        missing_data_behavior="No observation yields null; do not invent a reading or provider attribution.",
        baseline_requirements="Personal P10–P90 displays are observed history, not clinical normal ranges.",
        source_requirements="Retain provider and measurement-method identity when persisted; incompatible provider quantities are not interchangeable.",
        interpretation="Provider-specific context." if provider else "Observation interpreted in its measurement context.",
        limitations=("Provider attribution can be unavailable in legacy canonical observations.",
                     "Different devices or methods can disagree; no clinical diagnostic claim.") +
                    (("Proprietary algorithm and calibration are not available to Apex.",) if provider else ()),
        allowed_claims=("Reports an observed recorded value",), prohibited_claims=_NO_CLINICAL +
                      (("Equivalent to an Apex score", "Interchangeable across proprietary provider scales") if provider else ()),
        model=model, column=column, scale=scale, direction=direction, display_type=display_type, catalog=catalog,
        sex_handling=("Retain vendor estimate; vendor use of sex is unknown to Apex. Do not recalculate or apply a sex multiplier."
                      if provider else "Retain recorded measurement; personal history is not a sex-specific clinical normal range."),
    )


METRIC_REGISTRY: dict[str, MetricDefinition] = {}


def _register(definition):
    if definition.id in METRIC_REGISTRY:
        raise ValueError(f"Duplicate metric definition: {definition.id}")
    METRIC_REGISTRY[definition.id] = definition


for args in (
    ("resting_hr", "Resting heart rate", "biometric", "resting_hr", "bpm", False, 1., "down", "range"),
    ("hrv_ms", "HRV", "hrv", None, "ms", False, 1., "band", "range"),
    ("respiration", "Respiration", "sleep", "respiration_avg", "br/min", False, 1., "band", "range"),
    ("spo2", "Oxygen saturation", "biometric", "spo2_avg", "%", False, 1., "up", "range"),
    ("weight", "Body mass", "biometric", "weight_kg", "kg", False, 1., "band", "absolute"),
    ("body_fat", "Body fat estimate", "biometric", "body_fat_pct", "%", True, 1., "band", "absolute"),
    ("vo2max", "VO2max estimate", "biometric", "vo2max", "ml/kg/min", True, 1., "up", "trend"),
    ("steps", "Steps", "biometric", "steps", "steps", False, 1., "up", "absolute"),
    ("floors", "Floors", "biometric", "floors", "floors", False, 1., "up", "absolute"),
    ("hydration", "Recorded hydration", "biometric", "hydration_ml", "ml", False, 1., "up", "absolute"),
    ("sleep_duration", "Sleep duration", "sleep", "total_sleep_s", "h", False, 3600., "band", "trend"),
    ("provider_sleep_score", "Provider sleep score", "sleep", "sleep_score", "/100", True, 1., "band", "trend"),
    ("sleep_deep", "Estimated deep sleep", "sleep", "deep_s", "h", True, 3600., "band", "absolute"),
    ("sleep_rem", "Estimated REM sleep", "sleep", "rem_s", "h", True, 3600., "band", "absolute"),
    ("sleep_light", "Estimated light sleep", "sleep", "light_s", "h", True, 3600., "band", "absolute"),
    ("restlessness", "Provider restlessness", "sleep", "restlessness", "%", True, 1., "down", "trend"),
):
    key, name, model, column, unit, provider, scale, direction, display = args
    _register(_observed(key, name, model, column, unit, provider=provider, scale=scale, direction=direction, display_type=display))

for key, name, column, formula, inputs in (
    ("recovery", "Recovery estimate", "recovery_score", "100 × weighted mean of clamp(0.5+HRV deviation%/50), clamp(1−resting-HR deviation/10), Apex sleep architecture/100 and 1−prior strain/100.", ("hrv_deviation", "resting_hr_deviation", "sleep_score", "prior_day_strain")),
    ("sleep_score", "Sleep architecture estimate", "sleep_architecture_score", "100 × weighted mean of clamp((REM%−10)/15), clamp((deep%−10)/13), and sleep/(sleep+awake). Clamp bounds are 0..1.", ("rem_pct", "deep_pct", "total_sleep_s", "awake_s")),
    ("readiness", "Readiness estimate", "readiness_score", "100 × weighted mean of recovery/100, sleep architecture/100 and a heuristic ACWR transform: ratio/0.8 below 0.8; 1 from 0.8..1.3; clamp(1−(ratio−1.3)/0.7) above 1.3.", ("recovery", "sleep_score", "acwr")),
    ("systemic_stress", "Systemic stress signal", "systemic_stress_signal", "100 × weighted mean of clamp(−HRV deviation%/30), clamp(resting-HR deviation/8), clamp(respiration deviation%/10), and journal soreness/fatigue. This describes signals, not illness probability.", ("hrv_deviation", "resting_hr_deviation", "respiration_deviation", "journal_soreness_fatigue")),
    ("load_spike", "Load spike indicator", "load_spike_indicator", "100 × weighted mean of clamp((ACWR−1.3)/0.7) and clamp((today's load−prior 28-day mean)/(2×population SD)). Load-spike component is unavailable while fewer than 7 prior active days exist; with zero SD it is 1 only above the mean.", ("acwr", "day_load", "load_distribution_mean", "load_distribution_std", "active_days")),
):
    _register(_derived(key, name, column, "/100", formula, inputs, kind="heuristic", category="wellness",
                       baseline=_BASELINE if key in {"recovery", "systemic_stress"} else "See each component's persisted baseline/window.",
                       minimum="At least one available component with a configured positive-weight sum.", missing=_MISSING,
                       direction="down" if key in {"systemic_stress", "load_spike"} else "up"))

_register(_derived("strain", "Strain estimate", "strain_score", "/100", "clamp(today's selected-method load / max(28-day peak including today, 300) × 100, 0, 100).", ("day_load", "peak28"), kind="heuristic", baseline="Peak over [D−27,D]; ceiling floor 300 in the selected load units.", minimum="Selected load method and declared coverage.", missing="Null without selected-method session evidence. Days without recorded sessions are descriptive zero only after source history; excluded session loads remain unknown and coverage is partial.", limitations=("The 300-unit floor is a heuristic and is not calibrated equivalently across Edwards and Garmin units.",)))
for key, name, column, days, formula in (
    ("acute_load", "Acute load", "training_load_acute", 7, "Sum of selected-method session loads in [D−6,D]."),
    ("chronic_load", "Chronic load", "training_load_chronic", 28, "Sum of selected-method session loads in [D−27,D] / 4, on the same weekly scale as acute load."),
):
    _register(_derived(key, name, column, "load/week", formula, ("session_loads",), baseline=f"{days} local days including today.", minimum="Selected-method session evidence and one consistent load method for both windows, coverage declared.", missing="Null without eligible load evidence. No recorded session is descriptive zero only with source history; incompatible/missing session loads are excluded and disclosed, not assumed to be rest.", limitations=("Garmin proprietary load and Edwards TRIMP are distinct scales with no validated conversion.", "A method switch changes comparability and incomplete capture undercounts load.")))
_register(_derived("acwr", "Acute:chronic load ratio", "acwr", "ratio", "acute_load / chronic_load, with chronic_load = 28-day selected-method sum / 4.", ("acute_load", "chronic_load"), minimum="Finite same-method acute load and positive chronic load from the same calculation row.", missing="Null when chronic load is zero or operands are unavailable.", limitations=("Descriptive overlapping-window ratio; not a validated individual injury predictor.", "No universal optimal or healthy ratio band.", "Missing sessions and switching load methods affect the ratio.")))
_register(_derived("hrv_baseline", "Personal HRV baseline", None, "ms", "Arithmetic mean of eligible prior daily HRV observations.", ("hrv_ms",), category="wellness", baseline=_BASELINE, minimum="7 observed prior days.", catalog=False, limitations=("RMSSD and SDNN are incompatible. Only the same origin/method/device and overnight or daytime context can support a comparable baseline; source changes rebuild coverage. Device identity is not currently persisted.",)))
for key, name, column, formula, inputs, unit in (
    ("hrv_deviation", "HRV deviation", "hrv_deviation_from_baseline", "100 × (today HRV − prior baseline) / prior baseline.", ("hrv_ms", "hrv_baseline"), "%"),
    ("resting_hr_deviation", "Resting-HR deviation", None, "Today resting HR − prior observed-day mean.", ("resting_hr", "resting_hr_baseline"), "bpm"),
    ("respiration_deviation", "Respiration deviation", None, "100 × (today respiration − prior baseline) / prior baseline.", ("respiration", "respiration_baseline"), "%"),
):
    _register(_derived(key, name, column, unit, formula, inputs, category="wellness", baseline=_BASELINE,
                       minimum="Today's eligible observation and 7 prior observed days; positive denominator for percentage deviation.", catalog=column is not None))
_register(_derived("cross_discipline_fatigue", "Cross-discipline load carryover", "cross_discipline_fatigue_index", "index", "Sum across active disciplines of Σ(last 7 daily loads × 0.5^(days_ago/3)) / max(own prior 28-day peak including today,1).", ("discipline_daily_loads",), kind="heuristic", baseline="Per-discipline [D−27,D] peak including today; half-life 3 days.", minimum="At least one discipline with selected-method positive load in the last 7 days.", missing="Null when no discipline is active; no imputed session loads.", catalog=False))
for key, name, column, unit, formula, inputs, minimum, limits in (
    ("efficiency_factor", "Efficiency factor", "efficiency_factor", "W/bpm", "Normalized power / time-weighted mean HR (summary HR fallback); per-day arithmetic mean across eligible sessions.", ("power_stream", "hr_stream", "average_hr"), "Road cycling with power and positive recorded HR.", ("Context-specific cycling power/HR efficiency proxy, not physiological efficiency measurement.",)),
    ("aerobic_decoupling", "Aerobic decoupling", "aerobic_decoupling_pct", "%", "100 × (first-half NP/HR − second-half NP/HR) / (first-half NP/HR); per-day mean of eligible sessions.", ("power_stream", "hr_stream"), "Duration ≥1200s; ≥2 power samples per half; positive half HR; variability index ≤1.05 when available.", ("Physiological interpretation is experimental; not a diagnostic assessment.", "Discipline rows are separate; temperature, hydration, pacing and sensor quality affect drift.")),
    ("estimated_ftp", "Protocol-based FTP estimate", "estimated_ftp", "W", "0.95 × best rolling 1200-second mean power using sample-and-hold integration; daily maximum across eligible sessions.", ("power_stream", "ftp_model_type"), "Discipline twenty_min_protocol configuration and at least 1200s with recorded power.", ("A qualifying window is not proof that a maximal FTP test protocol was performed.", "Protocol-specific estimate; not a lab or independently validated individual threshold.")),
):
    _register(_derived(key, name, column, unit, formula, inputs, minimum=minimum, limitations=limits,
                       catalog=False, model="discipline", validation="experimental" if key == "aerobic_decoupling" else "established_formula"))
for key, name in (("provider_readiness", "Provider readiness"), ("provider_recovery", "Provider recovery"), ("provider_strain", "Provider strain"), ("provider_body_battery", "Garmin Body Battery")):
    _register(_observed(key, name, "biometric", "source_metrics", "provider scale", provider=True, catalog=False))


def metric_catalog() -> dict[str, dict]:
    """Numeric lookup adapter used by API queries; no parallel scientific table."""
    return {key: {"model": spec.model, "unit": spec.unit, "direction": spec.direction,
                  **({"column": spec.column} if spec.column else {}),
                  **({"scale": spec.scale} if spec.scale != 1 else {})}
            for key, spec in METRIC_REGISTRY.items() if spec.catalog}

# Versioned behavior changes: absent cold-start load component and corrected half offsets.
METRIC_REGISTRY["load_spike"] = _replace(METRIC_REGISTRY["load_spike"], formula_version="load-spike-v2")
METRIC_REGISTRY["aerobic_decoupling"] = _replace(METRIC_REGISTRY["aerobic_decoupling"], formula_version="aerobic-decoupling-v2")

METRIC_REGISTRY["recovery"] = _replace(METRIC_REGISTRY["recovery"], formula_version="recovery-v2", source_requirements="HRV baseline uses one origin/method/overnight-or-daytime context; sleep quality is Apex architecture from one coherent night, never a proprietary provider sleep score.")
_register(_observed("whoop_sleep_performance", "WHOOP sleep performance", "biometric", "source_metrics", "%", provider=True, catalog=False))
