"""Same-origin session controls for the local ride dashboard."""
import asyncio
import ipaddress
import subprocess
import sys

from fastapi import HTTPException, Request

from .mirror import loopback_authority
from .session_log import LogError


def install_sessions(api, session, settings):
    picker = asyncio.Lock()

    def authorize(request):
        host = request.headers.get("host", "")
        try:
            local = request.client and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            local = False
        if not local or not loopback_authority(host) or request.headers.get("origin") != f"{request.url.scheme}://{host}":
            raise HTTPException(403, "Open the dashboard on this computer.")
        revision = request.headers.get("x-session-revision")
        if revision != session.revision:
            raise HTTPException(409, "Session changed. Refresh the dashboard.")
        if not settings.reader or settings.simulate:
            raise HTTPException(409, "Start the live bike reader to record a session.")
        return revision

    @api.post("/session/pick-log")
    async def pick_log(request: Request):
        authorize(request)
        if picker.locked():
            raise HTTPException(409, "The log chooser is already open.")
        async with picker:
            try:
                result = await asyncio.to_thread(
                    subprocess.run, [sys.executable, "-m", "echelon_bridge.session_log"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    check=True, timeout=180, encoding="utf-8")
            except (OSError, subprocess.SubprocessError):
                raise HTTPException(503, "Type the full path to a .psv log file instead.") from None
        return {"path": result.stdout}

    @api.post("/session/start")
    async def start(request: Request):
        revision = authorize(request)
        if request.headers.get("content-type", "").split(";")[0] != "text/plain":
            raise HTTPException(415, "Send a local log path as plain text.")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                raise HTTPException(413, "Log path is too long.")
            body.extend(chunk)
        try:
            location = body.decode("utf-8")
            return await asyncio.shield(session.start(location, revision))
        except UnicodeDecodeError:
            raise HTTPException(400, "Invalid text in log path.") from None
        except LogError as exc:
            raise HTTPException(400, str(exc)) from None
        except OSError:
            raise HTTPException(400, "Cannot open that log. Check the folder, permissions and whether it is already in use.") from None
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from None

    @api.post("/session/finish")
    async def finish(request: Request):
        revision = authorize(request)
        try:
            return await asyncio.shield(session.finish(revision))
        except LogError as exc:
            raise HTTPException(503, str(exc)) from None
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from None
