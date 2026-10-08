from unittest.mock import patch

import pytest


@pytest.fixture
def empty_event(event):
    return event


@pytest.mark.django_db
def test_voxbento_disconnect_concurrency(empty_event):
    import redis.exceptions

    from interpretation.backends.voxbento_credentials import VoxbentoError, clear_voxbento_credentials
    from interpretation.models import VoxbentoOAuthGrant

    grant = VoxbentoOAuthGrant(event=empty_event)
    grant.save()

    with patch(
        "interpretation.backends.voxbento_oauth._get_cache_lock",
        side_effect=redis.exceptions.LockError("Lock already held"),
    ):
        with pytest.raises(VoxbentoError, match="The integration is currently syncing"):
            clear_voxbento_credentials(empty_event)


@pytest.mark.django_db
def test_voxbento_refresh_disconnect_concurrency(empty_event):
    from datetime import timedelta

    from django.utils import timezone

    from interpretation.backends.voxbento_oauth import VoxbentoReauthorizationRequired, get_valid_access_token
    from interpretation.models import VoxbentoOAuthGrant

    gs = type("GS", (), {"settings": {"voxbento_client_id": "test", "voxbento_client_secret": "secret"}})()

    empty_event.settings.set("interpretation_voxbento_base_url", "https://voxbento.test")

    grant = VoxbentoOAuthGrant(
        event=empty_event,
        access_token="old_access",
        refresh_token="old_refresh",
        expires_at=timezone.now() - timedelta(minutes=10),
    )
    grant.save()

    class MockResponse:
        status_code = 200
        ok = True

        def json(self):
            grant.refresh_from_db()
            grant.is_disconnected = True
            grant.save(update_fields=["is_disconnected"])

            return {"access_token": "new_access", "refresh_token": "new_refresh", "expires_in": 3600}

    with patch("eventyay.base.settings.GlobalSettingsObject", lambda: gs):
        with patch("requests.post", lambda *args, **kwargs: MockResponse()):
            with pytest.raises(
                VoxbentoReauthorizationRequired, match="Integration disconnected during refresh network call"
            ):
                get_valid_access_token(grant.id)
