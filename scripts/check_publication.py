#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fail closed on private files/identifiers in Git candidates or release archives.

Reports file names and finding types, never matched secret values. Generic
loopback/unspecified addresses and synthetic test/documentation addresses are
allowed. Run before staging or pushing, and again on built release archives.
"""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import tarfile
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
CREDENTIAL = re.compile(
    r'(?:github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|'
    r'(?:AKIA|ASIA)[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|'
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
    r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})'
)
IPV4 = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
IPV6 = re.compile(r'(?<![A-Za-z0-9_-])(?:[A-Fa-f0-9]{0,4}:){2,}[A-Fa-f0-9:.]*(?![A-Za-z0-9_-])')
MAC = re.compile(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}')
DOCUMENTATION_NETWORKS = [ipaddress.ip_network(value) for value in (
    '192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24', '2001:db8::/32')]
PRIVATE_PARTS = {'.git', '.aws', '.codex', '.agents', '.ssh', '.gnupg', '.venv',
                 'node_modules', '__pycache__', '.pytest_cache', '.cache', '.sites-runtime',
                 'captures', 'screenshots', 'diagnostics'}


def private_values(root):
    """Read local values for comparison only; do not write them to reports."""
    values = [(str(Path.home()), 'personal home path'),
              (getpass.getuser(), 'personal username'),
              (socket.gethostname(), 'host identifier')]
    env_file = root / '.env'
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            match = re.match(r'\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$', line)
            if match and re.search(r'ADDRESS|TOKEN|SECRET|PASSWORD|PRIVATE|CREDENTIAL|HOST|URL', match[1]):
                value = match[2].strip('"\'')
                if len(value) >= 6:
                    values.append((value, 'configured private value'))
    phone_file = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'echelon-bridge/phone.json'
    if phone_file.is_file() and not phone_file.is_symlink():
        try:
            with phone_file.open() as stream:
                content = stream.read(16385)
            phone = json.loads(content) if len(content) <= 16384 else {}
            if isinstance(phone, dict):
                for key in ('serial', 'service', 'adb', 'server'):
                    value = phone.get(key)
                    if isinstance(value, str) and len(value) >= 6:
                        values.append((value, 'configured private phone value'))
        except (OSError, ValueError):
            pass
    return [(value, kind) for value, kind in values if len(value) >= 4]


def forbidden_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or any(part in PRIVATE_PARTS for part in path.parts):
        return True
    filename = path.name
    if filename.startswith('.env') and filename != '.env.example':
        return True
    return (filename in {'CODEX_PROMPT.md', 'phone.json'} or filename.endswith(('-phone.json', '.local.md', '.pem', '.key', '.p12', '.pfx', '.pyc', '.pyo', '.jsonl'))
            or '.bak' in filename or filename.endswith('-diagnostics.json'))


def inspect_text(text, secrets):
    findings = set()
    for value, kind in secrets:
        if value.casefold() in text.casefold():
            findings.add(kind)
    if CREDENTIAL.search(text):
        findings.add('credential pattern')
    if re.search(r'https?://[^/\s"<>]+:[^/\s"<>]+@', text):
        findings.add('URL credentials')
    for match in [*IPV4.finditer(text), *IPV6.finditer(text)]:
        try:
            address = ipaddress.ip_address(match[0])
        except ValueError:
            continue
        documented = any(address.version == net.version and address in net for net in DOCUMENTATION_NETWORKS)
        if not (address.is_loopback or address.is_unspecified or documented):
            findings.add('non-placeholder network address')
    for match in MAC.finditer(text):
        address = match[0].upper().replace('-', ':')
        if not address.startswith('AA:BB:CC:DD:EE:') and address != '00:00:00:00:00:00':
            findings.add('non-placeholder Bluetooth address')
    return sorted(findings)


def inspect_bytes(name, data, secrets):
    findings = []
    if forbidden_path(name):
        findings.append('private or generated file path')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        findings.append('unreviewed binary file')
    else:
        findings.extend(inspect_text(name + '\n' + text, secrets))
    return findings


def git_candidates(root):
    probe = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if probe.returncode == 0 and Path(probe.stdout.strip()).resolve() == root:
        command = ['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z']
        result = subprocess.check_output(command)
    else:
        # Review a fresh publication file list without initializing or editing
        # the worktree's own Git metadata.
        with tempfile.TemporaryDirectory(prefix='bridge-publication-') as temporary:
            gitdir = Path(temporary) / 'review.git'
            subprocess.run(['git', 'init', '--bare', '--quiet', str(gitdir)], check=True)
            result = subprocess.check_output(['git', '--git-dir=' + str(gitdir), '--work-tree=' + str(root),
                                              'ls-files', '--others', '--exclude-standard', '-z'])
    return sorted({name.decode() for name in result.split(b'\0') if name})


def inspect_archive(path, secrets):
    count, failures = 0, []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                count += 1
                findings = inspect_bytes(entry.filename, archive.read(entry), secrets)
                if findings:
                    failures.append((entry.filename, findings))
    else:
        with tarfile.open(path) as archive:
            for entry in archive.getmembers():
                if entry.isdir():
                    continue
                count += 1
                if not entry.isfile() or entry.uid or entry.gid or entry.uname or entry.gname:
                    failures.append((entry.name, ['non-normalized owner metadata or non-regular file']))
                    continue
                findings = inspect_bytes(entry.name, archive.extractfile(entry).read(), secrets)
                if findings:
                    failures.append((entry.name, findings))
    return count, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, action='append', default=[])
    args = parser.parse_args()
    secrets = private_values(PROJECT)
    failures = []
    files = git_candidates(PROJECT)
    for name in files:
        path = PROJECT / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            failures.append((name, ['unreviewed symbolic link or non-regular file']))
            continue
        findings = inspect_bytes(name, path.read_bytes(), secrets)
        if findings:
            failures.append((name, findings))
    print(f'Checked {len(files)} Git publication candidates.')
    for archive in args.archive:
        count, results = inspect_archive(archive, secrets)
        print(f'Checked {count} entries in {archive.name}.')
        failures.extend(results)
    if failures:
        for name, findings in failures:
            print(name + ': ' + ', '.join(findings))
        print('Publication check failed. Matched values have been withheld.')
        return 1
    print('PASS: no private files, known personal identifiers, non-placeholder addresses, or credential patterns found.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
