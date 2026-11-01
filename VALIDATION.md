# Validation record — 2026-11-01

| Check | Result | Boundary |
|---|---|---|
| Staged Python unit/integration suite | 45 passed, 0 failed | Fake UI, printer reports and temporary files; existing Python 3.14 environment with upstream 0.3.0 / MCP 2.3.0 |
| Staged C# source compilation | Passed | Windows .NET Framework x64 compiler; binaries created outside this source distribution |
| Isolated Windows fixture | 14 passed, 0 failed | Synthetic window only: button, field, checkbox, list, tab, custom HWND panel and rejection checks |
| Installer PowerShell AST parse | Passed | Syntax only; does not prove installation on a clean machine |
| Node safety-probe syntax | Passed | `node --check`; no printer contacted |
| Real installed-development MCP/UI | Previously observed | Tool discovery and reversible project-tab navigation; separate from this staged installer |
| Clean-machine installer | **Not performed** | Requires a separate clean Windows environment |
| Extension final Send physical dispatch | **Not performed** | Next explicitly authorized job needs fresh live acceptance evidence |
| Full security audit / certificate pinning | **Not provided** | See `SECURITY.md`; inherited self-signed printer TLS limitation remains |

The Python tests cover busy/stale/error reports; wrong file, job, printer and UI identity; changed selectors; repeat/expired tickets; ambiguous outcomes; durable receipts; generic UI restrictions including device-page fields; missing/malformed/mismatching private binding configuration; and rejection of unsigned direct LAN dispatch before the original sender is called. No upload, heat, motion, print start or cancellation was part of the staged test suite.

A first navigation test during development compared entire UIA child order and failed because Studio recreates/reorders controls. Semantic section visibility was then checked and the reversible navigation passed. This is not evidence that every Studio control supports every UIA pattern.

No development logs, private paths, completed printer bindings, model data, camera frames or runtime receipts accompany this record. The source manifest and independently reviewed file list describe the published artifact.
