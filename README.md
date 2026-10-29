# Echelon Bridge

Use an **Echelon Connect Sport / EX-15 with Zwift**. This small Linux server reads your bike over Bluetooth and advertises **EchelonPython**, a power sensor that Zwift can pair with. A Vue + Tailwind dashboard shows live readings and connection diagnostics.

Power is **estimated from QZ's original wattage table**, not measured by a calibrated power meter. Turn the bike's resistance knob yourself.

## What you need

- A Linux computer with BlueZ, systemd user services, and Bluetooth LE central + peripheral support.
- Python **3.11–3.14**, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Node.js **22.12+** with npm.
- Your powered Echelon bike nearby, with other bike apps disconnected.
- The **Zwift game app** on a nearby phone, tablet, Windows PC, or Mac. The bridge runs on Linux; Zwift has no official native Linux game download. [Get Zwift](https://www.zwift.com/download).

## First setup

Download or clone this repository, then open a terminal in its folder.

### 1. Install and build

```bash
uv sync --frozen
./bridge build
```

This installs the Python dependencies and builds the Vue admin. Node is needed for the build; the running server uses Python.

### 2. Select your bike once

Power the bike, pedal to wake it, and close Echelon/QZ or other connected bike apps. Then run:

```bash
uv run echelon-bridge --scan
```

The scan lists nearby bike candidates and their Bluetooth addresses. **It does not connect.** Keep the scan output private.

Create your local configuration if it does not already exist:

```bash
test -f .env || cp .env.example .env
chmod 600 .env
```

Open `.env` in your editor. It needs just **one entry**:

```dotenv
ECHELON_ADDRESS=AA:BB:CC:DD:EE:FF
```

Replace that example address with **your own bike's address from the scan**. Save the file. The reader refuses to connect until an address is selected and never falls back to another bike. Your `.env` stays private and is ignored by Git.

### 3. Start the bridge

```bash
./bridge start
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** on the Linux computer. Pedal and look for live cadence, resistance, and estimated watts. If resistance is unknown, turn the knob once.

The server runs in the background after the terminal closes. It keeps running until stopped, the user session ends, or the computer reboots. It does not install a boot service.

### 4. Pair in Zwift

On the device running the Zwift game:

1. Enable Bluetooth and allow requested Bluetooth / Nearby devices permissions.
2. Sign in and open the pairing screen.
3. Select **Power Source → EchelonPython**. Optionally select it for Cadence too.
4. Continue into a ride and pedal. Watts should change and your avatar should move.

Keep the Linux computer within Bluetooth range of both the bike and the Zwift device. Zwift receives Bluetooth notifications; the dashboard address is for local administration. With the native Android/iOS Zwift game, a Companion phone relay is unnecessary.

## Everyday use

From the project folder:

```bash
./bridge start    # start in the background; safe to repeat
./bridge stop     # disconnect the bike and remove the power advertisement
./bridge status   # check the service
./bridge logs     # follow logs; Ctrl+C closes the log view
```

The dashboard includes live values, a power graph, Bluetooth registration/subscription status, redacted events, JSON diagnostics, a setup guide, and license notices. Current values clear if the server becomes unreachable.

### Optional: one-click controls on Omarchy

After the first setup above, run:

```bash
uv run python scripts/install_desktop.py
```

A bicycle icon appears beside Bluetooth in the top bar:

- **Left-click:** start the bridge and open its dashboard.
- **Right-click:** stop the bridge.
- **Hover:** see current status and click instructions.
- **Green:** bike connected. **Amber:** starting/waiting. **Dimmed:** stopped. **Red:** check Diagnostics.

The app launcher also gets **Echelon Bridge** and **Stop Echelon Bridge** entries. No terminal or repository navigation is needed afterward.

The installer runs as your user, backs up the bar configuration, and writes only user-local launchers, an icon, a helper, and `~/.config/omarchy/plugins/local.echelon-bridge/`. Run it without sudo. The widget loads at login; it starts the server only when clicked. After moving this repository, re-run the installer to update the launcher paths. Hide the widget with `omarchy plugin disable local.echelon-bridge`.

## If something is not connecting

- **No bike:** power/wake it, close competing bike apps, check the address in `.env`, and wait for a scan/retry (up to about 40 seconds). An absent selected bike never causes a connection to another device.
- **Unknown resistance:** turn the knob once; some firmware only reports resistance on changes.
- **Zwift cannot see the sensor:** open Diagnostics, verify the advertisement is registered, and disconnect nRF Connect or other sensor clients. A Bluetooth subscription does not identify the client app; confirm the connection in Zwift.
- **Drops with one adapter:** some adapters cannot connect to the bike and advertise reliably together. Use two adapters with `./bridge start --adapter hci1 --power-adapter hci0` after stopping the old instance.
- **Firmware authentication required:** the newer `f0 e0` challenge is detected, but its unlock flow is not implemented. Power stays at zero. See [SMOKE_TEST.md](SMOKE_TEST.md).

For a complete staged test with nRF Connect, recovery steps, and byte layout checks, use **[SMOKE_TEST.md](SMOKE_TEST.md)**.

<details>
<summary>Advanced options and API</summary>

Stop a background instance before starting a foreground mode:

```bash
./bridge run --read-only  # selected bike → metrics, no Zwift advertisement
./bridge run --http-only  # dashboard/API only, no Bluetooth
./bridge run --simulate   # fixed BLE smoke test, named EchelonSIM-TEST
```

Simulation is explicitly labeled and cannot run with the live reader. Use it for radio testing; end it before live riding. There are no HTTP controls for power injection or mode changes.

`uv run echelon-bridge --help` lists adapter, address, private trace, and port options. A trace uses mode `0600` and redacts unknown/authentication payloads. Explicit shell variables override `.env`; CLI options take priority. `.env` is parsed as data, without shell execution or variable expansion.

Read-only API routes:

| Route | Purpose |
| --- | --- |
| `/api/health` | Reader, selected-address mode, task failures, and peripheral status |
| `/api/metrics` | Current cadence, resistance, estimated watts, and freshness |
| `/api/events` | Last 100 redacted application events in memory |
| `/api/scan` | Candidates; identifiers require an explicit `?identifiers=true` query |
| `/api/estimate?cadence=90&resistance=20` | Bounded lookup; does not change the sensor output |
| `/api/docs` | Optional API docs; its Swagger assets use a CDN |

The earlier `/health`, `/metrics`, `/scan`, `/estimate`, and `/events` URLs remain aliases. Use one process/worker; Bluetooth ownership is not compatible with multiple Uvicorn workers or reload mode.

</details>

## Power accuracy and compatibility

The bridge uses QZ's default **33 × 11 cadence/resistance table**, including its scaling above 100 RPM. **No watt gain or 0.8 multiplier is applied.** Echelon calibration varies; a universal multiplier cannot establish accuracy for an individual bike. Compare against a measured power source if accuracy is important. Event organizers determine hardware eligibility.

Disconnected bikes, authentication challenges, or cadence older than five seconds produce zero watts on the next one-second update. Unknown resistance produces zero watts. A known resistance setting lasts for the current connection and is cleared on reconnect.

The legacy Echelon protocol is implemented. Other Echelon models/firmware and adapter combinations need their own physical checks. See [VALIDATION.md](VALIDATION.md) for verification scope.

## Privacy and publishing

HTTP binds only to **127.0.0.1**. Keep it local; do not expose it to the LAN or Internet. The desktop buttons use a systemd **user** service, and the HTTP API remains read-only. BLE sensor telemetry is unencrypted, and address selection is not cryptographic authentication. See [SECURITY.md](SECURITY.md).

Personal `.env` files, logs, packet captures, private notes, credential folders, and generated dependencies/builds are excluded from Git. Loopback addresses and clearly synthetic examples in this repo are generic defaults, not a user's network configuration.

Before publishing source or release artifacts:

```bash
uv run python scripts/check_publication.py
uv build --sdist --wheel
uv run python scripts/check_publication.py --archive dist/*.tar.gz --archive dist/*.whl
```

The checker reports finding types and filenames without echoing private values. It checks current Git candidates (including already-tracked files) and archive contents; it does not certify old Git history. A matching source archive should accompany a binary release.

## Development

```bash
uv sync --frozen --extra dev
uv run --extra dev pytest -q
npm --prefix frontend test
```

For Vue development, run `./bridge run --http-only` and `npm --prefix frontend run dev` in separate terminals. Vite binds localhost and proxies `/api` to FastAPI. `./bridge build` writes the production app into `backend/frontend_dist`; FastAPI serves it and `/api` from one process. Rebuild after frontend changes.

Python sources/tests are under `backend/`; Vue + Tailwind sources are under `frontend/`; Omarchy integration is under `desktop/`. Locks pin Python and frontend dependencies for repeatable installs.

## License and credits

**GPL-3.0-only**, including this repository's Omarchy widget. Echelon protocol knowledge and the default watt table are adapted from [QZ / qdomyos-zwift](https://github.com/cagnulein/qdomyos-zwift) by Roberto Viola and contributors. See [LICENSE](LICENSE), [NOTICE](NOTICE), and [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt). Builds retain the permissive notices for bundled/adapted components, and the admin's About page links to local copies.

Independent project; unaffiliated with Echelon, Zwift, QZ, or Omarchy. No proprietary Zwift/Echelon game, firmware, account credentials, or brand artwork is bundled.
