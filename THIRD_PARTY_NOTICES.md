# Third-party components

This source distribution uses separate upstream components; it does not bundle their installed environments, binaries or printer credentials.

| Component | Pinned source/version | License / role |
|---|---|---|
| unofficial-bambu-mcp | 0.3.0, Daniele Finocchiaro, https://github.com/danielefinocchiaro/unofficial-bambu-mcp | MIT; saved-project operations and MCP server |
| bambu-printer-mcp | commit `b3c33f55998b946914273e95fc26d5632bc86e01`, https://github.com/DMontgomery40/bambu-printer-mcp | GPL-2.0; independent file/live-printer validation |
| MCP Python SDK | 2.3.0 | MIT; MCP transport/runtime |
| Bambu Studio | installed by the user, https://github.com/bambulab/BambuStudio | Separate official application; not redistributed |
| Windows .NET UI Automation | Windows system framework | Built-in platform dependency; not redistributed |

The repository's `LICENSE` is the GPL-2.0 license text retained with the safety-runtime dependency. Preserve upstream license/copyright files when installing dependencies. The scoped 0.3.0 Windows-basename patch modifies the separately installed MIT package and records its own backup/diff locally.

This project is an unofficial integration and is not affiliated with or endorsed by Bambu Lab or the upstream maintainers. Product names remain their owners' trademarks. The dependency lock is a record of a tested environment, not a security guarantee; review upstream advisories and source changes when updating pins.
