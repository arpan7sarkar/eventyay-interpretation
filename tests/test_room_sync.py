from unittest.mock import Mock

import pytest
import requests
from django.db import transaction
from eventyay.base.models import Room
from eventyay.base.services.room import soft_delete_room

from interpretation.models import VoxbentoOAuthGrant
from interpretation.tasks import _do_sync_single_room_to_voxbento, sync_single_room_to_voxbento

pytestmark = pytest.mark.django_db


@pytest.fixture
def room_sync(room, monkeypatch):
    VoxbentoOAuthGrant.objects.create(event=room.event, event_provisioned=True)
    upsert = Mock(return_value={})
    delete = Mock()
    monkeypatch.setattr("interpretation.tasks.sync_voxbento_room", upsert)
    monkeypatch.setattr("interpretation.tasks.delete_voxbento_room", delete)
    monkeypatch.setattr("eventyay.base.models.cache.VersionedModel._set_cache_version_sync", Mock())
    monkeypatch.setattr("eventyay.base.models.cache.VersionedModel._set_cache_deleted_sync", Mock())
    return upsert, delete


def test_soft_delete_syncs_only_after_commit(room, room_sync, django_capture_on_commit_callbacks):
    upsert, delete = room_sync

    with django_capture_on_commit_callbacks(execute=True):
        deleted_room = soft_delete_room(room.event, room)
        assert deleted_room.deleted
        upsert.assert_not_called()
        delete.assert_not_called()

    room.refresh_from_db()
    assert room.deleted
    delete.assert_called_once_with(room.event, room.pk)
    upsert.assert_not_called()


def test_rolled_back_soft_delete_does_not_sync(room, room_sync, django_capture_on_commit_callbacks):
    upsert, delete = room_sync

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(ValueError), transaction.atomic():
            soft_delete_room(room.event, room)
            raise ValueError("Roll back deletion")

    room.refresh_from_db()
    assert not room.deleted
    upsert.assert_not_called()
    delete.assert_not_called()


@pytest.mark.parametrize("with_instance", [False, True])
def test_deleted_room_is_not_upserted(room, room_sync, with_instance):
    upsert, delete = room_sync
    Room.objects.filter(pk=room.pk).update(deleted=True)
    room.refresh_from_db()

    needs_retry = _do_sync_single_room_to_voxbento(
        room.pk, room.event_id, "upsert", room_instance=room if with_instance else None
    )

    assert not needs_retry
    upsert.assert_not_called()


def test_late_queued_upsert_does_not_recreate_deleted_room(room, room_sync):
    upsert, delete = room_sync
    Room.objects.filter(pk=room.pk).update(deleted=True)

    sync_single_room_to_voxbento.run(room.pk, room.event_id, "upsert")

    upsert.assert_not_called()


def test_room_update_still_upserts(room, room_sync, django_capture_on_commit_callbacks):
    upsert, delete = room_sync
    room.name = "Renamed stage"

    with django_capture_on_commit_callbacks(execute=True):
        room.save(update_fields=["name"])

    upsert.assert_called_once()
    assert upsert.call_args.args[2]["name"] == "Renamed stage"
    delete.assert_not_called()


def test_new_room_still_syncs_after_commit(event, room_sync, django_capture_on_commit_callbacks):
    upsert, delete = room_sync

    with django_capture_on_commit_callbacks(execute=True):
        room = Room.objects.create(event=event, name="Second stage")
        upsert.assert_not_called()

    upsert.assert_called_once()
    assert upsert.call_args.args[1] == room.pk
    delete.assert_not_called()


def test_hard_delete_still_syncs_after_commit(room, room_sync, django_capture_on_commit_callbacks):
    upsert, delete = room_sync
    room_id = room.pk
    event = room.event

    with django_capture_on_commit_callbacks(execute=True):
        room.delete()
        delete.assert_not_called()

    delete.assert_called_once_with(event, room_id)
    upsert.assert_not_called()


def test_delete_failure_requests_retry(room, room_sync, monkeypatch):
    upsert, delete = room_sync
    delete.side_effect = requests.ConnectionError("VoxBento unavailable")
    retry = Mock()
    monkeypatch.setattr(sync_single_room_to_voxbento, "retry", retry)

    sync_single_room_to_voxbento.run(room.pk, room.event_id, "delete")

    retry.assert_called_once()
    upsert.assert_not_called()


def test_active_booth_delete_is_not_forced(room, room_sync):
    upsert, delete = room_sync
    response = requests.Response()
    response.status_code = 409
    delete.side_effect = requests.HTTPError("Active booth", response=response)

    assert _do_sync_single_room_to_voxbento(room.pk, room.event_id, "delete")

    delete.assert_called_once_with(room.event, room.pk)
    upsert.assert_not_called()
