"""FastAPI serves the built Vue admin and a read-only, same-origin API."""
import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .diagnostics import PacketCapture, RecentEvents, safe_error
from .state import BikeState, PeripheralState
from .power import estimated_watts
from .bike_ble import read_forever, BikeDiscovery, simulate_forever
from .cycling_power import advertise_power_forever
from .mirror import Mirror, loopback_authority

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend_dist"
# Wheels carry the same build inside the installed package.
if (Path(__file__).parent / "frontend_dist").is_dir():
    FRONTEND_DIST = Path(__file__).parent / "frontend_dist"


def create_app(settings=None, *, discovery=None, reader=read_forever,
               advertiser=advertise_power_forever, frontend_dist=FRONTEND_DIST, mirror=None):
    settings = settings or Settings.from_env()
    state = BikeState(simulated=settings.simulate)
    peripheral = PeripheralState(name=settings.name)
    discovery = discovery or BikeDiscovery(settings)
    events = RecentEvents()
    tasks = {}
    mirror = mirror or Mirror()

    @asynccontextmanager
    async def lifespan(app):
        capture = PacketCapture(settings.trace) if settings.trace else None
        logger = logging.getLogger("echelon_bridge")
        old_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(events)
        try:
            if settings.reader:
                tasks["reader"] = asyncio.create_task(reader(state, settings, discovery, capture=capture), name="bike-reader")
            if settings.simulate:
                tasks["simulator"] = asyncio.create_task(simulate_forever(state), name="simulator")
            if settings.advertise:
                tasks["advertiser"] = asyncio.create_task(advertiser(state, peripheral, settings), name="zwift-advertiser")
            yield
        finally:
            await mirror.shutdown()
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            logger.removeHandler(events)
            logger.setLevel(old_level)
            if capture:
                capture.close()

    app = FastAPI(title="Echelon Bridge", version="0.3.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    api = FastAPI(title="Echelon Bridge API", version="0.3.0", redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.state.bike = state
    app.state.peripheral = peripheral
    app.state.tasks = tasks
    app.state.events = events
    app.state.mirror = mirror

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api") or request.url.path in {"/health", "/metrics", "/scan", "/estimate", "/events"}:
            response.headers["Cache-Control"] = "no-store"
        # Swagger's optional /api/docs uses its standard CDN assets. The admin
        # itself is fully bundled and never loads resources from third parties.
        if request.url.path != "/api/docs":
            authority = request.headers.get("host", "")
            socket_source = (("wss" if request.url.scheme == "https" else "ws") + "://" + authority
                             if loopback_authority(authority) else "")
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                f"connect-src 'self' {socket_source}; img-src 'self' data:; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'none'"
            )
        return response

    @api.get("/")
    async def info():
        return {"app": "Echelon → Zwift", "version": "0.3.0",
                "mode": "SIMULATION — BLE SMOKE TEST ONLY" if settings.simulate else "live",
                "health": "/api/health", "metrics": "/api/metrics", "docs": "/api/docs"}

    @api.get("/metrics")
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return {**state.snapshot(), "peripheral": peripheral.snapshot()}

    @api.get("/health")
    @app.get("/health", include_in_schema=False)
    async def health():
        failed = {name: safe_error(task.exception()) if not task.cancelled() and task.exception() else "Task stopped"
                  for name, task in tasks.items() if task.done()}
        ready = peripheral.gatt_started and peripheral.advertisement_registered if settings.advertise else True
        live = state.snapshot()
        return {"status": "error" if failed else ("ready" if ready and live["power_available"] else "waiting"),
                "reader_enabled": settings.reader, "simulated": settings.simulate,
                "ble_power_advertising_enabled": settings.advertise,
                "bike_connected": state.connected, "reader_status": state.reader_status,
                "power_available": live["power_available"], "power_type": "estimated, not calibrated",
                "adapter": settings.adapter or "default", "power_adapter": settings.power_adapter or "hci0",
                "bike_selection": "pinned_address" if settings.address else "unconfigured",
                "peripheral": peripheral.snapshot(), "error": state.last_error, "failed_tasks": failed}

    @api.get("/estimate")
    @app.get("/estimate", include_in_schema=False)
    async def estimate(cadence: int = Query(90, ge=0, le=255), resistance: int = Query(20, ge=1, le=32)):
        return {"cadence": cadence, "resistance": resistance, "estimated_watts": estimated_watts(cadence, resistance)}

    @api.get("/scan")
    @app.get("/scan", include_in_schema=False)
    async def scan(identifiers: bool = False):
        if (not settings.reader or not settings.address) and not discovery.lock.locked():
            try:
                await discovery.scan()
            except Exception as exc:
                raise HTTPException(503, safe_error(exc)) from None
        return discovery.snapshot(identifiers)

    @api.get("/events")
    @app.get("/events", include_in_schema=False)
    async def recent_events():
        return {"events": list(events.events)}

    @api.get("/mirror/status")
    async def mirror_status():
        return mirror.status()

    api.add_api_websocket_route("/mirror/stream", mirror.stream)

    @app.get("/docs", include_in_schema=False)
    async def docs_redirect():
        return RedirectResponse("/api/docs")

    # The mounted API owns its 404/405 responses; never return the SPA for API
    # errors. Legacy diagnostic URLs above remain compatible with curl/scripts.
    app.mount("/api", api)
    frontend_dist = Path(frontend_dist)
    files = StaticFiles(directory=frontend_dist, html=True, check_dir=False)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend(path: str, request: Request):
        if any(part.startswith(".") for part in Path(path).parts):
            raise HTTPException(404, "Not found")
        if not (frontend_dist / "index.html").is_file():
            return JSONResponse({"detail": "Admin UI has not been built. Run ./bridge build.",
                                 "metrics": "/api/metrics"}, status_code=503)
        serves_index = path in {"", "index.html"}
        try:
            response = await files.get_response(path, request.scope)
        except StarletteHTTPException as exc:
            if (exc.status_code != 404 or path == "assets" or path.startswith("assets/")
                    or Path(path).suffix or path.split("/")[0] in {"health", "metrics", "scan", "estimate", "events", "api"}
                    or "text/html" not in request.headers.get("accept", "")):
                raise
            response = await files.get_response("index.html", request.scope)
            serves_index = True
        if serves_index or response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith("assets/") and re.search(r"-[A-Za-z0-9_-]{8,}\.[^/]+$", path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    return app


app = create_app()
