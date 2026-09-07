from __future__ import annotations

import pytest

from local_backend import desktop


def test_primary_instance_starts_normally(monkeypatch):
    monkeypatch.setattr(desktop, "acquire_single_instance_mutex", lambda: True)
    assert desktop.prepare_single_instance_startup(wait_seconds=0) is True


def test_duplicate_instance_activates_existing_app(monkeypatch):
    monkeypatch.setattr(desktop, "acquire_single_instance_mutex", lambda: False)
    monkeypatch.setattr(desktop, "activate_existing_instance", lambda: True)
    assert desktop.prepare_single_instance_startup(wait_seconds=0) is False


def test_stale_primary_mutex_uses_recovery_lock_when_no_backend_or_window(monkeypatch):
    monkeypatch.setattr(desktop, "acquire_single_instance_mutex", lambda: False)
    monkeypatch.setattr(desktop, "activate_existing_instance", lambda: False)
    monkeypatch.setattr(desktop, "activate_named_window_any_process", lambda _title: False)
    monkeypatch.setattr(desktop, "port_is_in_use", lambda: False)
    monkeypatch.setattr(desktop, "acquire_recovery_mutex", lambda: True)

    assert desktop.prepare_single_instance_startup(wait_seconds=0) is True


def test_old_visible_window_is_focused_before_recovery(monkeypatch):
    monkeypatch.setattr(desktop, "acquire_single_instance_mutex", lambda: False)
    monkeypatch.setattr(desktop, "activate_existing_instance", lambda: False)
    monkeypatch.setattr(desktop, "activate_named_window_any_process", lambda _title: True)
    monkeypatch.setattr(
        desktop,
        "acquire_recovery_mutex",
        lambda: (_ for _ in ()).throw(AssertionError("recovery lock should not be used")),
    )

    assert desktop.prepare_single_instance_startup(wait_seconds=0) is False


def test_foreign_or_unhealthy_listener_is_not_bypassed(monkeypatch):
    monkeypatch.setattr(desktop, "acquire_single_instance_mutex", lambda: False)
    monkeypatch.setattr(desktop, "activate_existing_instance", lambda: False)
    monkeypatch.setattr(desktop, "activate_named_window_any_process", lambda _title: False)
    monkeypatch.setattr(desktop, "port_is_in_use", lambda: True)

    with pytest.raises(desktop.DesktopStartupError, match="8765"):
        desktop.prepare_single_instance_startup(wait_seconds=0)
