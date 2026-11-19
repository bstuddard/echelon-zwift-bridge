"""Create Start and Stop desktop shortcuts without changing PowerShell policy."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

# Paths travel as environment data, never as interpolated PowerShell code.
CREATE_SHORTCUT = r"""
$ErrorActionPreference = 'Stop'
$bridgeRoot = $env:ECHELON_SHORTCUT_ROOT
$destination = $env:ECHELON_SHORTCUT_DESTINATION
if (!$destination) { $destination = [Environment]::GetFolderPath('Desktop') }
if (!(Test-Path -LiteralPath $destination -PathType Container)) {
    throw 'Choose an existing destination folder for the shortcut.'
}
$destination = (Resolve-Path -LiteralPath $destination).Path
$bridgePython = Join-Path $bridgeRoot '.venv\Scripts\python.exe'
$shortcutShell = New-Object -ComObject WScript.Shell
$startPath = Join-Path $destination 'Start Echelon Bridge.lnk'
$legacyPath = Join-Path $destination 'Echelon Bridge.lnk'
if ((Test-Path -LiteralPath $legacyPath) -and !(Test-Path -LiteralPath $startPath)) {
    $legacy = $shortcutShell.CreateShortcut($legacyPath)
    $managedLegacy = (($legacy.TargetPath -eq $bridgePython -and $legacy.Arguments -eq '-m echelon_bridge.windows_launcher') -or
                      ($legacy.TargetPath -eq (Join-Path $bridgeRoot 'Start Echelon Bridge.bat') -and !$legacy.Arguments))
    if ($managedLegacy -and $legacy.WorkingDirectory -eq $bridgeRoot) {
        Move-Item -LiteralPath $legacyPath -Destination $startPath
    }
}
foreach ($action in @('Start', 'Stop')) {
    $shortcutPath = Join-Path $destination "$action Echelon Bridge.lnk"
    $bridgeBatch = Join-Path $bridgeRoot "$action Echelon Bridge.bat"
    $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
    if (Test-Path -LiteralPath $shortcutPath) {
        if ($shortcut.TargetPath -ne $bridgeBatch -or $shortcut.Arguments -or $shortcut.WorkingDirectory -ne $bridgeRoot) {
            # Also accept the original Python shortcut while migrating Start.
            if ($action -ne 'Start' -or $shortcut.TargetPath -ne $bridgePython -or
                $shortcut.Arguments -ne '-m echelon_bridge.windows_launcher' -or $shortcut.WorkingDirectory -ne $bridgeRoot) {
                throw "A different $action Echelon Bridge.lnk exists there. Choose another destination or remove that shortcut yourself."
            }
        }
    }
    $shortcut.TargetPath = $bridgeBatch
    $shortcut.Arguments = ''
    $shortcut.WorkingDirectory = $bridgeRoot
    $shortcut.Description = if ($action -eq 'Start') { 'Start the Echelon ride monitor or open its dashboard' } else { 'Finish recording and stop the Echelon ride monitor' }
    $shortcut.IconLocation = "$bridgePython,0"
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Output "Saved $shortcutPath"
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, help='Existing folder; defaults to your Windows desktop')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This installer requires Windows.')
    for action in ('Start', 'Stop'):
        if not (ROOT / f'{action} Echelon Bridge.bat').is_file():
            parser.error(f'The project is missing {action} Echelon Bridge.bat. Restore it before installing the shortcuts.')
    if not (ROOT / '.venv/Scripts/python.exe').is_file():
        parser.error('Run uv sync --frozen in the project folder first.')
    if not (ROOT / 'backend/frontend_dist/index.html').is_file():
        parser.error('Build the dashboard first: npm.cmd --prefix frontend ci, then npm.cmd --prefix frontend run build.')
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    env = {**os.environ, 'ECHELON_SHORTCUT_ROOT': str(ROOT),
           'ECHELON_SHORTCUT_DESTINATION': str(args.destination.resolve()) if args.destination else ''}
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', CREATE_SHORTCUT],
                            env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
