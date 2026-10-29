import asyncio
import os
from types import SimpleNamespace

import pytest
from httpx import AsyncClient, ASGITransport

from echelon_bridge.app import create_app
from echelon_bridge.bike_ble import BikeDiscovery
from echelon_bridge.config import Settings
from echelon_bridge.protocol import ECHELON_SERVICE

PINNED = 'AA:BB:CC:DD:EE:01'
OTHER = 'AA:BB:CC:DD:EE:02'


@pytest.fixture
def clean_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith('ECHELON_') or name in {'BLE_ADVERTISE', 'BLE_POWER_ADAPTER', 'LOG_LEVEL'}:
            monkeypatch.delenv(name)


def test_env_loads_pin_without_modifying_process_environment(tmp_path, monkeypatch, clean_env):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(f'ECHELON_ADDRESS="{PINNED}"\nECHELON_BLE=1\nBLE_ADVERTISE=true\n')
    settings = Settings.from_env()
    assert settings.address == PINNED
    assert settings.reader and settings.advertise
    assert 'ECHELON_ADDRESS' not in os.environ


def test_explicit_environment_overrides_file(tmp_path, monkeypatch, clean_env):
    env_file = tmp_path / '.env'
    env_file.write_text(f'ECHELON_ADDRESS={PINNED}\n')
    monkeypatch.setenv('ECHELON_ADDRESS', OTHER)
    assert Settings.from_env(env_file).address == OTHER


@pytest.mark.parametrize('value', ['not-a-bluetooth-address', '${OTHER_ADDRESS}', '$(touch injected-file)'])
def test_invalid_pin_fails_instead_of_enabling_discovery(tmp_path, monkeypatch, clean_env, value):
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / '.env'
    env_file.write_text(f'ECHELON_ADDRESS={value}\n')
    with pytest.raises(ValueError, match='Bluetooth address'):
        Settings.from_env(env_file)
    assert not (tmp_path / 'injected-file').exists()


def test_missing_pin_never_connects_to_another_echelon():
    class Scanner:
        @classmethod
        async def discover(cls, **kwargs):
            bike = SimpleNamespace(address=OTHER, name='ECH-another-bike')
            advertisement = SimpleNamespace(local_name=bike.name, service_uuids=[ECHELON_SERVICE])
            return {OTHER: (bike, advertisement)}
    async def run():
        discovery = BikeDiscovery(Settings(address=PINNED), Scanner)
        with pytest.raises(RuntimeError, match='not found'):
            await discovery.find()
    asyncio.run(run())


def test_pin_status_is_visible_without_disclosing_address():
    async def run():
        app = create_app(Settings(address=PINNED))
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url='http://localhost') as client:
            response = await client.get('/api/health')
            assert response.json()['bike_selection'] == 'pinned_address'
            assert PINNED not in response.text
    asyncio.run(run())


def test_cli_without_selected_bike_fails_before_startup(monkeypatch, capsys):
    from echelon_bridge.__main__ import main
    monkeypatch.setattr(Settings, 'from_env', classmethod(lambda cls: Settings()))
    monkeypatch.setattr('sys.argv', ['echelon-bridge'])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert 'Select a bike first' in capsys.readouterr().err


def test_cli_scan_lists_candidates_without_connecting(monkeypatch, capsys):
    from echelon_bridge.__main__ import main
    monkeypatch.setattr(Settings, 'from_env', classmethod(lambda cls: Settings()))
    monkeypatch.setattr('sys.argv', ['echelon-bridge', '--scan'])
    async def scan(discovery):
        bike = SimpleNamespace(address=PINNED, name='ECH-test')
        advertisement = SimpleNamespace(local_name=bike.name, service_uuids=[ECHELON_SERVICE])
        discovery.devices = [(bike, advertisement)]
    def reject_connection(*args, **kwargs):
        pytest.fail('Scan mode must not construct a Bluetooth client')
    monkeypatch.setattr(BikeDiscovery, 'scan', scan)
    monkeypatch.setattr('bleak.BleakClient', reject_connection)
    main()
    assert PINNED in capsys.readouterr().out


def test_cli_config_preflight_validates_without_starting_the_server(monkeypatch):
    from echelon_bridge.__main__ import main
    monkeypatch.setattr(Settings, 'from_env', classmethod(lambda cls: Settings()))
    monkeypatch.setattr('sys.argv', ['echelon-bridge', '--address', PINNED, '--check-config'])
    def reject_startup(*args, **kwargs):
        pytest.fail('Configuration preflight must not start a server')
    monkeypatch.setattr('uvicorn.run', reject_startup)
    main()
