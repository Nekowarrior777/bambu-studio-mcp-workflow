# Active view and verified tab transitions

Native Windows adapter version: **0.1.1**.

`studio_ui_inspect(window_id=...)` includes an `active_tab` descriptor independently of the displayed control filter. Check `verified`, `id`, `source`, `profile`, `studio_version` and `reason`. A missing or unsupported signal remains unknown.

For the installed Bambu Studio **02.08.02.61**, the adapter identifies the three native Plater canvas branches by a strict version and structure profile. It checks the same process, parent/container ownership, native classes and relative control-ID pairs `[1,3]`, `[5,6]`, `[8,9]`. Exactly one canvas branch and its parent must be visible under a visible common container. Enumeration order, sidebar fields and the most recent click do not determine the active state. The third recognized internal view is Assemble; verified Prepare/Preview switching is the supported navigation contract.

The profile is specific to this verified installed build. A changed version, allocation pattern, hidden container, duplicate branch or contradictory visibility returns `verified: false` and a reason. It does not guess the selected tab.

For a uniquely identified Prepare or Preview topbar click, `studio_ui_action` sends input at most once and includes `result.verification`:

- `requested_tab`, `before` and `after` describe the requested and independently observed state.
- `confirmed: true` requires two consecutive target-state reads within the bounded verification period.
- `outcome: tab_switch_confirmed` means the postcondition was observed after input.
- `outcome: already_in_requested_state` performs no input when the observed view already matches.
- `outcome: invoked_unconfirmed` means input was attempted but the postcondition was not confirmed. Inspect again; never automatically replay it.

Polling reads state only. It has a 3.5-second confirmation deadline and an iteration cap; the existing outer helper timeout remains in force. Readback does not change process, filament, plate, model settings, or printer state. Existing executable/window identity, token, Device, authentication, final Send and consumed-observation guards remain in place.

The Python MCP controller already forwards these additive helper fields. Rebuilding the one-request native helper makes them available to the existing connected MCP without a Python-server restart. Updated tool descriptions load on the next normal server restart.

## Source basis

- [Pinned Plater construction](https://github.com/bambulab/BambuStudio/blob/v02.08.02.61/src/slic3r/GUI/Plater.cpp#L6788): View3D, Preview and Assemble are constructed as sibling panels.
- [Pinned Plater selection](https://github.com/bambulab/BambuStudio/blob/v02.08.02.61/src/slic3r/GUI/Plater.cpp#L11199): the selected panel is shown and the others hidden.
- [Pinned Notebook selection](https://github.com/bambulab/BambuStudio/blob/v02.08.02.61/src/slic3r/GUI/Notebook.cpp#L198): selection is posted asynchronously, so input acknowledgement is not a view postcondition.
- [Pinned OpenGL manager](https://github.com/bambulab/BambuStudio/blob/v02.08.02.61/src/slic3r/GUI/OpenGLManager.cpp#L772), [wx native canvas creation](https://github.com/wxWidgets/wxWidgets/blob/master/src/msw/glcanvas.cpp) and [wx ID allocation](https://github.com/wxWidgets/wxWidgets/blob/master/src/common/windowid.cpp) explain the observed construction fingerprint. The exact numeric profile is an installed-build validation boundary, not a universal wx API guarantee.

## Verification evidence

- The development suite passed 48 Python mock/unit/integration tests, including eight new protocol tests. The staged public suite additionally includes five distribution-boundary tests (53 total).
- 40 isolated native fixture checks passed, including profile rejection, asynchronous readback, deadline and navigation-identity boundaries.
- Live current MCP: Prepare -> Preview -> Prepare. Both input attempts returned `tab_switch_confirmed`, with two consecutive target-state reads and a separate inspection after each.
- The original tab and visible control/value fingerprint were restored. The saved project SHA256, size and timestamp remained unchanged. No save, slice, final Send, heating or movement command was issued.
- See the sanitized [validation record](../../../VALIDATION.md). Raw development logs, models, UI receipts and printer telemetry are excluded from this distribution.
