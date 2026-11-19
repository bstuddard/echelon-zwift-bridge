# Echelon Bridge

Read an **Echelon Connect Sport / EX-15** over Bluetooth on Windows or Linux. The local dashboard shows cadence, resistance, estimated watts, and a live power graph. On Linux the bridge also advertises **EchelonPython**, a power sensor that Zwift can pair with.

Power is **estimated from QZ's original wattage table**, not measured by a calibrated power meter. Turn the bike's resistance knob yourself.

## Record a session on Windows or Linux

Open the [ride monitor](http://127.0.0.1:8000) on the bridge computer. Click **Start session**, browse for a `.psv` history file or type its full path, then click **Start recording**. Use **Finish session** for the final summary. You can use the same file for multiple rides. Recording continues while the backend runs, even with the browser closed.

The dashboard shows live watts, cadence, resistance, elapsed time, average watts, and estimated indoor distance in miles and kilometres. Distance uses the [QZ cadence-to-speed estimate](https://github.com/cagnulein/qdomyos-zwift/blob/master/src/devices/echelonconnectsport/echelonconnectsport.cpp). Average watts includes fresh zero-power readings and excludes gaps. Estimated FTP appears after 20 continuous minutes of valid power and uses 95% of the best such average. A sustained maximal effort gives this estimate its intended training meaning. [20-minute FTP test](https://www.zwift.com/uk/news/33613-best-zwift-workouts-to-improve-your-ftp-functional-threshold-power)

The pipe-delimited log includes UTC timestamps, a session ID, start/sample/finish rows, and the session metrics. Missing readings produce empty fields. A normal backend shutdown finishes the active session. In a spreadsheet, select `|` as the delimiter when opening the file.

### Pedal reminder and focus mode

In **Ride monitor**, switch **Pedal reminder** on and set **Target power** (45 W initially). When the last five seconds of estimated power average below your target, a large **PEDAL HARDER** message, power gauge, and amber page border pulse slowly, with a short beep every 1.5 seconds. The next live reading at or above the target clears the alert and sound immediately, even while the average is lower. A new dip can alert again if the five-second average is still below target. Uncheck **Beep** for a silent reminder; sound uses your browser and system volume.

The reminder waits for a full five seconds of fresh readings and pauses when readings are missing, stale, or simulated. It runs only in this dashboard, so keep the ride page visible. Reduced-motion settings use a steady highlight. It starts off after a page reload; you can change the watt target or switch it off at any time. If your browser blocks sound, allow audio for the local dashboard and toggle **Beep** off and on.

Set the reminder and target first, then click **Focus mode** for a black screen with small white five-second average watts in the center. A reminder turns the whole view solid red with white **PEDAL HARDER** text and the same optional beep. It returns to black immediately when live power reaches the target. Focus mode also works with the reminder off. Move the mouse to reveal **Exit focus**, or press **Esc**. It requests browser fullscreen; if that is unavailable, it fills the dashboard window instead. Focus mode changes presentation only: bike readings, recording, ride averages, distance, and all other statistics continue unchanged behind it.

### Remember your ride history file

Set `ECHELON_LOG_PATH` in your private `.env` to an absolute local `.psv` path. For example, replace this placeholder with your own Windows path:

```dotenv
ECHELON_LOG_PATH='C:/Users/YourName/Documents/Echelon Bridge/rides.psv'
```

Create the containing folder first, then restart the server after changing `.env`. **Start session** prefills this path; you can edit it or browse for another file. **Start recording** still starts each ride explicitly. Startup and opening the form never create or modify the history file. Leave the setting blank to choose a path each time. Linux accepts an absolute local path too.

`.env` and `.psv` files are ignored by Git and excluded from release source archives. The shared `.env.example` contains only an empty setting. The personal path is omitted from telemetry and downloaded diagnostics, and the publication checker detects it if copied into a source file.

## What you need

- For Windows ride metrics, a Windows 10 or 11 PC with Bluetooth LE enabled. The reader uses Bleak's native WinRT backend and the system Bluetooth adapter.
- For the Linux Zwift bridge, a Linux computer with BlueZ, systemd user services, and Bluetooth LE central + peripheral support.
- Python **3.11–3.14**, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Node.js **22.12+** with npm.
- Your powered Echelon bike nearby, with other bike apps disconnected.
- For Zwift rides, the **Zwift game app** on a device near the Linux bridge. [Get Zwift](https://www.zwift.com/download).

## Windows ride monitor

Open PowerShell in the project folder. Run these commands once to install the reader and build the dashboard:

```powershell
uv sync --frozen
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
```

Turn on Bluetooth, pedal to wake the bike, and disconnect any other app or Linux bridge using it. Find the bike's address:

```powershell
uv run echelon-bridge --scan
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Save the address from the scan as `ECHELON_ADDRESS` in that file. For each ride, start the server and open its dashboard with:

```powershell
uv run echelon-bridge --open
```

The [ride monitor](http://127.0.0.1:8000) opens on that PC. Pedal and turn the resistance knob once to see cadence, resistance, and estimated watts. Keep PowerShell open during the ride and press **Ctrl+C** to disconnect. Windows runs in reader-only mode by default. Zwift broadcasting, the Omarchy icon, private packet traces, and Android phone mirroring are Linux features.

### Windows batch launcher and desktop shortcut

After installing the dependencies and building the dashboard, double-click **Start Echelon Bridge.bat** in the project folder. It selects the correct working folder, uses the installed `.venv`, and reads your private `.env`. If setup is incomplete, it displays the commands you need. It does not install packages on each launch.

Double-click **Stop Echelon Bridge.bat** to finish any active recording, disconnect Bluetooth, and shut down the server. It also works for a server running in the background, and is safe to click again when the server is stopped. Both batch files use the folder they are stored in. Stop controls this checkout's server on the default port 8000 in the current Windows session.

For matching **Start Echelon Bridge** and **Stop Echelon Bridge** desktop shortcuts, run this from PowerShell in the project folder:

```powershell
uv run --frozen python scripts/install_windows_shortcut.py
```

**Start** opens the existing dashboard if the bridge is already running; otherwise it starts the server and opens the browser. Keep the server console open during your ride; use **Stop** or press **Ctrl+C** there when finished. Keep both batch files in the project folder; use shortcuts to launch them from elsewhere. The installer creates or updates this checkout's shortcuts without administrator rights or changes to PowerShell execution policy, and renames its older **Echelon Bridge** shortcut to **Start Echelon Bridge**. If you move the checkout, remove the old shortcuts and run the installer again. Use `--destination` to choose another existing folder. A server launched before the stop control was installed needs one restart before **Stop** can control it.

## Linux setup

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

## Everyday use on Linux

From the project folder:

```bash
./bridge start    # start in the background; safe to repeat
./bridge stop     # disconnect the bike and remove the power advertisement
./bridge status   # check the service
./bridge logs     # follow logs; Ctrl+C closes the log view
```

The dashboard includes live values, a power graph, Bluetooth registration/subscription status, redacted events, JSON diagnostics, a setup guide, and license notices. Current values clear if the server becomes unreachable.

### Optional: watch your Android phone in the dashboard

The **Phone mirror** page at [http://127.0.0.1:8000/mirror](http://127.0.0.1:8000/mirror) can show Zwift running on your selected phone, with bike readings underneath. This needs a recent desktop Chrome/Chromium browser and an external **scrcpy 4.x or 5.x** installation with its matching `scrcpy-server` and Android `adb` tools. [Official scrcpy installation](https://github.com/Genymobile/scrcpy/blob/master/doc/linux.md).

1. Authorize your Android phone using USB debugging or Android 11+ **Wireless debugging** with QR/code pairing. For wireless use, keep the phone and PC on the same trusted home network. The encrypted pairing method works without a USB cable. [Android pairing instructions](https://developer.android.com/tools/adb#wireless-android11-command-line).
2. With exactly one authorized phone connected, select it once:

   ```bash
   uv run echelon-mirror-setup
   ```

3. Open **Phone mirror**, unlock the phone, open Zwift, and choose **Start mirroring**. Use the phone to control the game. **Stop**, leaving the page, hiding the browser tab, or disconnecting the phone ends capture and clears the picture. Full screen is available while streaming.

Selection is stored privately under `$XDG_STATE_HOME/echelon-bridge/phone.json` (normally `~/.local/state/echelon-bridge/phone.json`), mode `0600`. Your bike's `.env` still needs only its original entry. The bridge verifies the selected phone's identity and uses only its USB connection or already-paired native ADB TLS transport. It never chooses another phone or falls back to a raw network address. If wireless viewing cannot find the transport, check that a recent ADB installation can automatically discover your paired phone.

For a portable scrcpy installation, `uv run echelon-mirror-setup --help` offers explicit client, server, and ADB paths. If you already have a private selection from the desktop mirroring helper, import it with `uv run echelon-mirror-setup --import-selection /path/to/private-selection.json`; the phone can be offline during import. Run setup again after replacing/upgrading the scrcpy installation or changing the phone's discovery identity.

Mirroring is **view-only**: no audio, microphone, phone controls, clipboard sharing, or recording. Phone identifiers, pairing credentials, and video are excluded from diagnostics. The viewer stays on loopback and requires a same-origin browser session; no extra LAN-facing web service is installed. Android debugging itself grants this computer broader access than the viewer uses, so turn debugging off when finished. Keep phone configuration and ADB keys private. See [SECURITY.md](SECURITY.md).

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
| `/api/metrics` | Current cadence, resistance, estimated watts, freshness, and session summary |
| `/api/events` | Last 100 redacted application events in memory |
| `/api/mirror/status` | Mirror availability and a browser session ticket; no phone identifiers |
| `/api/scan` | Candidates; identifiers require an explicit `?identifiers=true` query |
| `/api/estimate?cadence=90&resistance=20` | Bounded lookup; does not change the sensor output |
| `/api/docs` | Optional API docs; its Swagger assets use a CDN |

The earlier `/health`, `/metrics`, `/scan`, `/estimate`, and `/events` URLs remain aliases. Use one process/worker; Bluetooth ownership is not compatible with multiple Uvicorn workers or reload mode.

The local dashboard uses `POST /api/session/pick-log`, `/api/session/start`, and `/api/session/finish` for recording. The current session revision prevents a stale browser tab from finishing a newer ride.

The optional `/api/mirror/stream` WebSocket accepts one same-origin, ticket-authenticated viewer at a time. It receives only video from the pinned phone and accepts a fixed heartbeat; it exposes no phone-control commands. Merely opening the dashboard or checking status never starts phone capture.

</details>

## Power accuracy and compatibility

The bridge uses QZ's default **33 × 11 cadence/resistance table**, including its scaling above 100 RPM. **No watt gain or 0.8 multiplier is applied.** Echelon calibration varies; a universal multiplier cannot establish accuracy for an individual bike. Compare against a measured power source if accuracy is important. Event organizers determine hardware eligibility.

Disconnected bikes, authentication challenges, or cadence older than five seconds produce zero watts on the next one-second update. Unknown resistance produces zero watts. A known resistance setting lasts for the current connection and is cleared on reconnect.

The legacy Echelon protocol is implemented. Other Echelon models/firmware and adapter combinations need their own physical checks. See [VALIDATION.md](VALIDATION.md) for verification scope.

## Privacy and publishing

HTTP binds only to **127.0.0.1**. Keep it local; do not expose it to the LAN or Internet. The desktop buttons use a systemd **user** service, and the bike telemetry API remains read-only. BLE sensor telemetry is unencrypted, and address selection is not cryptographic authentication. See [SECURITY.md](SECURITY.md).

Personal `.env` files, logs, packet captures, private notes, credential folders, and generated dependencies/builds are excluded from Git. Loopback addresses and clearly synthetic examples in this repo are generic defaults, not a user's network configuration.

Before publishing source or release artifacts:

```bash
uv run python scripts/check_publication.py
./bridge build
uv build --sdist
uv build --wheel
uv run python scripts/check_publication.py --archive dist/*.tar.gz
uv run python scripts/check_publication.py --archive dist/*.whl
```

The checker reports finding types and filenames without echoing private values. It checks current Git candidates (including already-tracked files) and archive contents; it does not certify old Git history. A matching source archive should accompany a binary release.

Building the frontend first and the wheel directly from this checkout includes the current dashboard in the wheel. Check each archive separately.

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
