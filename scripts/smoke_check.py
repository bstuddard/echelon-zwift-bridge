#!/usr/bin/env python3
"""Check a running local bridge; independent radio discovery is still manual."""
import argparse
import json
import sys
from urllib.error import URLError
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--require-advertising", action="store_true")
    parser.add_argument("--require-bike", action="store_true")
    parser.add_argument("--require-subscriber", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024..65535")
    try:
        data = []
        for route in ("health", "metrics"):
            with urlopen(f"http://127.0.0.1:{args.port}/api/{route}", timeout=5) as response:
                data.append(json.load(response))
        health, metrics = data
    except (URLError, OSError, ValueError) as exc:
        print(f"Local bridge check failed: {exc}", file=sys.stderr)
        return 1
    peripheral = health["peripheral"]
    print(json.dumps({"server": health["status"], "reader": health["reader_status"],
                      "simulated": health["simulated"], "power_available": health["power_available"],
                      "cadence_rpm": metrics["cadence_rpm"], "estimated_watts": metrics["estimated_watts"],
                      "peripheral": peripheral}, indent=2))
    failures = []
    if health["failed_tasks"]:
        failures.append("background task stopped")
    if args.require_advertising and not (peripheral["gatt_started"] and peripheral["advertisement_registered"]
                                         and (peripheral["adapter_advertising_active"] or peripheral["client_subscribed"])):
        failures.append("power sensor is not registered/active")
    if args.require_bike and (health["simulated"] or not metrics["power_available"] or not metrics["initialized"]):
        failures.append("fresh live bike data is unavailable")
    if args.require_subscriber and not peripheral["client_subscribed"]:
        failures.append("no BLE client has subscribed")
    if failures:
        print("Pending: " + "; ".join(failures), file=sys.stderr)
        return 2
    print("Local checks passed. Verify over-the-air discovery and Zwift pairing on the other device.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
