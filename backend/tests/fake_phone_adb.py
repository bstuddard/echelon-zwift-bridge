#!/usr/bin/env python3
"""E2E fixture: fake ADB and phone video. Never calls Android tools or a phone.

All sockets are loopback. The apparent LAN address and identity are synthetic.
This fixture is executed only by scripts/test_mirror_e2e.py.
"""
import base64
import json
import os
from pathlib import Path
import signal
import socket
import struct
import sys
import time

root = Path(os.environ['FAKE_PHONE_ROOT'])
args = sys.argv[1:]
mode = (root/'mode').read_text().strip()
identity = 'synthetic-phone-serial'
service = 'adb-synthetic-phone'
transport = service + '._adb-tls-connect._tcp'
address = '.'.join(map(str, (10, 23, 42, 99)))


def event(kind, **details):
    fd=os.open(root/'events.jsonl',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(json.dumps({'kind':kind,**details})+'\n')


if Path(sys.argv[0]).name == 'ss':
    print('LISTEN 0 128 '+(address if mode == 'bad-listener' else '127.0.0.1')+':5037 0.0.0.0:*')
    raise SystemExit(0)

event('adb',args=args)
if args == ['start-server']:
    raise SystemExit(0)
if args == ['mdns','services']:
    print('List of discovered mdns services')
    if mode != 'missing-phone':
        print(service+'\t'+('_adb._tcp' if mode == 'legacy-only' else '_adb-tls-connect._tcp')+'\t'+address+':40000')
    raise SystemExit(0)
if args and args[0] == 'connect':
    raise SystemExit('Raw IP connections are prohibited in this fixture')
assert len(args)>=3 and args[:2] == ['-s',transport], 'Unexpected target or command'
command=args[2:]
if command == ['get-state']:
    print('unauthorized' if mode == 'unauthorized' else 'device')
elif command == ['shell','getprop','ro.serialno']:
    print('wrong-synthetic-phone' if mode == 'identity-mismatch' else identity)
elif command[0] == 'push':
    assert command[2].startswith('/data/local/tmp/echelon-video-')
    (root/'uploaded').write_text(command[2])
    if mode == 'slow-upload':
        time.sleep(10)
elif command[0] == 'reverse':
    if command[1] == '--remove':
        (root/'tunnel').unlink(missing_ok=True)
    else:
        assert command[1].startswith('localabstract:scrcpy_') and command[2].startswith('tcp:')
        (root/'tunnel').write_text(command[2].split(':')[1])
elif command[:3] == ['shell','rm','-f']:
    assert command[3].startswith('/data/local/tmp/echelon-video-')
    (root/'uploaded').unlink(missing_ok=True)
elif command[0] == 'shell' and len(command)>5 and command[1].startswith('CLASSPATH='):
    assert command[2:5] == ['app_process','/','com.genymobile.scrcpy.Server']
    assert all(option in command for option in ('audio=false','control=false','clipboard_autosync=false','power_on=false','send_device_meta=false'))
    event('capture-start',pid=os.getpid())
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        if mode == 'slow-start':
            time.sleep(30)
        port=int((root/'tunnel').read_text())
        with socket.create_connection(('127.0.0.1',port),timeout=3) as stream:
            stream.settimeout(None)
            stream.sendall(b'xxxx' if mode == 'bad-codec' else b'h264')
            fixtures=json.loads((root/'video.json').read_text())
            sequence=0
            def size(width,height):
                stream.sendall(struct.pack('!III',0x80000000,width,height))
            def packet(payload,flags):
                stream.sendall(struct.pack('!QI',flags,len(payload))+payload)
            size(64,48)
            packet(base64.b64decode(fixtures['configBase64']),1<<62)
            while True:
                if mode == 'oversize' or (mode == 'corrupt-after-frame' and sequence == 6):
                    stream.sendall(struct.pack('!QI',0,4*1024*1024+1))
                    stream.recv(1)
                    break
                if mode == 'truncated-header':
                    stream.sendall(b'\0'*5)
                    break
                if mode == 'rotate' and sequence == 12:
                    size(48,64)
                    packet(base64.b64decode(fixtures['portraitConfigBase64']),1<<62)
                key='portraitKeyBase64' if mode == 'rotate' and sequence >=12 else 'keyBase64'
                packet(base64.b64decode(fixtures[key]),(1<<61)|(sequence*33333))
                sequence+=1
                time.sleep(1/30)
    except (BrokenPipeError,ConnectionError,OSError):
        pass
    finally:
        event('capture-stop',pid=os.getpid())
else:
    raise SystemExit('Unexpected fake ADB command')
