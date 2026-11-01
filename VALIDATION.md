# Validation record - 2026-11-01

## Source distribution 0.1.1

| Check | Result | Boundary |
|---|---|---|
| Staged Python unit/integration suite | 53 passed, 0 failed | Fake UI, printer reports and temporary files; existing Python 3.14 environment with upstream 0.3.0 / MCP 2.3.0 |
| Staged C# source compilation | Passed | Windows .NET Framework x64 compiler; binaries compiled in a separate local verification directory, outside this source distribution |
| Isolated Windows fixture | 40 passed, 0 failed | Synthetic window and deterministic native-state fixtures; no live printer inputs |
| Installer PowerShell AST parse | Passed | Syntax only; does not prove installation on a clean machine |
| Node safety-probe syntax | Passed | `node --check`; no printer contacted |
| Real installed-development MCP/UI | Prepare -> Preview -> Prepare confirmed | Bambu Studio 02.08.02.61; two input attempts, each confirmed by two consecutive native target-state reads plus a separate inspection |
| Project preservation during live navigation | Passed | Original view and visible control/value fingerprint restored; saved project SHA256, size and timestamp unchanged |
| Screenshots in active-tab verification | Not required | Detection uses a strict native-window visibility/ownership/class/control-ID profile |
| Clean-machine installer | **Not performed** | Requires a separate clean Windows environment |
| Extension final Send physical dispatch | **Not performed** | Next explicitly authorized job needs fresh live acceptance evidence |
| Full security audit / certificate pinning | **Not provided** | See `SECURITY.md`; inherited self-signed printer TLS limitation remains |

The public Python suite consists of 48 development mock/unit/integration cases plus five distribution-boundary cases. Eight new protocol tests check active-tab evidence passthrough, explicit unknown state, confirmed/unconfirmed outcomes, dry-run behavior and consumed-observation/no-replay handling.

The native fixture retains 14 existing UI checks and adds 26 active-view, profile-rejection, stable-readback, deadline and navigation-identity checks. It verifies correct and unsupported versions, missing/duplicate/foreign/unowned/hidden branches, inconsistent or ambiguous visibility, delayed/unchanged/oscillating state, read failures and lookalike navigation controls.

The active-tab classifier is specific to the verified Bambu Studio build and structure. Other versions or changed native layouts return unknown rather than assuming the last clicked tab became active. It does not establish universal control support.

No save, slice, final Send, heat, motion, upload or cancellation command was issued during the live navigation verification. Printer telemetry remained in the previously finished state, with heater targets at zero. Development observations are distinct from the staged clean-machine installer and physical-dispatch acceptance gaps.

Existing regression coverage includes busy/stale/error reports; wrong file, job, printer and UI identity; changed selectors; repeat/expired tickets; ambiguous outcomes; durable receipts; generic UI restrictions including Device-page fields; missing/malformed/mismatching private binding configuration; and rejection of unsigned direct LAN dispatch before the original sender is called.

No development logs, private paths, completed bindings, models, camera frames, raw printer telemetry or runtime receipts accompany this record. The exact source manifest describes the published artifact.
