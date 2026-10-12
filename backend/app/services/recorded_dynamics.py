"""Unit-qualified recorded running sensors; no inferred measurements."""
from math import isfinite

DYNAMICS_FIELDS = {
    "ground_contact_time_ms": ("ms",20,1500), "vertical_oscillation_cm": ("cm",0,50),
    "stride_length_m": ("m",0,5), "step_length_m": ("m",0,5),
    "vertical_ratio_pct": ("%",0,100), "left_ground_contact_balance_pct": ("%",0,100),
    "ground_contact_balance_pct": ("%",0,100),
}


def canonical_dynamics(values):
    if not isinstance(values,dict):
        return {}
    out = {}
    for name,(_,lower,upper) in DYNAMICS_FIELDS.items():
        value = values.get(name)
        if isinstance(value,bool):
            continue
        try:
            value = float(value)
        except (TypeError,ValueError,OverflowError):
            continue
        if isfinite(value) and lower <= value <= upper:
            out[name] = value
    return out


# FIT profile units are available on decoded FieldData and checked explicitly.
# avg_step_length is a step length, never inferred/relabelled as a stride.
FIT_DYNAMICS = {
    "avg_stance_time":("ground_contact_time_ms","ms",1),
    "avg_vertical_oscillation":("vertical_oscillation_cm","mm",.1),
    "avg_step_length":("step_length_m","mm",.001),
    "avg_vertical_ratio":("vertical_ratio_pct","percent",1),
    "avg_stance_time_balance":("ground_contact_balance_pct","percent",1),
}


def decoded_fit_dynamics(fields):
    values,provenance = {},{}
    for field in fields:
        spec = FIT_DYNAMICS.get(field.name)
        if spec is None or getattr(field,"units",None) != spec[1] or isinstance(field.value,bool):
            continue
        name,unit,scale = spec
        try:
            value = float(field.value)*scale
        except (TypeError,ValueError,OverflowError):
            continue
        valid = canonical_dynamics({name:value})
        if valid:
            values.update(valid)
            provenance[name] = {"upstream_field":field.name,"upstream_unit":unit,"canonical_unit":DYNAMICS_FIELDS[name][0],
                "conversion_factor":scale,"method":"decoded_FIT_profile_units"}
    return values,provenance


def explicit_summary_dynamics(payload):
    """Accept canonical suffix-qualified fields; generic Garmin aliases need units."""
    values = canonical_dynamics(payload.get("running_dynamics"))
    provenance = {k:{"upstream_field":"running_dynamics."+k,"canonical_unit":DYNAMICS_FIELDS[k][0],"method":"explicit_unit_qualified_field"} for k in values}
    aliases = {"avgGroundContactTime":("ground_contact_time_ms","ms",1),
        "avgVerticalOscillation":("vertical_oscillation_cm","cm",1),
        "avgStrideLength":("stride_length_m","cm",.01),
        "avgVerticalRatio":("vertical_ratio_pct","%",1)}
    units = payload.get("field_units")
    if isinstance(units,dict):
        for upstream,(canonical,unit,scale) in aliases.items():
            if units.get(upstream) != unit or isinstance(payload.get(upstream),bool):
                continue
            try:
                value = float(payload[upstream])*scale
            except (KeyError,TypeError,ValueError,OverflowError):
                continue
            valid = canonical_dynamics({canonical:value})
            if valid:
                values.update(valid)
                provenance[canonical] = {"upstream_field":upstream,"upstream_unit":unit,"canonical_unit":DYNAMICS_FIELDS[canonical][0],"conversion_factor":scale,"method":"explicit_provider_field_units"}
    return values,provenance
