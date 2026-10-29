# Validation

The automated suite uses mock BLE clients/servers; it does not connect to nearby devices.

```bash
uv sync --frozen --extra dev
uv run --extra dev pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Checks cover Echelon decoding, initialization/poll commands and checksums, the original QZ table/interpolation, stale/disconnected zeroing, explicit bike selection, refusal to connect to a different address, environment precedence, crank payloads, reconnect/cancellation, GATT cleanup, HTTP boundaries, static/API routing, redacted events, and desktop-control lifecycle behavior. Frontend checks cover real/absent/stale/offline states, simulation labels, graph gaps, subscription distinctions, and license access.

Production browser smoke testing uses a temporary HTTP-only server:

```bash
./bridge run --http-only --port 8001
# In another terminal:
cd frontend
node tests/browser-smoke.mjs
```

The browser script expects Chromium at `/usr/bin/chromium`; adjust that path for the test environment if necessary. It checks desktop/mobile layouts, production assets, diagnostics, downloads, offline recovery, and JavaScript errors. Stop the temporary server after testing.

For a running live bridge:

```bash
uv run python scripts/smoke_check.py --require-advertising
# Add --require-bike for fresh real-bike data;
# add --require-subscriber for an active BLE notification subscription.
```

Real-bike discovery, initialization, cadence/resistance notifications, estimated-power updates, and simultaneous peripheral advertisement/subscription have been observed during development. This does not validate every bike, firmware, or adapter, identify a subscribing app, or establish watt accuracy. A user must verify changing watts/cadence in Zwift while pedaling. Follow [SMOKE_TEST.md](SMOKE_TEST.md) for the physical checklist.

Personal ride observations, host identifiers, and development-session details are excluded from public source and release artifacts. Generic dependency versions, synthetic test fixtures, and localhost endpoints are retained for reproducibility.
