"""Network-free Garmin API transport contracts; no unofficial client."""
import asyncio
import pytest
from app.connectors.garmin.client import GarminAuthError, GarminClient, build_live_client
from app.connectors.garmin.personal import GarminPersonalClient
from app.connectors.garmin.transport import GarminTransport

@pytest.mark.parametrize("credentials", [None, {}, {"di_token": "retired", "di_refresh_token": "retired"}, {"email": "x", "password": "retired"}])
def test_password_sessions_never_select_a_client(credentials):
    with pytest.raises(GarminAuthError, match="Reconnect Garmin API"):
        build_live_client(credentials)

def test_only_api_credentials_build_a_transport_without_authentication():
    client = build_live_client({"auth_type": "personal_api_key", "api_key": "synthetic-key"})
    try:
        assert isinstance(client, GarminPersonalClient)
        assert isinstance(client, GarminTransport)
        assert GarminClient is GarminTransport
        assert client._access_token is None
    finally:
        asyncio.run(client.aclose())

@pytest.fixture(scope="session", autouse=True)
def migrated_database(): pass
@pytest.fixture(scope="session", autouse=True)
def owner_account(): pass
@pytest.fixture(autouse=True)
def clean_redis(): pass
