"""User-selected append-only ride logs, shared by the Linux and Windows readers."""
import asyncio
import os
from pathlib import Path
import stat
import sys
from urllib.parse import unquote, urlsplit
from uuid import uuid4

HEADER = b"utc|session_id|event|elapsed_s|cadence_rpm|resistance|watts|avg_watts|distance_km_est|ftp_watts_est\n"


class LogError(ValueError):
    pass


def history_path(location):
    """Validate a local history path without touching the filesystem."""
    if not isinstance(location, str) or not location or len(location) > 4096 or any(ord(c) < 32 for c in location):
        raise LogError("Enter the full path to a .psv file.")
    path = Path(location)
    if not path.is_absolute() or path.suffix.lower() != ".psv":
        raise LogError("Choose a .psv file using its full local path.")
    if os.name == "nt" and (path.drive.startswith("\\\\") or any(":" in p or Path(p).is_reserved() for p in path.parts[1:])):
        raise LogError("Choose a normal file on a local Windows drive.")
    return path


def open_history(location):
    path = history_path(location)
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    if info and (not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise LogError("Choose a regular .psv file.")
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    handle = os.fdopen(os.open(path, flags, 0o600), "r+b", buffering=0)
    try:
        opened = os.fstat(handle.fileno())
        entry = path.lstat()
        if not stat.S_ISREG(entry.st_mode) or not os.path.samestat(opened, entry) or opened.st_nlink > 1:
            raise LogError("Choose a regular .psv file.")
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if handle.seek(0, os.SEEK_END):
            handle.seek(0)
            if handle.readline(len(HEADER) + 1) != HEADER:
                raise LogError("This file contains other data. Choose a new file or an existing Echelon session log.")
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                raise LogError("The existing log ends with a partial row. Choose a new file.")
        elif handle.write(HEADER) != len(HEADER):
            raise OSError("Incomplete log header")
        return handle
    except BaseException:
        handle.close()
        raise


async def portal_file():
    """Ask the Linux desktop portal, including on Wayland desktops without Tk."""
    from dbus_next import Message, MessageType, Variant
    from dbus_next.aio import MessageBus

    bus = await MessageBus().connect()
    try:
        desktop = "/org/freedesktop/portal/desktop"
        service = "org.freedesktop.portal.Desktop"
        interface = "org.freedesktop.portal.Request"
        token = "echelon_" + uuid4().hex
        sender = bus.unique_name[1:].replace(".", "_")
        handle = f"{desktop}/request/{sender}/{token}"
        response = asyncio.get_running_loop().create_future()

        def receive(message):
            if (message.message_type == MessageType.SIGNAL and message.path == handle and
                    message.interface == interface and message.member == "Response" and not response.done()):
                response.set_result(message.body)

        bus.add_message_handler(receive)
        rule = f"type='signal',sender='{service}',interface='{interface}',member='Response'"
        await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                               interface="org.freedesktop.DBus", member="AddMatch", signature="s", body=[rule]))
        options = {"handle_token": Variant("s", token), "current_name": Variant("s", "echelon-rides.psv")}
        reply = await bus.call(Message(destination=service, path=desktop, interface="org.freedesktop.portal.FileChooser",
                                       member="SaveFile", signature="ssa{sv}", body=["", "Choose a ride history log", options]))
        if reply.message_type == MessageType.ERROR:
            raise OSError("Desktop file chooser unavailable")
        handle, = reply.body
        code, result = await response
        if code == 1:
            return ""
        if code != 0:
            raise OSError("Desktop file chooser unavailable")
        uri = urlsplit(result["uris"].value[0])
        if uri.scheme != "file" or uri.netloc not in {"", "localhost"}:
            raise LogError("Choose a file on this computer.")
        return unquote(uri.path)
    finally:
        bus.disconnect()


def choose_file():
    """Run the native dialog on its own main thread, outside the server."""
    from tkinter import Tk, filedialog
    window = Tk()
    window.withdraw()
    try:
        window.attributes("-topmost", True)
        path = filedialog.asksaveasfilename(parent=window, title="Choose a ride history log",
                                            defaultextension=".psv", initialfile="echelon-rides.psv",
                                            filetypes=[("Ride history", "*.psv")], confirmoverwrite=False)
        return path
    finally:
        window.destroy()


if __name__ == "__main__":
    if sys.platform == "linux":
        try:
            selected = asyncio.run(portal_file())
        except OSError:
            selected = choose_file()
    else:
        selected = choose_file()
    sys.stdout.buffer.write(selected.encode("utf-8"))
