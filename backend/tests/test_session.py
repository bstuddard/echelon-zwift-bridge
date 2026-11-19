import asyncio
from httpx import ASGITransport, AsyncClient
import pytest

from echelon_bridge.app import create_app
from echelon_bridge.config import Settings
from echelon_bridge.session import KPH_PER_RPM, RideStats
from echelon_bridge.session_log import HEADER, LogError, open_history


def test_time_weighted_power_distance_and_rolling_ftp_exclude_gaps():
    stats = RideStats(0)
    for t in range(1200):
        stats.sample(t, 80, 100, 0)
    assert stats.snapshot()["ftp_watts"] is None
    stats.sample(1200, 90, 200, 0)
    assert stats.snapshot()["ftp_watts"] == 95
    for t in range(1201, 2401):
        stats.sample(t, 90, 200, 0)
    assert stats.snapshot()["ftp_watts"] == 190
    assert stats.snapshot()["avg_watts"] == 150
    assert stats.distance_km == pytest.approx(KPH_PER_RPM * (80 + 90) / 3)
    distance = stats.distance_km
    stats.sample(2410, None, None, 0)
    stats.sample(2411, 0, 0, 1)
    stats.sample(2412, 0, 0, 1)
    assert stats.distance_km == distance
    assert stats.joules == 360000 and stats.power_seconds == 2401
    assert stats.snapshot()["continuous_power_s"] == 1
    assert stats.snapshot()["ftp_watts"] == 190


def test_missing_watts_only_count_distance_and_gap_breaks_ftp():
    stats = RideStats(0)
    for t in range(1250):
        stats.sample(t, 80, None if t == 600 else 200, 0)
    assert stats.distance_km == pytest.approx(KPH_PER_RPM * 80 * 1249 / 3600)
    assert stats.snapshot()["ftp_watts"] is None
    assert stats.snapshot()["avg_watts"] == 200


def test_history_file_rejects_unrelated_content_and_concurrent_writers(tmp_path):
    path = tmp_path / "rides.psv"
    path.write_bytes(b"existing user data\n")
    with pytest.raises(LogError):
        open_history(str(path))
    assert path.read_bytes() == b"existing user data\n"
    fresh = tmp_path / "new.psv"
    with open_history(str(fresh)):
        with pytest.raises(OSError):
            open_history(str(fresh))
    with open_history(str(fresh)) as handle:
        handle.write(b"partial")
    with pytest.raises(LogError, match="partial"):
        open_history(str(fresh))
    assert fresh.read_bytes() == HEADER + b"partial"
    for invalid in ["relative.psv", str(tmp_path / ".env"), str(tmp_path)]:
        with pytest.raises(LogError):
            open_history(invalid)


def test_session_api_records_multiple_rides_and_preserves_prior_history(tmp_path):
    async def run():
        async def fake_bike(bike, *args, **kwargs):
            bike.connected = bike.initialized = True
            bike.ingest(bytes.fromhex("f0 d2 01 14 d7"))
            bike.ingest(bytes.fromhex("f0 d1 00 00 00 00 00 00 00 00 5a 00 00"))
            await asyncio.Event().wait()

        app = create_app(Settings(reader=True), reader=fake_bike)
        path = tmp_path / "my history.psv"
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url="http://localhost") as client:
            def headers(revision):
                return {"Origin": "http://localhost", "X-Session-Revision": revision, "Content-Type": "text/plain"}
            idle = (await client.get("/api/metrics")).json()["session"]
            first = await client.post("/api/session/start", content=str(path))
            assert first.status_code == 403 and not path.exists()
            for i in range(2):
                response = await client.post("/api/session/start", headers=headers(idle["revision"]), content=str(path))
                assert response.status_code == 200
                active = response.json()
                assert active["status"] == "active" and str(path) not in response.text
                stale = await client.post("/api/session/finish", headers=headers(idle["revision"]))
                assert stale.status_code == 409
                if i == 0:
                    await asyncio.sleep(1.1)
                    sample = (await client.get("/api/metrics")).json()["session"]
                    assert sample["avg_watts"] == 165 and sample["distance_km"] > 0
                    idle = (await client.post("/api/session/finish", headers=headers(active["revision"]))).json()
                    assert idle["status"] == "finished"
            # A normal backend shutdown also finalizes an active session.
        rows = path.read_bytes().splitlines()
        assert rows[0] == HEADER.rstrip() and rows.count(rows[0]) == 1
        fields = [row.decode().split("|") for row in rows[1:]]
        assert [v[2] for v in fields].count("finish") == 2
        assert len({v[1] for v in fields}) == 2
        assert all(len(v) == 10 for v in fields)
    asyncio.run(run())
