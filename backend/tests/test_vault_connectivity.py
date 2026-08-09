import pytest

from app.services.api_key_vault import APIKeyVault


@pytest.mark.asyncio
async def test_vault_fallback_is_encrypted_expiring_and_one_time(monkeypatch):
    class UnavailableRedis:
        async def setex(self, *args, **kwargs):
            raise RuntimeError("redis down")

        def pipeline(self, *args, **kwargs):
            raise RuntimeError("redis down")

    fake = UnavailableRedis()
    monkeypatch.setattr(APIKeyVault, "_redis", fake)
    await APIKeyVault.stash("submission", "sk-super-secret")
    encrypted, _ = APIKeyVault._local["submission"]
    assert b"sk-super-secret" not in encrypted
    assert await APIKeyVault.retrieve_and_purge("submission") == "sk-super-secret"
    assert await APIKeyVault.retrieve_and_purge("submission") is None
