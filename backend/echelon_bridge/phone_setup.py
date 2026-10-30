"""Select one already-authorized Android phone for the local Mirror page."""
import argparse
import asyncio
import os
from pathlib import Path
import re
import shutil
import subprocess

from .phone import Adb, PhoneError, PhoneSelection, SERVICE, read_private_json, server_digest


def installation(adb_path=None, server_path=None, scrcpy_path=None):
    client = str(scrcpy_path or shutil.which("scrcpy") or "")
    if not client:
        raise PhoneError("Install scrcpy 4.x or 5.x first, then run phone setup again.")
    result = subprocess.run([client, "--version"], capture_output=True, text=True, timeout=10)
    match = re.search(r"^scrcpy ([45]\.\d+(?:\.\d+)?)\b", result.stdout, re.MULTILINE)
    if result.returncode or match is None:
        raise PhoneError("Use a scrcpy 4.x or 5.x client with its matching server.")
    version = match[1]
    portable = Path.home() / ".local/share/scrcpy" / version
    adb = Path(adb_path or shutil.which("adb") or portable / "adb")
    candidates = [Path(server_path)] if server_path else [Path(os.environ["SCRCPY_SERVER_PATH"])] if os.environ.get("SCRCPY_SERVER_PATH") else [portable / "scrcpy-server", Path(client).resolve().parent / "scrcpy-server", Path("/usr/share/scrcpy/scrcpy-server")]
    server = next((path for path in candidates if path.is_file()), None)
    if not adb.is_file() or not os.access(adb, os.X_OK) or server is None:
        raise PhoneError("Could not locate Android tools and the matching scrcpy server. Use --adb and --server for a portable installation.")
    return adb.resolve(), server.resolve(), version


async def select(adb, imported=None):
    if imported is not None:
        # The existing desktop helper's selection can be imported while the
        # phone is offline. No address, private key, or pairing code is copied.
        data = read_private_json(imported)
        service, serial = data.get("service"), data.get("serial")
        if not isinstance(service, str) or not SERVICE.fullmatch(service) or not isinstance(serial, str):
            raise PhoneError("The imported selection does not contain a valid paired-phone identity.")
        return serial, service
    await adb.check_local_server()
    rows = [row.split() for row in (await adb.run("devices", "-l")).splitlines()[1:] if row.strip()]
    authorized = [row for row in rows if len(row) >= 2 and row[1] == "device"]
    if len(authorized) != 1:
        raise PhoneError("Connect and authorize exactly one phone, then run setup again. USB or encrypted wireless debugging is supported.")
    target = authorized[0][0]
    serial = await adb.run("-s", target, "shell", "getprop", "ro.serialno")
    if any(field.startswith("usb:") for field in authorized[0]):
        return serial, None
    for name, endpoint in await adb.services():
        if target in {endpoint, name, name + "._adb-tls-connect._tcp"}:
            return serial, name
    # A USB serial without a topology field is still selected explicitly;
    # network targets must always match an encrypted discovery service.
    if target == serial:
        return serial, None
    raise PhoneError("The connected phone must use USB or Android's encrypted wireless pairing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-selection", type=Path, help="Import an existing private desktop mirroring selection")
    parser.add_argument("--adb", type=Path)
    parser.add_argument("--server", type=Path, help="Matching scrcpy-server file")
    parser.add_argument("--scrcpy", type=Path, help="scrcpy client executable")
    args = parser.parse_args()
    try:
        adb, server, version = installation(args.adb, args.server, args.scrcpy)
        serial, service = asyncio.run(select(Adb(adb), args.import_selection))
        PhoneSelection(adb, server, version, serial, service, server_digest(server)).validate().save()
    except PhoneError as exc:
        parser.error(str(exc))
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        parser.error("Phone setup failed. Check the installation and authorization; private details withheld.")
    print("Selected phone saved privately. Open the local dashboard's Phone mirror page and choose Start.")


if __name__ == "__main__":
    main()
