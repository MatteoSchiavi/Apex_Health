"""Public deployment facts for privacy, terms and storage notices."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.legal_config import get_legal_config

router = APIRouter(prefix="/legal", tags=["legal"])


class PublicLegalConfig(BaseModel):
    controller_name: str
    controller_address: str
    contact_email: str
    hosting_region: str
    effective_date: str
    account_basis: str
    health_basis: str
    ai_processor: str
    backup_location: str
    transfer_details: str
    details_complete: bool


@router.get("/config", response_model=PublicLegalConfig)
async def legal_config() -> PublicLegalConfig:
    config = get_legal_config()
    return PublicLegalConfig(
        controller_name=config.legal_controller_name,
        controller_address=config.legal_controller_address,
        contact_email=config.legal_contact_email,
        hosting_region=config.legal_hosting_region,
        effective_date=config.legal_effective_date,
        account_basis=config.legal_account_basis,
        health_basis=config.legal_health_basis,
        ai_processor=config.legal_ai_processor,
        backup_location=config.legal_backup_location,
        transfer_details=config.legal_transfer_details,
        details_complete=all(
            value.strip()
            for value in (
                config.legal_controller_name,
                config.legal_controller_address,
                config.legal_contact_email,
                config.legal_hosting_region,
                config.legal_effective_date,
                config.legal_account_basis,
                config.legal_health_basis,
                config.legal_ai_processor,
                config.legal_backup_location,
                config.legal_transfer_details,
            )
        ),
    )
