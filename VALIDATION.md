# Validation

The automated suite uses mock BLE clients/servers; it does not connect to nearby devices.

```bash
uv sync --frozen --extra dev
uv run --extra dev pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

Checks cover Echelon decoding, initialization/poll commands and checksums, the original QZ table/interpolation, stale/disconnected zeroing, explicit bike selection, refusal to connect to a different address, environment precedence, crank payloads, reconnect/cancellation, GATT cleanup, HTTP boundaries, static/API routing, redacted events, and desktop-control lifecycle behavior. Frontend checks cover real/absent/stale/offline states, simulation labels, graph gaps, subscription distinctions, and license access.

Optional phone tests cover same-origin/ticket checks, rejection before capture, one-viewer ownership, phone identity pinning, private configuration/server integrity, bounded packets, orientation metadata, no phone-control channel, and capture cleanup. Frontend tests check opt-in capture, codec/key-frame handling, stop/unmount/hidden-tab cleanup, unsupported browsers, and phone-offline messages. No real phone is contacted by these automated tests.

Production browser smoke testing uses a temporary HTTP-only server:

```bash
./bridge run --http-only --port 8001
# In another terminal:
cd frontend
node tests/browser-smoke.mjs
node tests/mirror-browser-smoke.mjs
```

The browser scripts expect Chromium at `/usr/bin/chromium`; adjust that path for the test environment if necessary. They check desktop/mobile layouts, production assets, diagnostics, downloads, offline recovery, and JavaScript errors. The mirror browser test uses tiny original solid-color H.264 fixtures to exercise the actual browser decoder, direct `/mirror` navigation, Start/Stop, clearing the picture, and leaving the page. It does not record or display a real phone. Stop the temporary server after testing.

For the complete production stream pipeline without a phone:

```bash
uv run --extra dev python scripts/test_mirror_e2e.py
```

This starts an isolated HTTP-only server with temporary private configuration and a fake ADB executable. Every actual socket is loopback; no installed ADB, phone key, Bluetooth adapter, or LAN device is used. Chromium decodes generated video through the real Uvicorn/WebSocket/phone-stream code. Scenarios include malformed handshakes, cross-origin browser attempts with a valid ticket, one-viewer ownership, rapid stop/cancellation, portrait rotation, changed identity/server hashes, legacy discovery, corrupt/truncated/oversized packets, transport message limits, browser close, and process/file/tunnel cleanup. The runner rejects unexpected server tracebacks and removes its temporary environment.

To verify real mirroring, select an authorized phone with `uv run echelon-mirror-setup`, open `/mirror`, and choose Start. Check both portrait/landscape if relevant, then Stop and confirm capture ends. Turn phone debugging off after the test. Scrcpy 4.x/5.x protocol handling is covered by fixtures; each installed scrcpy/Android version still needs a physical check.

For a running live bridge:

```bash
uv run python scripts/smoke_check.py --require-advertising
# Add --require-bike for fresh real-bike data;
# add --require-subscriber for an active BLE notification subscription.
```

Real-bike discovery, initialization, cadence/resistance notifications, estimated-power updates, and simultaneous peripheral advertisement/subscription have been observed during development. This does not validate every bike, firmware, or adapter, identify a subscribing app, or establish watt accuracy. A user must verify changing watts/cadence in Zwift while pedaling. Follow [SMOKE_TEST.md](SMOKE_TEST.md) for the physical checklist.

Personal ride observations, host identifiers, and development-session details are excluded from public source and release artifacts. Generic dependency versions, synthetic test fixtures, and localhost endpoints are retained for reproducibility.

## Mirror software review — 2026-10-29

- 95 backend tests and 18 frontend tests passed.
- 38 scenarios passed through the actual production launcher, Uvicorn, WebSocket, stream parser, and Chromium decoder using only fake ADB and generated video. No actual phone, ADB key, Bluetooth adapter, or LAN device was used.
- Cross-origin browser reads/streams, malformed or missing/stale tickets, malformed handshake encodings, non-loopback peers/listeners, legacy discovery, wrong device identity, changed server content, corrupt/truncated/oversized video, viewer control attempts, rapid Start/Stop, navigation/browser close, slow startup, and cleanup were checked.
- Review fixes include strict handshake/peer parsing, clean rejection of invalid header encodings, private bounded/atomic configuration I/O, bounded/reaped subprocesses, named paired TLS transport without raw-IP fallback, 1 KiB viewer messages without compression, and stopping capture when the browser cannot display video.
- Production frontend dependency audit and the Python dependency audit reported no known vulnerabilities. The local application itself is reviewed/tested here; it has no PyPI advisory entry.

These checks validate the software paths under the documented trusted-local-computer model. They do not certify Android/browser/OS security or live compatibility with every phone and scrcpy version. Physical phone playback remains a separate opt-in test; no personal screen captures belong in published validation artifacts.
