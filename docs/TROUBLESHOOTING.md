# Troubleshooting and maintenance

Start with a read-only check of the Studio extension and printer status. Keep private configuration, model files and runtime receipts intact while diagnosing a problem.

## No MCP tools appear

After adding or changing an MCP registration, restart the client or open a fresh Codex session. Confirm that the configured Python executable and `enhanced_server.py` path exist. For `bambu-printer`, confirm the Node executable and built `dist/index.js` path.

The [configuration examples](GETTING_STARTED.md#4-register-both-mcp-servers) contain placeholders; replace them with absolute local paths. A literal `%LOCALAPPDATA%` or `<REPOSITORY_DIR>` in client arguments will not be expanded automatically. Inspect startup errors privately and share only a redacted summary.

## Studio is minimized, hidden or has no project window

UI actions intentionally reject a minimized/hidden window. Restore the intended Bambu Studio window, then inspect it again. If Studio is closed, open it normally and select the intended saved project. Do not reuse an old window handle or element token.

The project tools operate on saved `.3mf` files. Unsaved GUI changes are not silently read from disk. Preserve the open project and save a separate copy when a task requires one.

## Active view is unknown after a Studio update

The verified native profile currently supports **Bambu Studio 02.08.02.61**. A different build, changed native layout, hidden container or ambiguous state returns `active_tab.verified: false` with a reason. Restore the window and read the reason first.

An unsupported build needs a separately verified adapter profile. Do not change version metadata or loosen identity checks to force a result. Project-file tools may still respond, but an unknown UI state cannot prove a successful tab transition. See [the active-tab contract](../tools/unofficial-bambu-mcp/local_extension/ACTIVE_TABS.md).

## An observation expired or was consumed

Control observations last 30 seconds. An executed attempt consumes its observation before input. Call `studio_ui_inspect` again before a new action. Do not reuse a consumed snapshot or automatically replay an unconfirmed click.

For Prepare/Preview, check `result.verification.confirmed` and the independently observed `before`/`after` state. `invoked_unconfirmed` means the result was not confirmed; it is not permission to press again.

## An existing registration or skill blocks installation

The installer refuses to replace an existing `unofficial-bambu` registration or `bambu-print` skill. Back up the private client configuration and existing skill, compare paths and versions, then migrate deliberately. Use the [manual examples](GETTING_STARTED.md#4-register-both-mcp-servers) as a reference, merging only the intended entries. Do not replace the complete client configuration.

The installer also refuses an unexpected, modified or differently pinned safety-runtime checkout. Preserve that checkout and its changes. Prepare a separate clone to review the new release instead of resetting the working tree.

## Printer status or diagnostics cannot connect

Check the actual printer is powered on and reachable on the intended local network. Verify the model, host, serial and access code in your private environment file without posting their values.

The extension's read-only probe loads `%LOCALAPPDATA%\BambuPrinterMCP\printer.env`. The Node printer registration must load that same file through its resolved absolute `--env-file` argument. A `.env` in an unrelated working directory does not configure this probe. See [private connection setup](GETTING_STARTED.md#3-configure-the-private-printer-connection).

Keep an existing working connection and authorization mode unchanged. Consult the [upstream setup reference](https://github.com/DMontgomery40/bambu-printer-mcp/blob/b3c33f55998b946914273e95fc26d5632bc86e01/docs/SETUP.md) and current vendor guidance for model-specific connection failures. A successful status read does not itself prove permission to start a print.

## Final Send rejects or has an uncertain result

Final submission checks the exact recorded sliced file, selected printer, nozzle/material, fresh readiness, physical bed clearance and the official dialog. Resolve the reported mismatch with current evidence. Never invent a clear-bed observation, clear hardware errors as a shortcut, bypass the dispatcher through a generic UI click, or remove receipts to enable a retry.

If input may have occurred, reconcile current printer/job state and the durable receipt before taking further action. A prior finished print is not evidence that the build plate is empty.

## Update safely

1. Keep the working clone and private client configuration available for rollback. Finish current UI operations and stop the relevant MCP processes before replacing/rebuilding their runtime.
2. Read the new release's compatibility and verification notes. Prepare the new release in a separate clone; run its installer without registration switches first.
3. Preserve private environment files, bindings, generated models and the workflow state/dispatch receipts. The release contains no replacement for that data.
4. Compare the new command/argument/environment paths with the existing private MCP entries. Migrate only those intended entries and the reviewed skill. The installer's refusal to overwrite an existing registration is intentional.
5. Restart the client and run the read-only verification prompt from [Getting started](GETTING_STARTED.md#6-verify-without-printing). A software update does not require a test print.

## Remove the integration

Stop its MCP processes, then remove only the `unofficial-bambu` and `bambu-printer` entries that you installed for this workflow from the private client's MCP settings. Preserve unrelated MCP entries. Remove the user-level `bambu-print` skill only if it belongs to this installation and you no longer use it elsewhere.

The source/runtime clone can be archived after checking it for personal outputs. Keep private credentials, project copies, bindings and dispatch receipts unless you separately choose to retire them. No recursive cleanup command is required, and Bambu Studio itself is a separate installation.

## Report a problem

Open a [GitHub issue](https://github.com/Nekowarrior777/bambu-studio-mcp-workflow/issues) with the release/adapter version, Windows and Studio versions, tool name, expected result, actual result and a short redacted error. State whether the problem occurred during a read-only check, fixture test or an explicitly requested print.

Remove host/IP, serial, access code, account details, user-home paths, model contents and raw telemetry before attaching anything. Include sanitized values such as `active_tab.id`, `verified`, `reason` or `verification.confirmed` when relevant. Never attach a completed client configuration, private environment file, binding or runtime receipt.
