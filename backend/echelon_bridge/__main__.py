"""One command starts the live bridge, with HTTP bound only to loopback."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path

from .config import Settings
from .diagnostics import configure_logging


def main():
    parser = argparse.ArgumentParser(description="Echelon → Zwift Bluetooth bridge (estimated power)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--http-only", action="store_true", help="Diagnostics only; no Bluetooth")
    modes.add_argument("--read-only", action="store_true", help="Read the bike without advertising to Zwift")
    modes.add_argument("--simulate", action="store_true", help="BLE smoke test only; advertises EchelonSIM-TEST")
    modes.add_argument("--scan", action="store_true", help="List nearby bike candidates locally without connecting")
    parser.add_argument("--adapter", help="Bike connection adapter, e.g. hci1")
    parser.add_argument("--power-adapter", help="Zwift advertisement adapter, e.g. hci0")
    parser.add_argument("--address", help="Select a particular bike's Bluetooth address")
    parser.add_argument("--trace", type=Path, help="Private JSONL capture; identifiers/auth payloads excluded")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check-config", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    try:
        settings = replace(Settings.from_env(), reader=not (args.http_only or args.simulate or args.scan),
                           advertise=not (args.http_only or args.read_only or args.scan), simulate=args.simulate)
        values = {key: getattr(args, key) for key in ("adapter", "power_adapter", "address", "trace") if getattr(args, key) is not None}
        settings = replace(settings, **values)
    except ValueError as exc:
        parser.error(str(exc))
    configure_logging(settings.log_level)
    if settings.reader and not settings.address:
        parser.error("Select a bike first: run echelon-bridge --scan, then set ECHELON_ADDRESS in .env or pass --address")
    if args.check_config:
        return
    if args.scan:
        from .bike_ble import BikeDiscovery
        async def scan():
            discovery = BikeDiscovery(settings)
            await discovery.scan()
            print(json.dumps(discovery.snapshot(identifiers=True), indent=2))
        asyncio.run(scan())
        return
    from .app import create_app
    import uvicorn
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
