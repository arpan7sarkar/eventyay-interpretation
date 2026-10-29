"""OAuth callbacks bind both local identity and token exchange to the initiating event."""

import time
from contextlib import nullcontext
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from django.urls import reverse
from eventyay.base.models import Event, Organizer
from eventyay.base.settings import GlobalSettingsObject

from interpretation.models import VoxbentoOAuthGrant

pytestmark = pytest.mark.django_db


@pytest.fixture
def attempt(organizer_client, event):
    settings = GlobalSettingsObject().settings
    settings.set("voxbento_client_id", "test-client")
    settings.set("voxbento_client_secret", "test-secret")
    settings.set("voxbento_base_url", "https://voxbento.example.com")
    response = organizer_client.get(
        reverse(
            "plugins:interpretation:oauth_connect",
            kwargs={"organizer": event.organizer.slug, "event": event.slug},
        )
    )
    assert response.status_code == 302
    state = parse_qs(urlparse(response["Location"]).query)["state"][0]
    assert organizer_client.session[f"voxbento_oauth_state:{state}"]["event_id"] == event.pk
    return state


def callback(client, state, **params):
    return client.get(reverse("plugins:interpretation:oauth_callback"), {"state": state, **params})


def test_duplicate_slugs_resolve_session_event(organizer_client, event, attempt, django_capture_on_commit_callbacks):
    other = Event.objects.create(
        organizer=Organizer.objects.create(name="Other", slug="other"),
        slug=event.slug,
        name="Same slug, different organizer",
        date_from=event.date_from,
        currency="USD",
    )
    token_response = Mock()
    token_response.json.return_value = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "event": event.slug,
    }
    with (
        patch("interpretation.views_oauth.requests.post", return_value=token_response) as exchange,
        patch("interpretation.views_oauth._get_cache_lock", return_value=nullcontext()),
        patch("interpretation.views_oauth.sync_voxbento_connection.delay") as sync,
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = callback(organizer_client, attempt, code="code")
    assert response.status_code == 200
    assert response.context["success"] is True
    assert exchange.call_args.kwargs["data"]["event"] == event.slug
    assert VoxbentoOAuthGrant.objects.get(event=event).access_token == "access-token"
    assert not VoxbentoOAuthGrant.objects.filter(event=other).exists()
    sync.assert_called_once_with(event.pk)
    with patch("interpretation.views_oauth.requests.post") as exchange:
        assert callback(organizer_client, attempt, code="code").context["success"] is False
    exchange.assert_not_called()


def test_wrong_event_code_rejection_preserves_existing_grant(organizer_client, event, attempt):
    grant = VoxbentoOAuthGrant.objects.create(event=event, access_token="existing-token")

    def exchange(url, *, data, timeout):
        # Model VoxBento's rejection of a code issued for another event.
        assert data["event"] == event.slug
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("Code was issued for another event")
        return response

    with (
        patch("interpretation.views_oauth.requests.post", side_effect=exchange) as post,
        patch("interpretation.views_oauth.sync_voxbento_connection.delay") as sync,
    ):
        response = callback(organizer_client, attempt, code="other-event-code")
    assert response.context["success"] is False
    post.assert_called_once()
    grant.refresh_from_db()
    assert grant.access_token == "existing-token"
    sync.assert_not_called()


@pytest.mark.parametrize("invalid", ["expired", "legacy", "mismatch", "unknown", "permission"])
def test_invalid_attempt_never_exchanges_code(organizer_client, event, team, attempt, invalid):
    session = organizer_client.session
    key = f"voxbento_oauth_state:{attempt}"
    data = session[key]
    if invalid == "expired":
        data["timestamp"] = time.time() - 601
    elif invalid == "legacy":
        data.pop("event_id")
    elif invalid == "mismatch":
        data["state"] = "different-state"
    elif invalid == "unknown":
        attempt += "unknown"
    else:
        team.can_change_event_settings = False
        team.save()
    session[key] = data
    session.save()
    with patch("interpretation.views_oauth.requests.post") as exchange:
        response = callback(organizer_client, attempt, code="code")
    assert response.context["success"] is False
    exchange.assert_not_called()
    assert not VoxbentoOAuthGrant.objects.filter(event=event).exists()


def test_denial_consumes_validated_attempt(organizer_client, attempt):
    response = callback(organizer_client, attempt, error="access_denied")
    assert response.context["success"] is False
    assert "cancelled" in response.context["error_message"]
    assert f"voxbento_oauth_state:{attempt}" not in organizer_client.session
