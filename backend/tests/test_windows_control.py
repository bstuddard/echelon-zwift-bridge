"""Exercise real Windows controls, including finalizing an active ride on stop."""
import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

from echelon_bridge.windows_control import StopControl, request_stop

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows event objects')


def test_stop_is_scoped_and_rejects_duplicate_servers(tmp_path):
    assert request_stop(tmp_path) is False
    with StopControl(tmp_path) as control:
        assert request_stop(tmp_path / 'other') is False
        assert request_stop(tmp_path, port=8001) is False
        assert not control.requested()
        with pytest.raises(RuntimeError, match='already has a server'):
            with StopControl(tmp_path):
                pytest.fail('A duplicate server must not take ownership')
        with pytest.raises(TimeoutError, match='still finishing'):
            request_stop(tmp_path, timeout=0.01)
        assert control.requested()
    assert request_stop(tmp_path) is False


FIXTURE = r'''
import asyncio
import sys
import echelon_bridge.app as application
from echelon_bridge.__main__ import main

async def reader(bike, *args, **kwargs):
    bike.connected = bike.initialized = True
    bike.ingest(bytes.fromhex('f0 d2 01 14 d7'))
    bike.ingest(bytes.fromhex('f0 d1 00 00 00 00 00 00 00 00 5a 00 00'))
    await asyncio.Event().wait()

original = application.create_app
application.create_app = lambda settings: original(settings, reader=reader)
main(['--address', 'AA:BB:CC:DD:EE:01', '--port', sys.argv[1]])
'''


def test_stop_finishes_active_recording_and_releases_server(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]

    def call(method, route, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
        try:
            connection.request(method, route, body=body, headers=headers or {})
            response = connection.getresponse()
            assert response.status == 200
            return json.loads(response.read())
        finally:
            connection.close()

    with (tmp_path / 'server.log').open('w') as output:
        process = subprocess.Popen([sys.executable, '-c', FIXTURE, str(port)], cwd=tmp_path,
                                   stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 10
            while True:
                assert process.poll() is None, (tmp_path / 'server.log').read_text()
                try:
                    metrics = call('GET', '/api/metrics')
                    break
                except OSError:
                    assert time.monotonic() < deadline, 'Fixture server did not start'
                    time.sleep(0.05)
            history = tmp_path / 'history.psv'
            headers = {'Origin': f'http://127.0.0.1:{port}', 'Content-Type': 'text/plain',
                       'X-Session-Revision': metrics['session']['revision']}
            result = call('POST', '/api/session/start', str(history), headers)
            assert result['status'] == 'active'
            assert request_stop(tmp_path, port)
            assert process.wait(timeout=10) == 0
            events = [row.split('|')[2] for row in history.read_text().splitlines()[1:]]
            assert events[0] == 'start' and events[-1] == 'finish'
            assert events.count('finish') == 1
            assert request_stop(tmp_path, port) is False
            with socket.socket() as probe:
                assert probe.connect_ex(('127.0.0.1', port)) != 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
