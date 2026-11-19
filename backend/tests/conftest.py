import sys

# These suites exercise the Linux desktop service, BlueZ peripheral, and
# scrcpy transport. Windows runs the shared reader, HTTP and dashboard tests.
collect_ignore = (
    ["test_desktop.py", "test_peripheral.py", "test_mirror.py", "test_mirror_security.py"]
    if sys.platform == "win32" else []
)
