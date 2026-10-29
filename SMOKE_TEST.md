# Physical smoke test

Complete the README's one-time bike selection first: scan with `uv run echelon-bridge --scan` and save your own bike's address in your private `.env`. The reader requires a selected address and never connects by advertised name alone.

Keep the Linux bridge computer near the powered bike and the Zwift device. Close the Echelon app/QZ so the bike is available. Software tests do not replace these observations.

## 1. Bike to local metrics

For the first isolated check, stop the full background bridge and start the reader only:

```bash
./bridge stop
./bridge run --read-only
```

In another terminal:

```bash
watch -n 1 'curl -s http://127.0.0.1:8000/metrics | python -m json.tool'
```

Pedal, stop, and change resistance. Expect `connected: true`, `initialized: true`, increasing packet count, changing cadence, resistance 1–32, and corresponding estimated watts. Turn the knob once if resistance is unknown. Stop pedaling: watts should go to zero after the bike sends zero cadence or after the five-second freshness timeout plus at most one notification interval. Disconnect/unpower the bike: power goes to zero; reconnect should eventually recover without restarting the service. Fresh cadence alone must not restore watts until resistance is received again.

If `auth_required` becomes true, record the status (not challenge bytes) and consult the README firmware limitation. This bridge cannot currently unlock that firmware.

## 2. Linux to an independent BLE client

Stop the foreground reader with Ctrl+C, then:

```bash
./bridge start
```

In Android nRF Connect, scan for **EchelonPython**, connect, and inspect:

- Cycling Power Service `1818`.
- Cycling Power Measurement `2A63`: read/notify, with a client configuration descriptor `2902` supplied by BlueZ. Enable notifications.
- Cycling Power Feature `2A65`: readable, little-endian `08 00 00 00` (crank data).
- Measurement notifications every second, eight bytes. Initial zeros are `20 00 00 00 00 00 00 00`; pedaling changes signed watts at bytes 2–3 and crank count/time at bytes 4–7.
- `/health` → `peripheral.client_subscribed: true`. Disconnect nRF Connect and verify it returns to false; disconnect before opening Zwift.

Registration, adapter activity, and updates can be checked locally, but only the independent scan establishes over-the-air discovery. Subscription means a BLE client subscribed; it does not identify its app.

For a no-bike radio check, stop the background bridge and use `./bridge run --simulate`. Scan for **EchelonSIM-TEST** and verify notifications. End simulation and restart the live service before riding. Do not mistake simulated readings for bike compatibility.

## 3. Zwift

Open Paired Devices in Zwift on the other device, select Power Source, and choose **EchelonPython**. Optionally select it for Cadence if Zwift offers that. Do not select it as a controllable trainer. Pedal and turn the manual resistance knob; compare Zwift's power to `/metrics`. Both use estimated power.

Keep riding for a few minutes, then stop the bridge with `./bridge stop`; Zwift should lose the sensor and its power should fall. Start again, reconnect Zwift if necessary, and confirm recovery. A physical firmware/connection/notification test is complete only after these observations.

## Recovery

- **No bike:** power/wake it, close competing apps, move closer, wait up to an eight-second scan plus a 30-second retry. Check `./bridge logs`. Use `/scan?identifiers=true` locally and `--address` if more than one bike exists.
- **Permission denied / no adapter:** check `systemctl status bluetooth`, `bluetoothctl list`, `bluetoothctl show`, and `rfkill list bluetooth`. The bridge runs as your user; do not run the whole application as root. Distribution-specific BlueZ/polkit/D-Bus policy may need attention. This installation needed no permission or daemon configuration changes.
- **Not visible in Zwift:** disconnect nRF Connect/other clients, verify Bluetooth is enabled on the Zwift device, re-open the pairing screen, scan independently, and inspect `/health`. `gatt_started`, `advertisement_registered`, and `adapter_advertising_active` should be true while waiting for a client. Advertising activity may change while a client is connected. No public HTTP port is needed.
- **Adapter conflicts / drops when subscribing:** use two adapters with `./bridge start --adapter hci1 --power-adapter hci0`. If the hardware cannot host the CPS peripheral reliably even with a separate adapter, an ESP32 peripheral is an alternative requiring separate firmware/transport work, not an implemented fallback.
- **Restart:** `./bridge stop`, then `./bridge start`. The bridge unregisters GATT/advertising and closes its D-Bus connection. If BlueZ itself is stuck, inspect other Bluetooth users before manually restarting the system daemon; that disconnects other Bluetooth devices.
- **Port in use:** stop another bridge instance or use `./bridge start --port 8001` and visit that port. Run a single worker.
