# FragAI Nanobot distribution

This distribution preserves Nanobot v0.0.92 from obot-platform/nanobot,
revision 00a40e47b82581ffdf52860eae08ec500d76dd7b, under Apache-2.0.
Its original source, copyright and LICENSE are retained. FragAI packaging,
verification and release automation are maintained in yugantb24/Nanobot.

The MCP CLI source is retained in third_party/mcp-cli at upstream v0.4.0,
revision 48592ffed6ff0e51ce8e989a0b810089f24c3ed3, under its original MIT
licence. Its source package reports version 0.3.0, matching the installed
baseline binary. The runtime builds it from source with Bun 1.3.11.

The original mcp-oauth-proxy v0.0.3 source is retained under
third_party/mcp-oauth-proxy with its Apache-2.0 licence. Its module checksum
was verified against the exact checksum embedded in the original Nanobot
agent binary before it was selected as a local Go module replacement.

Linked Go and MCP CLI dependency notices are collected into /licenses during
the build. Debian package copyright files remain in /usr/share/doc and Python
distribution notices remain in their installed dist-info directories. Browser,
Bun and UV components retain their respective upstream licensing terms.
Explicit Bun 1.3.11 and UV 0.11.32 notices are included under
`third_party/licenses` in source and `/licenses/runtime` in the images, from
https://github.com/oven-sh/bun/blob/bun-v1.3.11/LICENSE.md and
https://github.com/astral-sh/uv/tree/0.11.32. Bun's notice identifies its bundled
JavaScriptCore/WebKit and other third-party components and source links.

Original upstream publishing automation and packaging are archived under
third_party/upstream-automation and third_party/upstream-packaging. They are
not the FragAI release workflow. Compatibility import paths, executable names,
configuration keys, database paths and MCP interfaces retain their identities.
