"""Time-weighted statistics and local history for one explicit ride at a time."""
import asyncio
from collections import deque
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from .session_log import LogError, open_history
from .state import STALE_AFTER_SECONDS

FTP_SECONDS = 20 * 60
# Default cadence-based speed in the QZ Echelon Connect Sport implementation.
KPH_PER_RPM = 0.37497622


class RideStats:
    def __init__(self, now):
        self.start = self.last = now
        self.distance_km = self.power_seconds = self.joules = 0.0
        self.window = deque()
        self.window_joules = 0.0
        self.ftp = None
        self.previous_cadence = self.previous_watts = self.connection = None

    def sample(self, now, cadence, watts, connection):
        dt = now - self.last
        continuous = 0 < dt <= STALE_AFTER_SECONDS and self.connection == connection
        if continuous and cadence is not None and self.previous_cadence is not None:
            self.distance_km += self.previous_cadence * KPH_PER_RPM * dt / 3600
        if continuous and watts is not None and self.previous_watts is not None:
            energy = self.previous_watts * dt
            self.joules += energy
            self.power_seconds += dt
            self.window.append((self.last, now, self.previous_watts))
            self.window_joules += energy
            cutoff = now - FTP_SECONDS
            while self.window and self.window[0][1] <= cutoff:
                start, end, power = self.window.popleft()
                self.window_joules -= (end - start) * power
            if self.window and self.window[0][0] <= cutoff:
                start, end, power = self.window[0]
                self.window_joules -= (cutoff - start) * power
                self.window[0] = (cutoff, end, power)
                self.ftp = max(self.ftp or 0, round(0.95 * self.window_joules / FTP_SECONDS))
        elif dt > 0:
            self.window.clear()
            self.window_joules = 0.0
        self.last, self.previous_cadence, self.previous_watts, self.connection = now, cadence, watts, connection

    def snapshot(self):
        return {"elapsed_s": int(self.last - self.start), "distance_km": round(self.distance_km, 4),
                "avg_watts": round(self.joules / self.power_seconds) if self.power_seconds else None,
                "ftp_watts": self.ftp,
                "continuous_power_s": int(self.last - self.window[0][0]) if self.window else 0}


class RideSession:
    def __init__(self, bike):
        self.bike = bike
        self.status = "idle"
        self.revision = uuid4().hex
        self.lock = asyncio.Lock()
        self.stats = None
        self.handle = self.worker = self.error = None

    def snapshot(self):
        return {"status": self.status, "revision": self.revision, "error": self.error,
                **(self.stats.snapshot() if self.stats else {})}

    def record(self, event):
        now = monotonic()
        bike = self.bike
        fresh = bike.connected and bike.initialized and not bike.simulated and not bike.auth_required and not bike.stale(now)
        cadence, watts = bike.live_values(now=now)
        self.stats.sample(now, cadence if fresh else None, watts if fresh and bike.resistance is not None else None, bike.reconnects)
        summary = self.stats.snapshot()
        values = [datetime.now(timezone.utc).isoformat(timespec="milliseconds"), self.revision, event, summary["elapsed_s"],
                  cadence if fresh else None, bike.resistance if fresh else None, self.stats.previous_watts,
                  summary["avg_watts"], summary["distance_km"], summary["ftp_watts"]]
        row = "|".join("" if value is None else str(value) for value in values) + "\n"
        return row.encode("ascii")

    async def write(self, event):
        row = self.record(event)
        try:
            count = await asyncio.to_thread(self.handle.write, row)
            if count != len(row):
                raise OSError("Incomplete write")
        except OSError:
            self.close("error")
            self.error = "Recording stopped because the log could not be written. Check the drive and start a new session."
            raise LogError(self.error) from None

    def close(self, status):
        self.handle.close()
        self.handle = None
        self.status = status
        self.revision = uuid4().hex

    async def start(self, location, revision):
        async with self.lock:
            if revision != self.revision or self.status == "active":
                raise RuntimeError("Session changed. Refresh the dashboard.")
            self.handle = await asyncio.to_thread(open_history, location)
            self.status, self.error, self.revision = "active", None, uuid4().hex
            self.stats = RideStats(monotonic())
            await self.write("start")
            self.worker = asyncio.create_task(self.run())
            return self.snapshot()

    async def run(self):
        try:
            while True:
                await asyncio.sleep(1)
                async with self.lock:
                    await self.write("sample")
        except LogError:
            return

    async def finish(self, revision=None):
        async with self.lock:
            if revision is not None and (revision != self.revision or self.status != "active"):
                raise RuntimeError("Session changed. Refresh the dashboard.")
            if self.status == "active":
                self.worker.cancel()
                await asyncio.gather(self.worker, return_exceptions=True)
                await self.write("finish")
                self.close("finished")
            return self.snapshot()
