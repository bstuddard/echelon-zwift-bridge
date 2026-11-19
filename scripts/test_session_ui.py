"""Exercise the production ride dashboard with fixture readings and a temporary log."""
import asyncio
from pathlib import Path
import socket
import subprocess
import tempfile

import uvicorn

from echelon_bridge.app import create_app
from echelon_bridge.config import Settings

ROOT = Path(__file__).resolve().parents[1]


async def fixture_reader(bike, *args, **kwargs):
    bike.connected = bike.initialized = True
    bike.ingest(bytes.fromhex("f0 d2 01 14 d7"))
    while True:
        bike.ingest(bytes.fromhex("f0 d1 00 00 00 00 00 00 00 00 5a 00 00"))
        await asyncio.sleep(0.5)


async def main():
    with tempfile.TemporaryDirectory() as scratch, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        path = Path(scratch) / "test-ride.psv"
        app = create_app(Settings(reader=True, log_path=str(path)), reader=fixture_reader)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", log_level="warning"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("The fixture server exited before startup")
                    await asyncio.sleep(0.05)
            await asyncio.to_thread(subprocess.run, ["node", "frontend/tests/session-browser.mjs", url, str(path)],
                                    cwd=ROOT, check=True, timeout=90)
        finally:
            server.should_exit = True
            await task
        events = [row.split("|")[2] for row in path.read_text().splitlines()[1:]]
        assert events[0] == "start" and events[-1] == "finish" and "sample" in events


if __name__ == "__main__":
    asyncio.run(main())
