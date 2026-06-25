import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.main import require_backend_secret


def _set_required_env(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_AGORA_APP_ID", "app-id")
    monkeypatch.setenv("NEXT_AGORA_APP_CERTIFICATE", "app-cert")


@pytest.mark.asyncio
async def test_backend_secret_dependency_allows_unprotected_local_dev(monkeypatch):
    get_settings.cache_clear()
    _set_required_env(monkeypatch)

    await require_backend_secret(None)

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_backend_secret_dependency_rejects_missing_or_wrong_secret(monkeypatch):
    get_settings.cache_clear()
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BACKEND_API_SECRET", "shared-secret")

    with pytest.raises(HTTPException) as missing:
        await require_backend_secret(None)
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as wrong:
        await require_backend_secret("wrong-secret")
    assert wrong.value.status_code == 401

    await require_backend_secret("shared-secret")

    get_settings.cache_clear()
