#!/usr/bin/env python3
"""Install user-local launchers and an Omarchy bar widget for Echelon Bridge."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
PLUGIN_ID = 'local.echelon-bridge'


def desktop_quote(value):
    escaped = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    return '"' + escaped + '"'


def launcher(helper, icon, *, stop=False):
    name = 'Stop Echelon Bridge' if stop else 'Echelon Bridge'
    action = 'stop' if stop else 'open'
    text = f'''[Desktop Entry]
Version=1.0
Type=Application
Name={name}
Comment={'Disconnect the bike and stop the Zwift power sensor' if stop else 'Start the bike bridge and open its local dashboard'}
Exec={desktop_quote(helper)} {action}
Icon={icon}
Terminal=false
StartupNotify=false
Categories=Utility;
Keywords=Echelon;Bike;Zwift;Bluetooth;Bridge;
'''
    if not stop:
        text += f'''Actions=Stop;

[Desktop Action Stop]
Name=Stop bridge
Exec={desktop_quote(helper)} stop
Icon={icon}
'''
    return text


def stage_files(stage):
    user_home = Path.home()
    helper = user_home / '.local/bin/echelon-bridge-control'
    icon = user_home / '.local/share/icons/hicolor/scalable/apps/echelon-bridge.svg'
    python = Path(sys.executable).resolve()
    files = {
        '.local/bin/echelon-bridge-control': '#!/bin/sh\n# Generated Echelon Bridge desktop control.\nexec ' + shlex.quote(str(python)) + ' ' + shlex.quote(str(PROJECT / 'desktop/bridge_control.py')) + ' "$@"\n',
        '.local/share/applications/echelon-bridge.desktop': launcher(helper, icon),
        '.local/share/applications/echelon-bridge-stop.desktop': launcher(helper, icon, stop=True),
        '.local/share/icons/hicolor/scalable/apps/echelon-bridge.svg': (PROJECT / 'desktop/echelon-bridge.svg').read_text(),
    }
    for name in ('manifest.json', 'Widget.qml'):
        files[f'.config/omarchy/plugins/{PLUGIN_ID}/{name}'] = (PROJECT / 'desktop/omarchy-plugin' / name).read_text()
    for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.txt'):
        files[f'.config/omarchy/plugins/{PLUGIN_ID}/{name}'] = (PROJECT / name).read_text()
    for relative, contents in files.items():
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        path.chmod(0o755 if relative.endswith('echelon-bridge-control') else 0o644)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-only', type=Path, help='Render/validate files here without installing or changing the desktop')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='echelon-desktop-') as temporary:
        stage = args.stage_only.resolve() if args.stage_only else Path(temporary)
        files = stage_files(stage)
        for entry in (stage / '.local/share/applications').glob('*.desktop'):
            subprocess.run(['desktop-file-validate', str(entry)], check=True)
        subprocess.run(['omarchy', 'plugin', 'validate', str(stage / f'.config/omarchy/plugins/{PLUGIN_ID}')], check=True)
        if args.stage_only:
            print('Validated desktop files and widget staged at', stage)
            return
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        config = Path.home() / '.config/omarchy/shell.json'
        if config.is_file():
            backup = config.with_name(config.name + '.bak.echelon-' + stamp)
            shutil.copy2(config, backup)
            print('Bar configuration backup:', backup)
        for relative in files:
            source = stage / relative
            destination = Path.home() / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                raise RuntimeError('Refusing to replace a symlink: ' + str(destination))
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                shutil.copy2(destination, destination.with_name(destination.name + '.bak.' + stamp))
            shutil.copy2(source, destination)
        subprocess.run(['omarchy-shell', 'shell', 'rescanPlugins'], check=True)
        subprocess.run(['omarchy', 'plugin', 'enable', PLUGIN_ID, '--section', 'right', '--before', 'omarchy.bluetooth'], check=True)
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database', str(Path.home() / '.local/share/applications')], check=True)
        print('Installed Echelon Bridge and Stop Echelon Bridge launchers, plus the top-bar bicycle widget.')


if __name__ == '__main__':
    main()
