"""Optional, selected-phone video source. No phone controls or audio channel.

The scrcpy 4.x/5.x wire format is described in its official doc/develop.md.
scrcpy remains an external installation; no Android binaries are bundled here.
"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import tempfile

MAX_PACKET = 4 * 1024 * 1024
MAX_ADB_OUTPUT = 128 * 1024
MAX_SERVER_FILE = 16 * 1024 * 1024
SERVICE = re.compile(r"[A-Za-z0-9_-]{1,160}(?:\._adb-tls-connect\._tcp)?")
TLS_SUFFIX = "._adb-tls-connect._tcp"


class PhoneError(Exception):
    """Only fixed, identifier-free messages may be exposed to the browser."""


def read_private_json(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 16384:
                raise PhoneError("Phone configuration must be a small private file owned by your user.")
            content = stream.read(16385)
            if len(content) > 16384:
                raise PhoneError("Phone configuration is too large. Run phone setup again.")
            data = json.loads(content)
            if not isinstance(data, dict):
                raise PhoneError("Invalid phone configuration. Run phone setup again.")
            return data
    except FileNotFoundError:
        raise PhoneError("Select your phone first with uv run echelon-mirror-setup.") from None
    except (OSError, ValueError, TypeError):
        raise PhoneError("Phone setup could not be read. Run phone setup again.") from None


def server_digest(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SERVER_FILE:
                raise PhoneError("The scrcpy server file is invalid. Run phone setup again.")
            data = stream.read(MAX_SERVER_FILE + 1)
            if len(data) > MAX_SERVER_FILE:
                raise PhoneError("The scrcpy server file is too large. Run phone setup again.")
            return hashlib.sha256(data).hexdigest()
    except OSError:
        raise PhoneError("The scrcpy server could not be read. Run phone setup again.") from None


def selection_path():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "echelon-bridge/phone.json"


def tls_target(service):
    if not isinstance(service, str) or not SERVICE.fullmatch(service):
        raise PhoneError("Invalid selected phone. Run phone setup again.")
    return service if service.endswith(TLS_SUFFIX) else service + TLS_SUFFIX


def local_endpoint(value):
    if not isinstance(value, str) or len(value) > 200:
        raise PhoneError("Invalid phone connection settings. Run phone setup again.")
    if value.startswith("["):
        host, _, port = value[1:].rpartition("]:")
    else:
        host, _, port = value.rpartition(":")
    try:
        parts = host.split("%")
        address = ipaddress.ip_address(parts[0])
        if address.version == 4:
            first, second = address.packed[:2]
            valid = first == 10 or (first == 172 and 16 <= second <= 31) or (first == 192 and second == 168)
        else:
            valid = address.is_link_local or address.packed[0] & 0xfe == 0xfc
        if len(parts) > 1:
            valid = valid and len(parts) == 2 and address.version == 6 and address.is_link_local and bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", parts[1]))
        valid = valid and port.isdecimal() and 1 <= int(port) <= 65535
    except ValueError:
        valid = False
    if not valid:
        raise PhoneError("Invalid phone connection settings. Run phone setup again.")
    return value


@dataclass(frozen=True)
class PhoneSelection:
    adb: Path
    server: Path
    version: str
    serial: str
    service: str | None
    server_sha256: str

    def validate(self):
        if not re.fullmatch(r"[45]\.\d+(?:\.\d+)?", self.version):
            raise PhoneError("Phone mirroring requires a matching scrcpy 4.x or 5.x installation.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,160}", self.serial):
            raise PhoneError("Invalid selected phone. Run phone setup again.")
        if self.service is not None and not SERVICE.fullmatch(self.service):
            raise PhoneError("Invalid selected phone. Run phone setup again.")
        if not self.adb.is_absolute() or not self.adb.is_file() or not os.access(self.adb, os.X_OK):
            raise PhoneError("Android tools are missing. Run phone setup again.")
        if not self.server.is_absolute() or not self.server.is_file():
            raise PhoneError("The scrcpy server is missing. Run phone setup again.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.server_sha256):
            raise PhoneError("Invalid phone configuration. Run phone setup again.")
        if server_digest(self.server) != self.server_sha256:
            raise PhoneError("The scrcpy installation changed. Run phone setup again to verify it.")
        return self

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path is not None else selection_path()
        try:
            data = read_private_json(path)
            return cls(Path(data["adb"]), Path(data["server"]), data["version"], data["serial"],
                       data["service"], data["server_sha256"]).validate()
        except (OSError, ValueError, KeyError, TypeError):
            raise PhoneError("Phone setup could not be read. Run phone setup again.") from None

    def save(self, path=None):
        path = Path(path) if path is not None else selection_path()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.parent.stat().st_uid != os.getuid():
            raise PhoneError("Phone configuration directory has unexpected ownership.")
        path.parent.chmod(0o700)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise PhoneError("Phone configuration must be a regular file, not a link or device.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".phone-", delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                json.dump({"adb": str(self.adb), "server": str(self.server), "version": self.version,
                           "serial": self.serial, "service": self.service, "server_sha256": self.server_sha256}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class Adb:
    def __init__(self, executable):
        self.executable = str(executable)
        self.env = os.environ.copy()
        for name in ("ANDROID_SERIAL", "ANDROID_ADB_SERVER_ADDRESS", "ANDROID_ADB_SERVER_PORT", "ADB_SERVER_SOCKET", "ADB_TRACE", "ADB_VENDOR_KEYS"):
            self.env.pop(name, None)
        self.env["ADB_MDNS_AUTO_CONNECT"] = "adb-tls-connect"

    async def run(self, *args, timeout=8):
        process = await asyncio.create_subprocess_exec(self.executable, *args, env=self.env,
                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            async def collect():
                output = bytearray()
                while True:
                    chunk = await process.stdout.read(min(65536, MAX_ADB_OUTPUT + 1 - len(output)))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_ADB_OUTPUT:
                        raise PhoneError("Android tools returned too much data. Mirroring was stopped.")
                await process.wait()
                return bytes(output)
            output = await asyncio.wait_for(collect(), timeout)
            if process.returncode:
                raise PhoneError("The selected phone is unavailable. Check its connection and debugging setting.")
            return output.decode("utf-8", "replace").strip()
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                # Drain the bounded pipe after termination so a paused reader
                # cannot prevent asyncio from reaping the child transport.
                await asyncio.wait_for(process.communicate(), 2)

    async def check_local_server(self):
        await self.run("start-server")
        # ADB's host service exposes powerful commands. Refuse an existing
        # daemon bound to a network interface instead of broadening access.
        process = await asyncio.create_subprocess_exec("ss", "-ltnH", "sport = :5037", stdout=asyncio.subprocess.PIPE)
        output, _ = await process.communicate()
        addresses = [row.split()[3] for row in output.decode().splitlines() if row.strip()]
        if process.returncode or not addresses or any(value not in {"127.0.0.1:5037", "[::1]:5037"} for value in addresses):
            raise PhoneError("ADB must listen only on this computer's loopback interface.")

    async def services(self):
        result = await self.run("mdns", "services")
        services = []
        for row in result.splitlines():
            fields = row.split()
            if len(fields) >= 3 and fields[1].rstrip(".") == "_adb-tls-connect._tcp":
                try:
                    services.append((fields[0].rstrip("."), local_endpoint(fields[2])))
                except PhoneError:
                    pass
        return services

    async def selected(self, selection):
        await self.check_local_server()
        if selection.service:
            target = tls_target(selection.service)
            discovered = [(name, endpoint) for name, endpoint in await self.services()
                          if SERVICE.fullmatch(name) and tls_target(name) == target]
            if not discovered:
                raise PhoneError("Your selected phone is offline. Enable Wireless debugging on the same trusted network, then retry.")
            # Use only ADB's already-paired, named TLS transport. A raw
            # `adb connect IP:port` can also speak legacy plaintext ADB and
            # would make the unauthenticated discovery label our only check.
            # The ADB daemon establishes the paired TLS transport itself.
        else:
            target = selection.serial
        if await self.run("-s", target, "get-state") != "device":
            raise PhoneError("The selected phone is not authorized or connected. Unlock it and check debugging permissions.")
        identity = await self.run("-s", target, "shell", "getprop", "ro.serialno")
        if identity != selection.serial:
            raise PhoneError("Phone identity changed. Capture was refused; select your phone again.")
        return target


async def read_packet(reader):
    """Normalize scrcpy 4/5 video into size messages or a small binary envelope.

    Browser envelope: kind (1=config, 2=key, 3=delta), timestamp u64 BE,
    followed by one H.264 Annex-B access unit. No device metadata is relayed.
    """
    header = await asyncio.wait_for(reader.readexactly(12), 15)
    flags, length = struct.unpack("!QI", header)
    if flags & (1 << 63):
        session, width, height = struct.unpack("!III", header)
        if session not in (0x80000000, 0x80000001) or not (16 <= width <= 4096 and 16 <= height <= 4096):
            raise PhoneError("The phone sent invalid video dimensions.")
        return {"type": "size", "width": width, "height": height}
    if not 0 < length <= MAX_PACKET:
        raise PhoneError("The phone sent an invalid video packet.")
    payload = await asyncio.wait_for(reader.readexactly(length), 10)
    config = bool(flags & (1 << 62))
    key = bool(flags & (1 << 61))
    timestamp = flags & ((1 << 61) - 1)
    if timestamp > 2**53 - 1:
        raise PhoneError("The phone sent an invalid video timestamp.")
    return struct.pack("!BQ", 1 if config else 2 if key else 3, timestamp) + payload


class PhoneVideo:
    def __init__(self, selection):
        self.selection = selection
        self.adb = Adb(selection.adb)

    @asynccontextmanager
    async def open(self):
        target = await self.adb.selected(self.selection)
        session = secrets.randbelow(2**31)
        socket_name = f"localabstract:scrcpy_{session:08x}"
        jar = f"/data/local/tmp/echelon-video-{session:08x}.jar"
        connected = asyncio.get_running_loop().create_future()
        writer = process = None
        forwarded = uploaded = False

        def accept(reader, incoming):
            if connected.done():
                incoming.close()
            else:
                connected.set_result((reader, incoming))

        server = await asyncio.start_server(accept, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            uploaded = True
            await self.adb.run("-s", target, "push", str(self.selection.server), jar, timeout=15)
            forwarded = True
            await self.adb.run("-s", target, "reverse", socket_name, f"tcp:{port}")
            options = [f"scid={session:08x}", "log_level=error", "audio=false", "control=false", "clipboard_autosync=false",
                       "power_on=false", "cleanup=true", "tunnel_forward=false", "send_device_meta=false",
                       "send_dummy_byte=false", "send_frame_meta=true", "send_stream_meta=true", "video_codec=h264",
                       "max_size=1920", "max_fps=30", "video_bit_rate=4000000", "video_codec_options=i-frame-interval=1"]
            process = await asyncio.create_subprocess_exec(self.adb.executable, "-s", target, "shell",
                         f"CLASSPATH={jar}", "app_process", "/", "com.genymobile.scrcpy.Server", self.selection.version,
                         *options, env=self.adb.env, stdin=asyncio.subprocess.DEVNULL,
                         stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            reader, writer = await asyncio.wait_for(connected, 10)
            server.close()
            if await asyncio.wait_for(reader.readexactly(4), 10) != b"h264":
                raise PhoneError("The phone could not start the expected video format.")

            async def packets():
                while True:
                    yield await read_packet(reader)
            yield packets()
        finally:
            async def cleanup():
                nonlocal writer
                server.close()
                if writer is None and connected.done() and not connected.cancelled():
                    _, writer = connected.result()
                if writer:
                    writer.close()
                    try:
                        await asyncio.wait_for(writer.wait_closed(), 2)
                    except (OSError, asyncio.TimeoutError):
                        writer.transport.abort()
                try:
                    await asyncio.wait_for(server.wait_closed(), 2)
                except asyncio.TimeoutError:
                    pass
                if process is not None and process.returncode is None:
                    try:
                        await asyncio.wait_for(process.wait(), 2)
                    except asyncio.TimeoutError:
                        try:
                            process.terminate()
                            await asyncio.wait_for(process.wait(), 2)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                        except ProcessLookupError:
                            pass
                for args in (("reverse", "--remove", socket_name) if forwarded else (), ("shell", "rm", "-f", jar) if uploaded else ()):
                    if args:
                        try:
                            await self.adb.run("-s", target, *args, timeout=2)
                        except (PhoneError, OSError, asyncio.TimeoutError):
                            pass

            # A navigation close followed by server shutdown can cancel the
            # producer twice. Complete bounded cleanup even in that case.
            cleanup_task = asyncio.create_task(cleanup())
            cancelled = False
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup_task.result()
            if cancelled:
                raise asyncio.CancelledError
