# FragAI Nanobot agent, Phase 4.4

Owner repository: https://github.com/yugantb24/Nanobot

Work branch: `fragai/nanobot-agent-phase4`. The matching governance-platform
branch carries the migration trace. Both main branches and the running platform
are kept separate from this packaging review.

The source baseline is Nanobot v0.0.92, commit
`00a40e47b82581ffdf52860eae08ec500d76dd7b`. Original source/licences are preserved;
upstream publishing workflows and packaging are archived under `third_party`.
`fragai/upstream-source.lock.json` records every imported file. The MCP CLI is
built from its exact v0.4.0 source (installed CLI version 0.3.0), with the original
Bun 1.3.11 compiler. The runtime retains Python 3.13, Playwright 1.61.0,
browser-use 0.13.6, Chromium 149, UV 0.11.32, LibreOffice, Poppler, Ghostscript
and the original non-root browser entrypoint. Debian security package updates
are retained and separately recorded; this is not a byte-identical OS rebuild.

The compiler is Go 1.26.5, matching the original binary's build metadata. The
original mcp-oauth-proxy v0.0.3 repository is no longer readable by the build.
Its cached module archive was recovered and its Go h1 checksum matched the
original agent binary exactly. The 54 unchanged Apache-2.0 source files are
retained under `third_party/mcp-oauth-proxy`; `go.mod` selects that local copy.
`fragai/oauth-source.lock.json` records the proof and every file hash. Original
module metadata and CODEOWNERS are archived, with owned metadata tracked too.

## Build and review

```sh
node fragai/verify-sources.mjs
docker build --target agent -t fragai-nanobot-agent:review .
node fragai/check-inventory.mjs fragai-nanobot-agent:review
node fragai/check-runtime.mjs fragai-nanobot-agent:review
```

Go tests/vet and the seven MCP CLI unit suites run during the build. Runtime
verification runs an actual MCP fixture and synthetic streaming model in a
network-disabled container, using no external accounts or customer data. It
checks CLI discovery/tool execution, agent model/tool round trips, governance
launch/configuration, browser automation, office/PDF tools and restart. The
four-stage comparison preserves synthetic records through baseline, candidate,
candidate restart and baseline rollback. JSON reports are retained under `bin`;
only test-labelled containers and their owned volume are cleaned up.

`docker build --target cli` builds the separate CLI/sandbox image selected by
the agent's linked `BaseImage`. `--target agent-runtime` builds its browser/office
dependencies without the Go executable. Release automation builds the exact same
source for native AMD64 and ARM64 and gates publication on compatibility checks.
Image labels record the owned repository, source commit and upstream revision.

## Publication and platform compatibility

The intended public images are:

- `ghcr.io/yugantb24/fragai-nanobot-agent:v0.0.92-fragai.4.4-rc.1`
- `ghcr.io/yugantb24/fragai-nanobot-agent-runtime:v0.0.92-fragai.4.4-rc.1`
- `ghcr.io/yugantb24/fragai-nanobot:v0.0.92-fragai.4.4-rc.1`

The agent must retain `nanobot run`, port 8080, `/mcp`, `/mcp/chat`, `/healthz`,
the `.nanobot/state/nanobot.db` workspace state, repeated `--config`,
`NANOBOT_ENV_FILE`, `NANOBOT_CONFIG_FILE` and existing authentication interfaces.
The fixture mirrors governance main `1a3474257`'s generated launch contract.
Publishing does not change `NanobotAgentImage` in governance-platform; that
default cutover and live Docker/Kubernetes deployment checks are a separate PR.
Real model providers, production OAuth/Okta and customer backup restores are
not established by offline fixtures. Existing Obot Go module identities and
their pinned resolution remain a separate Phase 5 source-ownership audit.
