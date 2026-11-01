# Changelog

## 0.1.1 - 2026-11-01

- Add independently observed `active_tab` state to window inspection through native adapter 0.1.1.
- Confirm Prepare/Preview transitions through two consecutive native visibility reads after at most one input attempt; preserve unconfirmed outcomes without replay.
- Recognize only the strict Bambu Studio 02.08.02.61 native-window profile; unsupported versions or ambiguous layouts remain unknown.
- Preserve existing Device, authentication, final Send, identity and consumed-observation guards.
- Include English skill preview metadata, eight new Python protocol tests, 26 additional native fixture checks and the active-tab contract documentation.
- Verify a real Prepare -> Preview -> Prepare sequence without screenshots, changing settings or starting a print. Clean-machine installation and physical final Send remain unverified.

## 0.1.0 — 2026-11-01

- Add a reusable Bambu Print skill for project review, preparation, explicitly requested printing, status and camera tasks.
- Add seven MCP tools for observed Studio UI control and guarded official print submission.
- Resolve controls by their actual process/window/runtime identity; support native UIA patterns and bounded custom wx button events without screenshot coordinates.
- Bind a final Send attempt to an exact sliced artifact, selected printer, fresh readiness evidence and a durable single-use receipt.
- Keep local bindings, credentials and runtime state outside the tracked source tree; publish placeholder configuration only.
- Disable unsigned direct LAN dispatch through this distribution's `send_to_printer` wrapper.
- Include fake-adapter tests and an isolated Windows UI fixture. A fresh physical dispatch through the final Send extension and a clean-machine installer run remain unverified.
