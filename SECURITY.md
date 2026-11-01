# Security and privacy

## Scope and trust boundary

The MCP server runs as the local Windows user. A connected agent can read model/project data and operate supported Studio controls. Install only in a local MCP client you trust. The distribution does not expose an HTTP server, open firewall ports, change Defender, enable Developer Mode/LAN-only mode, change authentication, or weaken system TLS settings.

This is not a sandbox against a malicious local user, compromised MCP client, replaced executable, or hostile process running as the same account. Exact executable paths and UIA/HWND identity checks reduce accidental targeting; they do not cryptographically attest the Bambu Studio executable.

## Connection limitation inherited from upstream

The imported `bambu-printer-mcp` runtime accepts the printer's self-signed MQTT/FTPS certificates with `rejectUnauthorized:false` in relevant connection paths. This supplies encrypted transport but **does not establish CA-verified or certificate-pinned server identity**. Fresh serial/model reports are operational checks, not cryptographic authentication of the remote endpoint.

Use a trusted local network. Do not forward printer/MCP ports to the Internet. Treat an untrusted shared network or active network attacker as outside this release's security assurance. This installer does not add a certificate pinning solution and must not be described as a full connection-security audit. The final physical print command uses the user's official Bambu Studio application; the distribution disables the wrapper's unsigned `via='lan'` start path. Independent upstream tools have their own controls and limitations.

## Private local files

- Configure the existing printer connector's access information outside Git, normally `%LOCALAPPDATA%\BambuPrinterMCP\printer.env`.
- Copy `examples/printer-bindings.example.json` to `%LOCALAPPDATA%\BambuStudioMCPWorkflow\printer-bindings.json` and fill in your verified name/serial locally. It contains no access code. `BAMBU_WORKFLOW_BINDINGS` may point to another private local file.
- State, single-use tickets and receipts default to `%LOCALAPPDATA%\BambuStudioMCPWorkflow\state`, or `BAMBU_WORKFLOW_STATE_DIR`.
- Keep projects, photos, output, logs, keys and connection settings outside this repository. `.gitignore` is a secondary aid; publish an explicit reviewed source-file list, not a recursive working-directory upload.
- UI inspection can reveal window titles, filenames and non-password field values. Treat returned snapshots and diagnostic reports as private. Password fields are redacted and excluded from action paths, but other sensitive text may not be marked as a password by its application.

## Hardware actions and uncertainty

Review/preparation is not a print request. Physical starts require the user's specific request, current bed clearance, compatible material/nozzle/plate, independent file inspection, live ready status and the exact official dialog. Busy/error states reject. Tickets expire and are consumed before one Send attempt. A lost response is not permission to retry: retain receipts, inspect the actual job and reconcile the result.

Do not test against a live printer by starting a new job. Fake-adapter and isolated Windows-fixture results do not prove physical print safety or quality. Disable or disconnect the server from the MCP client when its capabilities are not wanted.

## Reporting

When reporting an issue publicly, remove credentials, serial/IP/MAC values, account details, local usernames/paths, model/photo content, runtime snapshots and receipts. Provide a synthetic reproduction and software versions instead. Do not publish a security report containing live access information.
