"""An opt-in, same-origin WebSocket for one view-only phone stream."""
import asyncio
import hmac
import ipaddress
import re
import secrets

from fastapi import WebSocket, WebSocketDisconnect

from .phone import PhoneError, PhoneSelection, PhoneVideo


def loopback_authority(host):
    match = re.fullmatch(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::([0-9]{1,5}))?", host)
    return bool(match and (match[1] is None or 1 <= int(match[1]) <= 65535))


class Mirror:
    HEARTBEAT_TIMEOUT = 30
    SEND_TIMEOUT = 3
    def __init__(self, source_factory=None):
        self.token = secrets.token_urlsafe(32)
        self.lock = asyncio.Lock()
        self.source_factory = source_factory
        self.session_task = None

    def status(self):
        try:
            if self.source_factory is None:
                PhoneSelection.load()
            return {"configured": True, "active": self.lock.locked(), "token": self.token,
                    "message": "Ready for your selected phone. Capture starts only when you choose Start."}
        except PhoneError as exc:
            return {"configured": False, "active": False, "message": str(exc)}

    async def shutdown(self):
        if self.session_task is not None:
            self.session_task.cancel()
            await asyncio.gather(self.session_task, return_exceptions=True)

    def authorized(self, socket):
        host = socket.headers.get("host", "")
        origin = socket.headers.get("origin", "")
        try:
            local_peer = socket.client is not None and ipaddress.ip_address(socket.client.host).is_loopback
        except ValueError:
            return False
        scheme = "https" if socket.scope.get("scheme") == "wss" else "http"
        protocols = socket.scope.get("subprotocols", [])
        return (local_peer and loopback_authority(host) and origin == f"{scheme}://{host}"
                and len(protocols) == 2 and protocols[0] == "echelon-mirror" and protocols[1].isascii()
                and hmac.compare_digest(protocols[1], "ticket." + self.token))

    async def stream(self, socket: WebSocket):
        if not self.authorized(socket):
            await socket.close(code=1008)
            return
        await socket.accept(subprotocol="echelon-mirror")
        if self.lock.locked():
            await socket.send_json({"type": "error", "message": "A phone mirror is already open. Stop that session first."})
            await socket.close(code=1013)
            return
        async with self.lock:
            async def send_video():
                source = self.source_factory() if self.source_factory else PhoneVideo(PhoneSelection.load()).open()
                await socket.send_json({"type": "starting"})
                async with source as packets:
                    async for packet in packets:
                        if isinstance(packet, dict):
                            await asyncio.wait_for(socket.send_json(packet), self.SEND_TIMEOUT)
                        else:
                            await asyncio.wait_for(socket.send_bytes(packet), self.SEND_TIMEOUT)

            async def receive_heartbeat():
                while True:
                    message = await asyncio.wait_for(socket.receive(), self.HEARTBEAT_TIMEOUT)
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("text") != "keepalive":
                        raise PhoneError("Only video viewing is supported. The session was stopped.")

            sender = asyncio.create_task(send_video())
            receiver = asyncio.create_task(receive_heartbeat())
            self.session_task = asyncio.current_task()
            try:
                done, _ = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            except PhoneError as exc:
                await self._error(socket, str(exc))
            except (asyncio.TimeoutError, OSError, EOFError):
                await self._error(socket, "The phone video connection ended. Check the phone and retry.")
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                sender.cancel()
                receiver.cancel()
                await asyncio.gather(sender, receiver, return_exceptions=True)
                self.session_task = None
                try:
                    await socket.close()
                except (WebSocketDisconnect, RuntimeError, OSError):
                    pass

    async def _error(self, socket, message):
        try:
            await socket.send_json({"type": "error", "message": message})
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
