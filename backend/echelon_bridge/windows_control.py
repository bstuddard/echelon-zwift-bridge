"""Graceful desktop shutdown through session-local Windows event objects."""
import ctypes
from ctypes import wintypes
import hashlib
from pathlib import Path

EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
ERROR_FILE_NOT_FOUND = 2
ERROR_ALREADY_EXISTS = 183


def _kernel32():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateEventW.restype = wintypes.HANDLE
    api.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    api.OpenEventW.restype = wintypes.HANDLE
    api.SetEvent.argtypes = [wintypes.HANDLE]
    api.SetEvent.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def _name(root, port):
    identity = f'{Path(root).resolve()}|{port}'.casefold().encode('utf-8')
    return 'Local\\EchelonBridge.' + hashlib.sha256(identity).hexdigest()


class StopControl:
    """Own the stop request and acknowledge only after server cleanup finishes."""
    def __init__(self, root, port=8000):
        self.api = _kernel32()
        self.name = _name(root, port)
        self.request = self.done = None

    def _create(self, suffix):
        # Default Windows ACLs come from the creator's token. Handles are not
        # inherited; the Local namespace scopes them to this Windows session.
        handle = self.api.CreateEventW(None, True, False, self.name + suffix)
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        if error == ERROR_ALREADY_EXISTS:
            self.api.CloseHandle(handle)
            raise RuntimeError('This checkout already has a server running or shutting down on that port.')
        return handle

    def __enter__(self):
        self.request = self._create('.stop')
        try:
            self.done = self._create('.done')
        except BaseException:
            self.api.CloseHandle(self.request)
            raise
        return self

    def requested(self):
        result = self.api.WaitForSingleObject(self.request, 0)
        if result not in (WAIT_OBJECT_0, WAIT_TIMEOUT):
            raise ctypes.WinError(ctypes.get_last_error())
        return result == WAIT_OBJECT_0

    def __exit__(self, *args):
        try:
            if not self.api.SetEvent(self.done):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(self.done)
            self.api.CloseHandle(self.request)


def request_stop(root, port=8000, timeout=15):
    """Signal this checkout only; never terminate a PID or kill other Python apps."""
    api = _kernel32()
    name = _name(root, port)
    request = api.OpenEventW(EVENT_MODIFY_STATE, False, name + '.stop')
    if not request:
        error = ctypes.get_last_error()
        if error == ERROR_FILE_NOT_FOUND:
            return False
        raise ctypes.WinError(error)
    done = None
    try:
        done = api.OpenEventW(SYNCHRONIZE, False, name + '.done')
        if not done:
            raise ctypes.WinError(ctypes.get_last_error())
        if not api.SetEvent(request):
            raise ctypes.WinError(ctypes.get_last_error())
        result = api.WaitForSingleObject(done, int(timeout * 1000))
        if result == WAIT_TIMEOUT:
            raise TimeoutError('Shutdown was requested but is still finishing. Check the server window or logs before trying again.')
        if result != WAIT_OBJECT_0:
            raise ctypes.WinError(ctypes.get_last_error())
        return True
    finally:
        if done:
            api.CloseHandle(done)
        api.CloseHandle(request)
