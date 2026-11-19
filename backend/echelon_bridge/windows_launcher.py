"""Start, open, or gracefully stop the bridge from Windows batch files."""
import argparse
import http.client
import json
from pathlib import Path
import sys
import webbrowser

from .__main__ import main as run_bridge

URL = "http://127.0.0.1:8000/"


def bridge_running():
    connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=3)
    try:
        connection.request("GET", "/api/")
        response = connection.getresponse()
        body = response.read(8193)
        if response.status != 200 or len(body) > 8192:
            raise ValueError("Unexpected local server response")
        info = json.loads(body)
        if not isinstance(info, dict) or info.get("app") != "Echelon \u2192 Zwift":
            raise ValueError("Unexpected local server response")
        return True
    except ConnectionRefusedError:
        return False
    except (OSError, ValueError, http.client.HTTPException):
        raise RuntimeError("Port 8000 is busy or unresponsive. Close the other local server and try again.") from None
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop', action='store_true', help='Finish recording and shut down this checkout\'s server')
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        raise RuntimeError("This shortcut launcher is for Windows. Use echelon-bridge on Linux.")
    if args.stop:
        from .windows_control import request_stop
        if request_stop(Path.cwd()):
            print('Echelon Bridge stopped.')
        elif bridge_running():
            raise RuntimeError('The running bridge does not have this checkout\'s stop control. Stop it with Ctrl+C and restart it using Start Echelon Bridge.bat.')
        else:
            print('Echelon Bridge is already stopped.')
        return
    if bridge_running():
        webbrowser.open(URL)
        return
    print("Starting Echelon Bridge. Keep this window open during your ride.")
    print("Press Ctrl+C here to stop the server and finish any active recording.")
    run_bridge(["--open"])


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code in (None, 0):
            raise
        if not isinstance(exc, SystemExit):
            print(f"Cannot start Echelon Bridge: {exc}", file=sys.stderr)
        if sys.stdin.isatty():
            input("Press Enter to close this window.")
        raise SystemExit(1)
