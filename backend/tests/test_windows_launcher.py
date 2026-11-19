import json
from unittest.mock import Mock

import pytest

from echelon_bridge import windows_launcher as launcher


@pytest.fixture
def desktop(monkeypatch):
    monkeypatch.setattr(launcher.sys, 'platform', 'win32')
    browser, server = Mock(), Mock()
    monkeypatch.setattr(launcher.webbrowser, 'open', browser)
    monkeypatch.setattr(launcher, 'run_bridge', server)
    connection = Mock()
    monkeypatch.setattr(launcher.http.client, 'HTTPConnection', Mock(return_value=connection))
    return browser, server, connection


def test_running_bridge_opens_dashboard_without_starting_another_reader(desktop):
    browser, server, connection = desktop
    response = connection.getresponse.return_value
    response.status = 200
    response.read.return_value = json.dumps({'app': 'Echelon \u2192 Zwift'}).encode()
    launcher.main([])
    browser.assert_called_once_with(launcher.URL)
    server.assert_not_called()
    connection.close.assert_called_once()


def test_stopped_bridge_starts_with_browser_opening_enabled(desktop):
    browser, server, connection = desktop
    connection.request.side_effect = ConnectionRefusedError()
    launcher.main([])
    server.assert_called_once_with(['--open'])
    browser.assert_not_called()


@pytest.mark.parametrize('body', [b'not JSON', b'{"app":"another server"}', b'[]', b'x' * 8193])
def test_unrelated_server_is_not_opened_or_replaced(desktop, body):
    browser, server, connection = desktop
    response = connection.getresponse.return_value
    response.status = 200
    response.read.return_value = body
    with pytest.raises(RuntimeError, match='Port 8000'):
        launcher.main([])
    browser.assert_not_called()
    server.assert_not_called()


def test_stop_uses_graceful_control_without_starting_or_opening_server(desktop, monkeypatch):
    from echelon_bridge import windows_control
    browser, server, connection = desktop
    signal = Mock(return_value=True)
    monkeypatch.setattr(windows_control, 'request_stop', signal)
    launcher.main(['--stop'])
    signal.assert_called_once()
    server.assert_not_called()
    browser.assert_not_called()
    connection.request.assert_not_called()


def test_stop_when_already_stopped_does_not_start_server(desktop, monkeypatch, capsys):
    from echelon_bridge import windows_control
    browser, server, connection = desktop
    monkeypatch.setattr(windows_control, 'request_stop', Mock(return_value=False))
    connection.request.side_effect = ConnectionRefusedError()
    launcher.main(['--stop'])
    assert 'already stopped' in capsys.readouterr().out
    server.assert_not_called()
    browser.assert_not_called()
