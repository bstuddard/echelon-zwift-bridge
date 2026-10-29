# Security model

This is experimental, local desktop software for a user-controlled exercise bike.

- The supported launcher binds HTTP to loopback only. API routes are read-only, reject untrusted Host names, and do not accept injected watts or shell commands. Other local processes/users may access a loopback service; it is not an authentication boundary.
- The reader requires an explicitly selected bike address. A fresh checkout does not inherit anybody else's bike pin and does not connect based on a matching advertised name. MAC selection limits accidental connections; names, services, and addresses can be imitated.
- Standard BLE power notifications are not encrypted or authenticated by this application. Nearby clients may observe or subscribe. A subscriber is not proof that the client is Zwift.
- The Omarchy widget and installer execute trusted local code with the user's privileges. The installer writes user-local files, backs up bar configuration, and needs no root access. Install/review code you trust, and do not run it with sudo.
- Keep `.env` private (mode `0600`). Unknown/authentication packets and device identifiers are excluded from normal metrics and logs. Explicit scan output contains identifiers locally; redact it before sharing. Optional captures and downloaded diagnostics should also be reviewed before sharing.
- The application itself requires no Echelon or Zwift credentials and makes no cloud requests. Package installation, optional Swagger docs, and the separately installed Zwift game have their own network behavior.

## Publication checks

Run `uv run python scripts/check_publication.py` before staging/pushing, and pass source archives/wheels with `--archive` after building. The checker inspects the actual Git file list rather than relying only on ignore rules, compares against known local identifiers/configuration values, and blocks private file paths, credential patterns, non-placeholder network addresses, and unreviewed binary files. It does not replace review or scan all historical commits.

Do not publish a file or rewrite a license notice to silence a finding without understanding it. Loopback/unspecified addresses, documentation IP ranges, and deliberately synthetic Bluetooth fixtures are allowed. They do not identify a real user's network or bike.

If a real credential was previously committed, remove it from Git history and revoke/rotate it before publication. Adding an ignore rule or deleting the current file does not remove old copies.

## Reporting a problem

Use the repository host's private security-reporting facility when enabled. Avoid putting credentials, device identifiers, captures, or exploit details in a public issue. For a report that affects an upstream dependency, follow that project's security policy as well.
