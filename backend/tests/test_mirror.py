import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import struct
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from echelon_bridge.app import create_app
from echelon_bridge.config import Settings
from echelon_bridge.mirror import Mirror
from echelon_bridge.phone import Adb, MAX_PACKET, PhoneError, PhoneSelection, PhoneVideo, read_packet


class Source:
    def __init__(self):
        self.opened = 0
        self.closed = 0

    @asynccontextmanager
    async def open(self):
        self.opened += 1
        try:
            async def packets():
                yield {"type": "size", "width": 1280, "height": 720}
                yield b"test-video-packet"
                await asyncio.Event().wait()
            yield packets()
        finally:
            self.closed += 1


def test_status_never_contacts_phone_or_exposes_selection(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    with TestClient(create_app(Settings()), base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        result = client.get('/api/mirror/status')
        assert result.status_code == 200
        assert result.headers['cache-control'] == 'no-store'
        assert result.json()['configured'] is False
        assert 'token' not in result.json()
        assert 'serial' not in result.text and 'endpoint' not in result.text


@pytest.mark.parametrize('origin,token', [('https://untrusted.example', True), ('null', True), (None, True), ('http://127.0.0.1', False)])
def test_websocket_rejects_cross_origin_missing_origin_and_invalid_token(origin, token):
    source = Source()
    mirror = Mirror(source_factory=source.open)
    with TestClient(create_app(Settings(), mirror=mirror), base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        headers = {'origin': origin} if origin else {}
        ticket = mirror.token if token else 'invalid'
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect('ws://127.0.0.1/api/mirror/stream', headers=headers, subprotocols=['echelon-mirror', 'ticket.' + ticket]):
                pass
        assert error.value.code == 1008
        assert source.opened == 0


def test_stream_is_opt_in_single_viewer_and_cleans_up_on_disconnect():
    source = Source()
    mirror = Mirror(source_factory=source.open)
    with TestClient(create_app(Settings(), mirror=mirror), base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        assert client.get('/api/mirror/status').json()['active'] is False
        assert source.opened == 0
        options = {'headers': {'origin': 'http://127.0.0.1'}, 'subprotocols': ['echelon-mirror', 'ticket.' + mirror.token]}
        with client.websocket_connect('ws://127.0.0.1/api/mirror/stream', **options) as socket:
            assert socket.receive_json() == {'type': 'starting'}
            assert socket.receive_json()['type'] == 'size'
            assert socket.receive_bytes() == b'test-video-packet'
            socket.send_text('keepalive')
            assert client.get('/api/mirror/status').json()['active'] is True
            with client.websocket_connect('ws://127.0.0.1/api/mirror/stream', **options) as second:
                assert 'already open' in second.receive_json()['message']
            assert source.opened == 1
        for _ in range(50):
            if source.closed:
                break
            time.sleep(.01)
        assert source.closed == 1
        assert client.get('/api/mirror/status').json()['active'] is False


def test_browser_cannot_send_phone_controls():
    source = Source()
    mirror = Mirror(source_factory=source.open)
    with TestClient(create_app(Settings(), mirror=mirror), base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        with client.websocket_connect('ws://127.0.0.1/api/mirror/stream', headers={'origin': 'http://127.0.0.1'}, subprotocols=['echelon-mirror', 'ticket.' + mirror.token]) as socket:
            socket.receive_json()
            socket.receive_json()
            socket.receive_bytes()
            socket.send_text('tap 100 100')
            assert 'Only video viewing' in socket.receive_json()['message']
        assert source.closed == 1


def test_protocol_supports_rotation_config_and_frames_and_rejects_oversize():
    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack('!III', 0x80000000, 720, 1280))
        reader.feed_data(struct.pack('!QI', 1 << 62, 3) + b'cfg')
        reader.feed_data(struct.pack('!QI', (1 << 61) | 123456, 3) + b'key')
        reader.feed_data(struct.pack('!QI', 123789, 5) + b'delta')
        reader.feed_data(struct.pack('!III', 0x80000000, 1280, 720))
        reader.feed_data(struct.pack('!QI', 0, MAX_PACKET + 1))
        assert await read_packet(reader) == {'type': 'size', 'width': 720, 'height': 1280}
        assert await read_packet(reader) == struct.pack('!BQ', 1, 0) + b'cfg'
        assert await read_packet(reader) == struct.pack('!BQ', 2, 123456) + b'key'
        assert await read_packet(reader) == struct.pack('!BQ', 3, 123789) + b'delta'
        assert await read_packet(reader) == {'type': 'size', 'width': 1280, 'height': 720}
        with pytest.raises(PhoneError, match='invalid video packet'):
            await read_packet(reader)
    asyncio.run(run())


def test_private_phone_selection_checks_permissions_and_server_integrity(tmp_path):
    adb = tmp_path/'adb'
    adb.write_text('#!/bin/sh\nexit 0\n')
    adb.chmod(0o700)
    server = tmp_path/'scrcpy-server'
    server.write_bytes(b'generic external server fixture')
    selection = PhoneSelection(adb, server, '5.0.1', 'test-phone-serial', 'adb-test-phone', hashlib.sha256(server.read_bytes()).hexdigest())
    config = tmp_path/'private'/'phone.json'
    selection.save(config)
    assert config.stat().st_mode & 0o777 == 0o600
    assert PhoneSelection.load(config) == selection
    config.chmod(0o644)
    with pytest.raises(PhoneError, match='private file'):
        PhoneSelection.load(config)
    config.chmod(0o600)
    server.write_bytes(b'changed external server')
    with pytest.raises(PhoneError, match='installation changed'):
        PhoneSelection.load(config)


def test_phone_discovery_only_connects_to_selected_encrypted_service(monkeypatch):
    adb = Adb(Path('/not-executed'))
    calls = []
    other = '.'.join(map(str, (10, 23, 42, 98)))
    selected_host = '.'.join(map(str, (10, 23, 42, 99)))
    async def local():
        pass
    async def run(*args, **kwargs):
        calls.append(args)
        if args == ('mdns', 'services'):
            return f'unselected _adb-tls-connect._tcp {other}:40001\nselected _adb-tls-connect._tcp {selected_host}:40002'
        if args[0] == 'connect':
            return 'connected to selected phone'
        if args[-1] == 'get-state':
            return 'device'
        return 'test-phone-serial'
    monkeypatch.setattr(adb, 'check_local_server', local)
    monkeypatch.setattr(adb, 'run', run)
    selection = PhoneSelection(Path('/unused'), Path('/unused'), '5.0.1', 'test-phone-serial', 'selected', '0'*64)
    assert asyncio.run(adb.selected(selection)) == 'selected._adb-tls-connect._tcp'
    assert not any(call[0] == 'connect' for call in calls)
    assert not any(other + ':40001' in call or selected_host + ':40002' in call for call in calls)
    selection = PhoneSelection(Path('/unused'), Path('/unused'), '5.0.1', 'different-phone-serial', 'selected', '0'*64)
    with pytest.raises(PhoneError, match='identity changed'):
        asyncio.run(adb.selected(selection))


def test_phone_capture_uses_only_video_and_removes_its_own_resources(monkeypatch):
    async def run():
        calls, server_options, peers = [], [], []
        source = PhoneVideo(PhoneSelection(Path('/unused'), Path('/unused'), '5.0.1', 'test-phone-serial', None, '0'*64))
        async def selected(_):
            return 'test-phone-serial'
        async def adb(*args, **kwargs):
            calls.append(args)
            if 'reverse' in args and '--remove' not in args:
                port = int(args[-1].split(':')[1])
                _, writer = await asyncio.open_connection('127.0.0.1', port)
                peers.append(writer)
                writer.write(b'h264' + struct.pack('!III', 0x80000000, 1280, 720))
                await writer.drain()
            return ''
        class Process:
            returncode = 0
        async def spawn(*args, **kwargs):
            server_options.extend(args)
            return Process()
        monkeypatch.setattr(source.adb, 'selected', selected)
        monkeypatch.setattr(source.adb, 'run', adb)
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        async with source.open() as packets:
            assert (await anext(packets))['type'] == 'size'
        assert 'audio=false' in server_options and 'control=false' in server_options
        assert 'clipboard_autosync=false' in server_options and 'power_on=false' in server_options
        assert any('reverse' in call and '--remove' in call for call in calls)
        assert any('rm' in call and call[-1].startswith('/data/local/tmp/echelon-video-') for call in calls)
        for peer in peers:
            peer.close()
            await peer.wait_closed()
    asyncio.run(run())


def test_capture_cancellation_during_upload_still_removes_partial_phone_file(monkeypatch):
    async def run():
        calls = []
        uploading = asyncio.Event()
        source = PhoneVideo(PhoneSelection(Path('/unused'), Path('/unused'), '5.0.1', 'test-phone-serial', None, '0'*64))
        async def selected(_):
            return 'test-phone-serial'
        async def adb(*args, **kwargs):
            calls.append(args)
            if 'push' in args:
                uploading.set()
                await asyncio.Event().wait()
            return ''
        monkeypatch.setattr(source.adb, 'selected', selected)
        monkeypatch.setattr(source.adb, 'run', adb)
        async def capture():
            async with source.open():
                pytest.fail('Upload must not finish')
        task = asyncio.create_task(capture())
        await uploading.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert any('rm' in call and call[-1].startswith('/data/local/tmp/echelon-video-') for call in calls)
    asyncio.run(run())
