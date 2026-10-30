"""Release privacy checks must reject private data even when Git tracks it."""
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

spec = importlib.util.spec_from_file_location('publication_check', Path(__file__).resolve().parents[2] / 'scripts/check_publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


def test_addresses_and_credentials_are_checked_without_echoing_values():
    private_ip = '.'.join(map(str, (10, 42, 0, 7)))
    private_mac = ':'.join(['12', '34', '56', '78', '9A', 'BC'])
    credential = 'ghp_' + 'x' * 36
    for value, expected in [(private_ip, 'non-placeholder network address'),
                            (private_mac, 'non-placeholder Bluetooth address'),
                            (credential, 'credential pattern')]:
        result = publication.inspect_text(value, [])
        assert expected in result
        assert value not in str(result)
    assert publication.inspect_text('127.0.0.1 ::1 AA:BB:CC:DD:EE:01', []) == []
    assert publication.inspect_text('::before{content:""} ::after{color:red} ::backdrop{opacity:0}', []) == []


def test_personal_identifiers_are_blocked():
    value = 'example-personal-identifier'
    assert publication.inspect_text(value, [(value, 'configured private value')]) == ['configured private value']


def test_private_phone_identity_is_compared_without_echoing_it(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path))
    directory=tmp_path/'echelon-bridge';directory.mkdir()
    identity='private-phone-fixture-serial'
    (directory/'phone.json').write_text(json.dumps({'serial':identity,'service':'private-phone-fixture-service'}))
    secrets=publication.private_values(tmp_path)
    findings=publication.inspect_text(identity,secrets)
    assert 'configured private phone value' in findings
    assert identity not in str(findings)


def test_tracked_environment_file_is_not_hidden_by_gitignore(tmp_path):
    subprocess.run(['git', 'init', '--quiet', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('.env*\n!.env.example\n')
    (tmp_path / '.env').write_text('ECHELON_ADDRESS=AA:BB:CC:DD:EE:01\n')
    (tmp_path / '.env.example').write_text('ECHELON_ADDRESS=\n')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '-f', '.env'], check=True)
    files = publication.git_candidates(tmp_path)
    assert '.env' in files and '.env.example' in files
    assert publication.forbidden_path('.env')
    assert not publication.forbidden_path('.env.example')


def test_release_archive_rejects_private_files_and_binary_payloads(tmp_path):
    artifact = tmp_path / 'release.whl'
    with zipfile.ZipFile(artifact, 'w') as archive:
        archive.writestr('package/.env', 'PRIVATE=example\n')
        archive.writestr('package/payload.bin', bytes((255, 254)))
    count, failures = publication.inspect_archive(artifact, [])
    assert count == 2
    assert failures[0][1] == ['private or generated file path']
    assert failures[1][1] == ['unreviewed binary file']
