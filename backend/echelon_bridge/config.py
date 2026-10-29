"""Startup-only configuration. The HTTP API cannot change bike or power data."""
from dataclasses import dataclass
import os
from pathlib import Path
import re
from dotenv import dotenv_values


def enabled(name: str, default: bool = False, *, environ=None) -> bool:
    environ = os.environ if environ is None else environ
    return str(environ.get(name) or str(int(default))).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    reader: bool = False
    advertise: bool = False
    simulate: bool = False
    adapter: str | None = None
    power_adapter: str | None = None
    address: str | None = None
    trace: Path | None = None
    log_level: str = "INFO"

    def __post_init__(self):
        if self.reader and self.simulate:
            raise ValueError("Simulation and the live bike reader cannot run together")
        for value in (self.adapter, self.power_adapter):
            if value and not re.fullmatch(r"hci\d+", value):
                raise ValueError("Bluetooth adapter must be named hci0, hci1, etc.")
        if self.address and not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", self.address):
            raise ValueError("ECHELON_ADDRESS must be a Linux Bluetooth address")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")

    @property
    def name(self) -> str:
        return "EchelonSIM-TEST" if self.simulate else "EchelonPython"

    @classmethod
    def from_env(cls, env_file: Path | None = None):
        # Parse data only: no shell execution or variable expansion. Explicit
        # process environment takes precedence, then .env, then defaults.
        env_file = Path.cwd() / ".env" if env_file is None else env_file
        values = {**dotenv_values(env_file, interpolate=False), **os.environ}
        return cls(
            reader=enabled("ECHELON_BLE", environ=values), advertise=enabled("BLE_ADVERTISE", environ=values),
            simulate=enabled("ECHELON_SIMULATE", environ=values),
            adapter=values.get("ECHELON_ADAPTER") or None,
            power_adapter=values.get("BLE_POWER_ADAPTER") or None,
            address=values.get("ECHELON_ADDRESS") or None,
            trace=Path(values["ECHELON_TRACE"]) if values.get("ECHELON_TRACE") else None,
            log_level=(values.get("LOG_LEVEL") or "INFO").upper(),
        )
