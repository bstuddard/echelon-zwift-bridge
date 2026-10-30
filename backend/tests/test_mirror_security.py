import asyncio
from contextlib import asynccontextmanager
import ipaddress
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from echelon_bridge.app import create_app
from echelon_bridge.config import Settings
from echelon_bridge.mirror import Mirror, loopback_authority
from echelon_bridge.phone import Adb, PhoneError, PhoneSelection, local_endpoint, read_private_json


def stub_socket(mirror, host='127.0.0.1:8000', origin='http://127.0.0.1:8000', peer='127.0.0.1', protocols=None):
    return SimpleNamespace(headers={'host': host, 'origin': origin}, client=SimpleNamespace(host=peer),
                           scope={'scheme': 'ws', 'subprotocols': protocols if protocols is not None else ['echelon-mirror', 'ticket.' + mirror.token]})


@pytest.mark.parametrize('host', ['localhost:0', 'localhost:65536', 'localhost/', 'localhost?x', 'localhost#x', 'localhost:',
                                  'localhost@untrusted.example', '127.0.0.1:8000/extra', '[::1]@untrusted.example', 'localhost;connect-src *'])
def test_malformed_authority_is_rejected(host):
    mirror = Mirror()
    assert not loopback_authority(host)
    assert not mirror.authorized(stub_socket(mirror, host=host, origin='http://' + host))


@pytest.mark.parametrize('protocols', [[], ['echelon-mirror'], ['echelon-mirror', 'ticket.é'], ['echelon-mirror', 'ticket.bad', 'extra'], ['ticket.bad','echelon-mirror']])
def test_malformed_tickets_fail_closed_without_exceptions(protocols):
    mirror = Mirror()
    assert not mirror.authorized(stub_socket(mirror, protocols=protocols))


def test_valid_ticket_does_not_bypass_peer_origin_or_process_boundaries():
    mirror = Mirror()
    assert mirror.authorized(stub_socket(mirror))
    assert not mirror.authorized(stub_socket(mirror, peer='192.0.2.10'))
    assert not mirror.authorized(stub_socket(mirror, origin='https://untrusted.example'))
    assert not Mirror().authorized(stub_socket(mirror))


def test_http_host_rejection_does_not_reflect_untrusted_websocket_sources():
    with TestClient(create_app(Settings()), base_url='http://127.0.0.1') as client:
        response=client.get('/mirror',headers={'host':'untrusted.example','accept':'text/html'})
        assert response.status_code == 400
        assert 'untrusted.example' not in response.headers.get('content-security-policy','')
        allowed=client.get('/mirror',headers={'accept':'text/html'})
        assert 'ws://127.0.0.1' in allowed.headers['content-security-policy']


def test_remote_peer_with_valid_origin_and_ticket_cannot_start_capture():
    started=[]
    @asynccontextmanager
    async def source():
        started.append(True)
        yield None
    mirror=Mirror(source_factory=source)
    with TestClient(create_app(Settings(),mirror=mirror),base_url='http://127.0.0.1',client=('192.0.2.10',50000)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('ws://127.0.0.1/api/mirror/stream',headers={'origin':'http://127.0.0.1'},subprotocols=['echelon-mirror','ticket.'+mirror.token]):
                pass
    assert not started


def test_fifo_symlink_directory_oversized_and_non_object_configurations_are_rejected(tmp_path):
    fifo=tmp_path/'fifo'
    os.mkfifo(fifo,0o600)
    start=time.monotonic()
    with pytest.raises(PhoneError):
        read_private_json(fifo)
    assert time.monotonic()-start < 1
    source=tmp_path/'source'
    source.write_text('{}');source.chmod(0o600)
    link=tmp_path/'link';link.symlink_to(source)
    for path in (link,tmp_path):
        with pytest.raises(PhoneError):
            read_private_json(path)
    for value in ('x'*17000, '[]', 'null', '{broken'):
        source.write_text(value)
        with pytest.raises(PhoneError):
            read_private_json(source)


def test_adb_environment_cannot_redirect_daemon_or_enable_plaintext_discovery(monkeypatch):
    for name in ('ADB_SERVER_SOCKET','ANDROID_SERIAL','ANDROID_ADB_SERVER_ADDRESS','ANDROID_ADB_SERVER_PORT','ADB_VENDOR_KEYS','ADB_TRACE'):
        monkeypatch.setenv(name,'untrusted-test-value')
    monkeypatch.setenv('ADB_MDNS_AUTO_CONNECT','all')
    adb=Adb(Path('/not-executed'))
    assert not any(name in adb.env for name in ('ADB_SERVER_SOCKET','ANDROID_SERIAL','ANDROID_ADB_SERVER_ADDRESS','ANDROID_ADB_SERVER_PORT','ADB_VENDOR_KEYS','ADB_TRACE'))
    assert adb.env['ADB_MDNS_AUTO_CONNECT'] == 'adb-tls-connect'


@pytest.mark.parametrize('endpoint', ['127.0.0.1:4000','0.0.0.0:4000','192.0.2.10:4000','https://untrusted.example','localhost:4000','[::1]:4000',
                                      'invalid:0'])
def test_non_lan_or_malformed_discovery_endpoints_are_rejected(endpoint):
    with pytest.raises(PhoneError):
        local_endpoint(endpoint)


def test_valid_private_network_endpoints_are_accepted():
    for octets in ((10,23,42,99),(172,20,1,2),(192,168,20,30)):
        endpoint='.'.join(map(str,octets))+':4000'
        assert local_endpoint(endpoint) == endpoint
    ula=str(ipaddress.IPv6Address((0xfd << 120) | 1))
    link=str(ipaddress.IPv6Address((0xfe80 << 112) | 1))
    assert local_endpoint(f'[{ula}]:4000') == f'[{ula}]:4000'
    assert local_endpoint(f'[{link}%test0]:4000') == f'[{link}%test0]:4000'
    for scope in ('bad;scope','scope%extra',''):
        with pytest.raises(PhoneError):
            local_endpoint(f'[{link}%{scope}]:4000')
    public=str(ipaddress.IPv4Address(0x01010101))+':4000'
    with pytest.raises(PhoneError):
        local_endpoint(public)


def test_raw_ip_or_legacy_discovery_never_becomes_a_phone_transport(monkeypatch):
    calls=[]
    async def local():
        pass
    async def run(*args,**kwargs):
        calls.append(args)
        if args == ('mdns','services'):
            return 'selected _adb._tcp '+'.'.join(map(str,(10,23,42,99)))+':5555'
        pytest.fail('Legacy discovery must be rejected before device commands')
    adb=Adb(Path('/unused'))
    monkeypatch.setattr(adb,'check_local_server',local)
    monkeypatch.setattr(adb,'run',run)
    selection=PhoneSelection(Path('/unused'),Path('/unused'),'5.0.1','test-phone-serial','selected','0'*64)
    with pytest.raises(PhoneError,match='offline'):
        asyncio.run(adb.selected(selection))
    assert calls == [('mdns','services')]


def test_adb_output_and_command_time_are_bounded_and_children_are_reaped(tmp_path):
    script=tmp_path/'fake-adb'
    pidfile=tmp_path/'pid'
    for body, expected in (("import sys,time;sys.stdout.buffer.write(b'x'*200000);sys.stdout.flush();time.sleep(30)",PhoneError),
                           ('import time;time.sleep(30)',asyncio.TimeoutError)):
        script.write_text('#!/usr/bin/python3\nimport os\nfrom pathlib import Path\nPath('+repr(str(pidfile))+').write_text(str(os.getpid()))\n'+body+'\n')
        script.chmod(0o700)
        async def run():
            with pytest.raises(expected):
                await Adb(script).run('test',timeout=.2)
        asyncio.run(run())
        assert not (Path('/proc')/pidfile.read_text()).exists()


def test_silent_client_timeout_releases_the_capture_and_lock(monkeypatch):
    closed=[]
    @asynccontextmanager
    async def source():
        try:
            async def packets():
                yield b'test-frame'
                await asyncio.Event().wait()
            yield packets()
        finally:
            closed.append(True)
    mirror=Mirror(source_factory=source)
    monkeypatch.setattr(mirror,'HEARTBEAT_TIMEOUT',.05)
    with TestClient(create_app(Settings(),mirror=mirror),base_url='http://127.0.0.1',client=('127.0.0.1',50000)) as client:
        with client.websocket_connect('ws://127.0.0.1/api/mirror/stream',headers={'origin':'http://127.0.0.1'},subprotocols=['echelon-mirror','ticket.'+mirror.token]) as socket:
            socket.receive_json();socket.receive_bytes()
            assert socket.receive_json()['type'] == 'error'
        assert closed == [True]
        assert not mirror.lock.locked()


def test_slow_viewer_does_not_hold_video_capture_forever(monkeypatch):
    async def run():
        closed=[]
        @asynccontextmanager
        async def source():
            try:
                async def packets():
                    yield b'test-frame'
                yield packets()
            finally:
                closed.append(True)
        mirror=Mirror(source_factory=source)
        monkeypatch.setattr(mirror,'SEND_TIMEOUT',.03)
        socket=stub_socket(mirror)
        messages=[]
        async def accept(**kwargs):
            pass
        async def send_json(value):
            messages.append(value)
        async def blocked(*args):
            await asyncio.Event().wait()
        async def close(**kwargs):
            pass
        socket.accept=accept;socket.send_json=send_json;socket.send_bytes=blocked;socket.receive=blocked;socket.close=close
        await asyncio.wait_for(mirror.stream(socket),1)
        assert closed == [True] and not mirror.lock.locked()
        assert messages[-1]['type'] == 'error'
    asyncio.run(run())
