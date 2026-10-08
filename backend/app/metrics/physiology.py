"""Recorded physiological context, never inferred from an SVG or a default.

Sex alone cannot identify menstrual phase, contraception, pregnancy, menopause
or hormone treatment. No general correction to Apex's heuristic scores has
been validated for those states. Keep the unknowns visible to all AI paths.
"""
from app.features.load import age_at


PHYSIOLOGY_GUIDANCE = (
    "Use recorded profile sex as context, not as a diagnosis or a reason to reduce training. "
    "Unknown or other sex must never silently select male physiological constants. "
    "Do not infer menstruation, cycle phase, contraception, pregnancy, menopause or hormone "
    "treatment from sex, dates, HRV or heart rate. Consider explicitly reported symptoms "
    "and clinician restrictions; personal baselines are not adjusted for an unrecorded cycle. "
    "Apex scores have no validated sex-specific or pregnancy-specific calibration. "
    "Use the recorded laboratory's reference intervals; do not invent male or female normal "
    "ranges, donation eligibility, nutritional requirements or sex-specific corrections."
)


def physiological_context(user, day):
    """Only current, account-owned profile facts; missing fields remain null."""
    sex = getattr(user, "sex", None)
    return {
        "sex": sex if sex in {"male", "female", "other"} else None,
        "source": "account_profile",
        "age_years": age_at(getattr(user, "dob", None), day),
        "height_cm": float(user.height_cm) if getattr(user, "height_cm", None) is not None else None,
        "reproductive_context": "not_structurally_recorded",
        "score_calibration": "shared_heuristic_not_validated_by_sex",
    }
