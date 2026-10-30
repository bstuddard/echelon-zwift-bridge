#!/usr/bin/env python3
"""Run the production mirror pipeline with fake ADB and original test video.

Requires the dev Python environment, frontend dependencies/build, and Chromium.
Does not invoke installed ADB, access phone keys, use Bluetooth, or contact LAN devices.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='echelon-mirror-e2e-') as directory:
        temporary=Path(directory)
        bin_dir=temporary/'bin';bin_dir.mkdir()
        fake=ROOT/'backend/tests/fake_phone_adb.py'
        for name in ('adb','ss'):
            path=bin_dir/name
            shutil.copy2(fake,path);path.chmod(0o700)
        fixture=temporary/'fixture';fixture.mkdir(mode=0o700)
        (fixture/'mode').write_text('normal')
        fixture_text=(ROOT/'frontend/tests/mirror-video-fixture.mjs').read_text()
        video=dict(re.findall(r"export const (\w+) = '([^']+)'",fixture_text))
        assert all(name in video for name in ('configBase64','keyBase64','portraitConfigBase64','portraitKeyBase64'))
        (fixture/'video.json').write_text(json.dumps(video))
        server=temporary/'fake-scrcpy-server';server.write_text('Inert E2E fixture; never uploaded to a phone.')
        state=temporary/'state'/'echelon-bridge';state.mkdir(parents=True,mode=0o700)
        selection=state/'phone.json'
        selection.write_text(json.dumps({'adb':str(bin_dir/'adb'),'server':str(server),'version':'5.0.1',
             'serial':'synthetic-phone-serial','service':'adb-synthetic-phone',
             'server_sha256':hashlib.sha256(server.read_bytes()).hexdigest()}))
        selection.chmod(0o600)
        with socket.socket() as available:
            available.bind(('127.0.0.1',0));port=available.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        env=os.environ.copy()
        env.update({'XDG_STATE_HOME':str(temporary/'state'),'FAKE_PHONE_ROOT':str(fixture),
                    'PATH':str(bin_dir)+os.pathsep+env['PATH'], 'PYTHONPATH':str(ROOT/'backend'),
                    'BRIDGE_TEST_URL':url,'MIRROR_TEST_ROOT':str(fixture),'MIRROR_TEST_SERVER':str(server)})
        with (temporary/'server.log').open('w+') as log:
            process=subprocess.Popen([sys.executable,'-m','echelon_bridge','--http-only','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            passed=False
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Isolated test server exited before startup')
                    try:
                        with opener.open(url+'/api/mirror/status',timeout=.3) as response:
                            assert json.load(response)['configured']
                        break
                    except (OSError,AssertionError):
                        time.sleep(.05)
                else:
                    raise RuntimeError('Isolated test server did not become ready')
                subprocess.run(['node','frontend/tests/mirror-e2e.mjs'],cwd=ROOT,env=env,check=True,timeout=180)
                for script in ('browser-smoke.mjs','mirror-browser-smoke.mjs'):
                    subprocess.run(['node','frontend/tests/'+script],cwd=ROOT,env=env,check=True,timeout=120)
                passed=True
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
                events_path=fixture/'events.jsonl'
                events=[json.loads(row) for row in events_path.read_text().splitlines()] if events_path.exists() else []
                for entry in events:
                    if entry['kind']=='capture-start':
                        try:
                            # Only synthetic capture subprocesses started by this fixture.
                            os.kill(entry['pid'],0)
                        except ProcessLookupError:
                            continue
                        cmdline=Path('/proc')/str(entry['pid'])/'cmdline'
                        try: args=[arg.decode() for arg in cmdline.read_bytes().split(b'\0') if arg]
                        except FileNotFoundError: continue
                        if str(bin_dir/'adb') in args and 'app_process' in args:
                            try: os.kill(entry['pid'],15)
                            except ProcessLookupError: pass
                            if passed: raise AssertionError('Synthetic capture child was not reaped')
                log.seek(0)
                content=log.read()
                if not passed:
                    for line in content.splitlines()[-15:]:
                        print(line.replace(str(Path.home()),'[user-home]'),file=sys.stderr)
                else:
                    assert not any(marker in content for marker in ('Traceback (most recent call last)', 'Exception in ASGI application', 'ERROR:')), 'Isolated server logged an unexpected error'


if __name__=='__main__':
    main()
