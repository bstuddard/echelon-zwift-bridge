# Security model

This is experimental, local desktop software for a user-controlled exercise bike.

- The supported launcher binds HTTP to loopback only. API routes are read-only, reject untrusted Host names, and do not accept injected watts or shell commands. Other local processes/users may access a loopback service; it is not an authentication boundary.
- The reader requires an explicitly selected bike address. A fresh checkout does not inherit anybody else's bike pin and does not connect based on a matching advertised name. MAC selection limits accidental connections; names, services, and addresses can be imitated.
- Standard BLE power notifications are not encrypted or authenticated by this application. Nearby clients may observe or subscribe. A subscriber is not proof that the client is Zwift.
- The Omarchy widget and installer execute trusted local code with the user's privileges. The installer writes user-local files, backs up bar configuration, and needs no root access. Install/review code you trust, and do not run it with sudo.
- Keep `.env` private (mode `0600`). Unknown/authentication packets and device identifiers are excluded from normal metrics and logs. Explicit scan output contains identifiers locally; redact it before sharing. Optional captures and downloaded diagnostics should also be reviewed before sharing.
- The application itself requires no Echelon or Zwift credentials and makes no cloud requests. Package installation, optional Swagger docs, and the separately installed Zwift game have their own network behavior.

## Optional phone mirroring

The Mirror page captures only after Start. It opens one view-only scrcpy video channel for the locally selected phone; audio, microphone, clipboard, input/control channels, and recording are disabled. Video is relayed in memory to the local browser. Leaving the page, hiding its browser tab, Stop, browser disconnect, or server shutdown closes capture, removes the temporary tunnel/server file, and clears the picture. Merely loading the dashboard or checking mirror status never contacts the phone.

The WebSocket checks an exact same-origin Origin header, a strictly parsed loopback Host, a loopback client address, and a random per-process session ticket obtained from the same-origin status endpoint. The ticket travels in WebSocket subprotocol headers, not URLs. Cross-origin pages and tokenless clients are rejected before capture. Invalid handshake encodings are closed cleanly before application execution. Only a fixed heartbeat is accepted from the viewer; incoming messages are limited to 1 KiB and compression is disabled. No HTTP/WebSocket argument becomes an ADB command, device selector, filename, or control event. The stream has bounded video packets, subprocess output, decoder queues, and timeouts. One viewer can capture at a time.

Use the supported `bridge` / `echelon-bridge` launcher. It installs the tested WebSocket transport guard and message limits; a separately configured bare Uvicorn invocation does not inherit those launcher settings.

Phone selection is a user-owned mode `0600` file outside the repository, saved atomically and read with size/type/link checks. The selection pins device identity, the encrypted discovery service (for Wi-Fi), ADB/server paths, matching scrcpy version, and server file hash. The server refuses changed phone identity, unexpected server binary changes, unencrypted/unknown network services, and a non-loopback ADB host listener. Wireless viewing uses only the already-paired native ADB TLS transport by its full service name; it does not fall back to a raw IP/port connection. ADB establishes the paired TLS connection. It uses fixed argv without a host shell and a uniquely named temporary phone file/tunnel. Another local process with access to the user's session can access the dashboard, ADB, or screen data; these checks protect browser origins, not a compromised local account.

Use USB or Android's modern pairing-based, TLS-encrypted Wireless debugging on a trusted network. Android debugging grants broader access than this application's viewer uses. Turn debugging off when finished; forgetting the PC in Android's paired devices revokes its authorization. Keep ADB keys, phone configuration, pairing QR/code, logs, and screen images private. None belong in Git or diagnostics. scrcpy/ADB are separately installed trusted programs, not bundled binaries, and their version/API compatibility needs validation after upgrades.

## Publication checks

Run `uv run python scripts/check_publication.py` before staging/pushing, and pass source archives/wheels with `--archive` after building. The checker inspects the actual Git file list rather than relying only on ignore rules, compares against known local identifiers/configuration values, and blocks private file paths, credential patterns, non-placeholder network addresses, and unreviewed binary files. It does not replace review or scan all historical commits.

Do not publish a file or rewrite a license notice to silence a finding without understanding it. Loopback/unspecified addresses, documentation IP ranges, and deliberately synthetic Bluetooth fixtures are allowed. They do not identify a real user's network or bike.

If a real credential was previously committed, remove it from Git history and revoke/rotate it before publication. Adding an ignore rule or deleting the current file does not remove old copies.

## Reporting a problem

Use the repository host's private security-reporting facility when enabled. Avoid putting credentials, device identifiers, captures, or exploit details in a public issue. For a report that affects an upstream dependency, follow that project's security policy as well.
