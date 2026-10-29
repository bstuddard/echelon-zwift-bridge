"""Verify desktop actions don't stop unmanaged processes or duplicate services."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('bridge_desktop', Path(__file__).resolve().parents[2] / 'desktop/bridge_control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def test_start_is_idempotent_and_keeps_the_existing_ride(monkeypatch):
    actions = []
    monkeypatch.setattr(control, 'read_status', lambda: {'running': True, 'reachable': True})
    monkeypatch.setattr(control, 'run_bridge', actions.append)
    monkeypatch.setattr(control, 'notify', lambda *args: None)
    control.control('start')
    assert actions == []


def test_stop_targets_managed_service_and_verifies_it_stopped(monkeypatch):
    actions = []
    monkeypatch.setattr(control, 'read_status', lambda: {'running': True, 'reachable': True})
    monkeypatch.setattr(control, 'run_bridge', actions.append)
    monkeypatch.setattr(control, 'service_state', lambda: 'inactive')
    notifications = []
    monkeypatch.setattr(control, 'notify', lambda title, message: notifications.append(title))
    control.control('stop')
    assert actions == ['stop'] and notifications == ['Echelon Bridge stopped']
    monkeypatch.setattr(control, 'service_state', lambda: 'active')
    notifications.clear()
    with pytest.raises(RuntimeError, match='did not stop'):
        control.control('stop')
    assert notifications == []


def test_unmanaged_foreground_server_is_not_killed_or_replaced(monkeypatch):
    actions = []
    notifications = []
    monkeypatch.setattr(control, 'read_status', lambda: {'running': False, 'reachable': True})
    monkeypatch.setattr(control, 'run_bridge', actions.append)
    monkeypatch.setattr(control, 'notify', lambda title, message: notifications.append(title))
    control.control('stop')
    assert actions == []
    assert notifications == ['Stop the foreground bridge in its terminal']
    control.control('start')
    assert actions == []
