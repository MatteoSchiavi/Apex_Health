"""Inspectable maturity facts; code/fixtures do not establish live support."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderSupport:
    status: str
    ingestion_implemented: bool
    normalization_implemented: bool
    fixture_tested: bool
    live_tested: bool = False
    production_supported: bool = False
    commercial_approval_required: bool | None = None
    write_back: str = 'none'
    ai_evidence_eligible: bool = False
    manual_only: bool = False
    experimental: bool = True


SUPPORT = {
    'garmin': ProviderSupport('EXPERIMENTAL', True, True, True, commercial_approval_required=True, ai_evidence_eligible=True),
    'apple_health': ProviderSupport('MANUAL_IMPORT', True, True, True, commercial_approval_required=False, manual_only=True, experimental=False),
    'apple_healthkit': ProviderSupport('DEVELOPMENT_ONLY', True, True, True, commercial_approval_required=False),
    'whoop': ProviderSupport('EXPERIMENTAL', True, True, True, commercial_approval_required=None, ai_evidence_eligible=True),
    'oura': ProviderSupport('EXPERIMENTAL', True, True, False, commercial_approval_required=None, ai_evidence_eligible=True),
    'strava': ProviderSupport('EXPERIMENTAL', True, True, True, commercial_approval_required=True),
    'coros': ProviderSupport('PENDING_PROVIDER_APPROVAL', True, True, True, commercial_approval_required=True, ai_evidence_eligible=True),
    'technogym': ProviderSupport('EXPERIMENTAL', True, True, True, commercial_approval_required=True, write_back='experimental_access_dependent', ai_evidence_eligible=True),
    'fitbit': ProviderSupport('EXPERIMENTAL', True, True, True, commercial_approval_required=None),
    'google_fit': ProviderSupport('MANUAL_IMPORT', False, False, False, commercial_approval_required=None, manual_only=True),
}


def support_for(provider: str) -> dict:
    definition = SUPPORT.get(provider, ProviderSupport('DEVELOPMENT_ONLY', False, False, False))
    return asdict(definition)
