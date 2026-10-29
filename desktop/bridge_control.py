#!/usr/bin/env python3
"""Local desktop controls for the bridge's systemd user service; no HTTP writes."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

PROJECT = Path(__file__).resolve().parents[1]
SERVICE = 'echelon-bridge.service'
DASHBOARD = 'http://127.0.0.1:8000'


def service_state():
    result = subprocess.run(['systemctl', '--user', 'show', SERVICE, '--property=ActiveState', '--value'],
                            capture_output=True, text=True, timeout=3)
    return result.stdout.strip() if result.returncode == 0 else 'inactive'


def read_status():
    state = service_state()
    health = None
    try:
        with urlopen(DASHBOARD + '/api/health', timeout=1) as response:
            candidate = json.load(response)
        if isinstance(candidate.get('peripheral'), dict) and 'reader_enabled' in candidate:
            health = candidate
    except (URLError, OSError, ValueError, AttributeError):
        pass
    running = state in {'active', 'activating', 'reloading'}
    if health:
        sensor = health['peripheral']
        failed = bool(health.get('failed_tasks') or sensor.get('last_error'))
        phase = 'error' if failed else ('running' if health.get('bike_connected') else 'waiting')
        if not running:
            phase = 'external'
        message = 'Bike connected' if health.get('bike_connected') else 'Waiting for your bike'
        if sensor.get('client_subscribed'):
            message += ' · BLE client subscribed'
        elif sensor.get('advertisement_registered'):
            message += ' · advertising to Zwift'
        if failed:
            message = 'Bridge needs attention; open Diagnostics'
        if phase == 'external':
            message = 'Bridge is running outside the desktop service'
    else:
        phase = 'starting' if running else 'off'
        message = 'Starting / waiting for the local API' if running else 'Bridge is stopped'
    return {'phase': phase, 'running': running, 'reachable': health is not None,
            'message': message, 'bike_connected': bool(health and health.get('bike_connected')),
            'client_subscribed': bool(health and health['peripheral'].get('client_subscribed'))}


def notify(title, message):
    try:
        subprocess.run(['notify-send', '--app-name=Echelon Bridge', '--icon=echelon-bridge',
                        title, message], capture_output=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_bridge(action):
    result = subprocess.run([str(PROJECT / 'bridge'), action], capture_output=True, text=True,
                            timeout=180 if action == 'start' else 25)
    if result.returncode:
        raise RuntimeError('Bridge command failed. Open a terminal and run the bridge logs command.')


def control(action):
    status = read_status()
    if action == 'stop':
        if status['running']:
            run_bridge('stop')
            if service_state() in {'active', 'activating', 'reloading'}:
                raise RuntimeError('The bridge service did not stop.')
        if not status['running'] and status['reachable']:
            notify('Stop the foreground bridge in its terminal', 'This server was started separately from the desktop service.')
        else:
            notify('Echelon Bridge stopped', 'Bike disconnected; Bluetooth power advertisement removed.')
        return
    if not status['running'] and not status['reachable']:
        run_bridge('start')
    deadline = time.monotonic() + 20
    while not status['reachable'] and time.monotonic() < deadline:
        time.sleep(0.5)
        status = read_status()
    if not status['reachable']:
        raise RuntimeError('The local server did not become ready. Check the bridge logs.')
    if action == 'open':
        subprocess.Popen(['xdg-open', DASHBOARD], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    notify('Echelon Bridge is running', 'Dashboard: ' + DASHBOARD + '\nRight-click the bicycle icon to stop.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['open', 'start', 'stop', 'status-json'])
    args = parser.parse_args()
    try:
        if args.action == 'status-json':
            print(json.dumps(read_status()))
            return 0
        runtime = Path(os.getenv('XDG_RUNTIME_DIR', str(PROJECT / '.cache')))
        runtime.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(runtime / 'echelon-bridge-control.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            control(args.action)
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        notify('Echelon Bridge needs attention', str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
