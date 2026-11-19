"""One command starts the live bridge, with HTTP bound only to loopback."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path

from . import config
from .config import Settings
from .diagnostics import configure_logging


def main(argv=None):
    parser = argparse.ArgumentParser(description="Echelon bike monitor and Linux Zwift bridge")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--http-only", action="store_true", help="Diagnostics only; no Bluetooth")
    modes.add_argument("--read-only", action="store_true", help="Read the bike without advertising to Zwift")
    modes.add_argument("--simulate", action="store_true", help="Linux BLE smoke test; advertises EchelonSIM-TEST")
    modes.add_argument("--scan", action="store_true", help="List nearby bike candidates locally without connecting")
    parser.add_argument("--adapter", help="Bike connection adapter, e.g. hci1")
    parser.add_argument("--power-adapter", help="Zwift advertisement adapter, e.g. hci0")
    parser.add_argument("--address", help="Select a particular bike's Bluetooth address")
    parser.add_argument("--trace", type=Path, help="Private JSONL capture; identifiers/auth payloads excluded")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="Open the ride dashboard in your browser after startup")
    parser.add_argument("--check-config", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    try:
        settings = replace(Settings.from_env(), reader=not (args.http_only or args.simulate or args.scan),
                           advertise=not (config.WINDOWS or args.http_only or args.read_only or args.scan),
                           simulate=args.simulate)
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
    from .ws_transport import LocalWebSocketProtocol
    import uvicorn
    options = dict(host="127.0.0.1", port=args.port, access_log=False,
                   ws=LocalWebSocketProtocol, ws_max_size=1024, ws_per_message_deflate=False)
    app = create_app(settings)
    if args.open or config.WINDOWS:
        import webbrowser

        class DashboardServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started and args.open:
                    await asyncio.to_thread(webbrowser.open, f"http://127.0.0.1:{args.port}/")

        server = DashboardServer(uvicorn.Config(app, **options))
        if config.WINDOWS:
            from .windows_control import StopControl
            with StopControl(Path.cwd(), args.port) as control:
                async def check_stop():
                    if control.requested():
                        server.should_exit = True
                server.config.callback_notify = check_stop
                server.config.timeout_notify = 0.5
                server.run()
        else:
            server.run()
    else:
        uvicorn.run(app, **options)


if __name__ == "__main__":
    main()
