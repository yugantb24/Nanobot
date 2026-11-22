# syntax=docker/dockerfile:1
# FragAI Phase 4.4. Original packaging is retained under third_party/upstream-packaging.
ARG GO_IMAGE=golang:1.26.5-trixie@sha256:f1a132429b98724a904e9b3bdbaed399d8f923203c3e5170e6def66d0a7cc04c
ARG BUN_IMAGE=oven/bun:1.3.11@sha256:0733e50325078969732ebe3b15ce4c4be5082f18c4ac1a0f0ca4839c2e4e42a7
ARG DEBIAN_IMAGE=debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c
ARG CLI_UV_IMAGE=ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded
ARG WOLFI_IMAGE=cgr.dev/chainguard/wolfi-base@sha256:be019c1c74fe69204a42c4e10bc4d886a49bf5403ffa74374ef7baa408fc9a26

FROM ${GO_IMAGE} AS go-build
ENV GOMAXPROCS=2
WORKDIR /src
COPY go.mod go.sum ./
COPY third_party/mcp-oauth-proxy/ ./third_party/mcp-oauth-proxy/
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
ARG VERSION=v0.0.92-fragai.4.4-rc.1
ARG CLI_IMAGE=ghcr.io/yugantb24/fragai-nanobot
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go vet -p=2 ./... && go test -p=2 -count=1 ./... && \
    CGO_ENABLED=0 go build -buildvcs=false -trimpath -tags netgo \
      -ldflags="-s -w -X github.com/obot-platform/nanobot/pkg/version.Tag=${VERSION} -X github.com/obot-platform/nanobot/pkg/version.BaseImage=${CLI_IMAGE}:${VERSION}" \
      -o /out/nanobot . && \
    mkdir -p /out/licenses/go && \
    find /go/pkg/mod -type f \( -iname 'license*' -o -iname 'notice*' -o -iname 'copying*' -o -iname 'copyright*' \) \
      -exec cp --parents '{}' /out/licenses/go/ \; && \
    go version -m /out/nanobot > /out/build-info.txt

FROM ${BUN_IMAGE} AS mcp-cli-build
WORKDIR /src
COPY third_party/mcp-cli/ ./
RUN bun install --frozen-lockfile && \
    bun build --compile --minify src/index.ts --outfile /out/mcp-cli && \
    bun test --timeout 60000 tests/config.test.ts tests/output.test.ts tests/client.test.ts tests/errors.test.ts tests/grep.test.ts tests/filter.test.ts tests/cli-errors.test.ts && \
    mkdir -p /out/licenses/mcp-cli && cp LICENSE /out/licenses/mcp-cli/LICENSE && \
    find node_modules -type f \( -iname 'license*' -o -iname 'notice*' -o -iname 'copying*' -o -iname 'copyright*' \) \
      -exec cp --parents '{}' /out/licenses/mcp-cli/ \;

FROM ${UV_IMAGE} AS uv

FROM ${CLI_UV_IMAGE} AS cli-uv

FROM scratch AS binary
COPY --from=go-build /out/ /

FROM ${DEBIAN_IMAGE} AS tools
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get full-upgrade -y && \
    apt-get install -y --no-install-recommends \
      bash git curl wget jq gzip unzip xz-utils coreutils findutils grep sed gawk ripgrep \
      poppler-utils ca-certificates python3 python3-venv nodejs npm && \
    rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=mcp-cli-build /out/mcp-cli /usr/bin/mcp-cli
COPY --from=mcp-cli-build /out/licenses/ /licenses/
COPY LICENSE /licenses/nanobot-APACHE-2.0.txt
COPY third_party/mcp-oauth-proxy/LICENSE /licenses/mcp-oauth-proxy-APACHE-2.0.txt
COPY third_party/licenses/ /licenses/runtime/
COPY FRAGAI_NOTICES.md /licenses/FRAGAI_NOTICES.md
COPY scripts/prefetch-tiktoken-encodings.sh /tmp/prefetch-tiktoken-encodings.sh
COPY fragai/tokenizer-cache.lock.json fragai/verify-token-cache.py /tmp/
ENV TIKTOKEN_CACHE_DIR=/var/cache/tiktoken
RUN chmod +x /tmp/prefetch-tiktoken-encodings.sh && \
    /tmp/prefetch-tiktoken-encodings.sh && python3 /tmp/verify-token-cache.py && \
    rm /tmp/prefetch-tiktoken-encodings.sh /tmp/verify-token-cache.py /tmp/tokenizer-cache.lock.json && \
    useradd -m -u 1000 -d /home/nanobot -s /bin/bash nanobot && \
    mkdir -p /data /home/nanobot/.nanobot && chown -R nanobot:nanobot /data /home/nanobot
ENV HOME=/home/nanobot
ENV NANOBOT_STATE=/data/nanobot.db
ENV NANOBOT_RUN_LISTEN_ADDRESS=0.0.0.0:8080
WORKDIR /home/nanobot
EXPOSE 8080
VOLUME ["/data"]

FROM ${WOLFI_IMAGE} AS cli-tools
RUN apk update && apk upgrade --no-cache && apk add --no-cache \
      bash git curl "libnghttp2-14>=1.70.0-r0" wget jq gzip xz coreutils findutils grep sed gawk ripgrep poppler-utils
COPY --from=cli-uv /uv /uvx /usr/bin/
COPY --from=mcp-cli-build /out/mcp-cli /usr/bin/mcp-cli
COPY --from=mcp-cli-build /out/licenses/ /licenses/
COPY LICENSE /licenses/nanobot-APACHE-2.0.txt
COPY third_party/mcp-oauth-proxy/LICENSE /licenses/mcp-oauth-proxy-APACHE-2.0.txt
COPY third_party/licenses/ /licenses/runtime/
COPY FRAGAI_NOTICES.md /licenses/FRAGAI_NOTICES.md
COPY scripts/prefetch-tiktoken-encodings.sh /tmp/prefetch-tiktoken-encodings.sh
COPY fragai/tokenizer-cache.sha256 /tmp/tokenizer-cache.sha256
ENV TIKTOKEN_CACHE_DIR=/var/cache/tiktoken
RUN chmod +x /tmp/prefetch-tiktoken-encodings.sh && /tmp/prefetch-tiktoken-encodings.sh && \
    (cd /var/cache/tiktoken && sha256sum -c /tmp/tokenizer-cache.sha256) && \
    rm /tmp/prefetch-tiktoken-encodings.sh /tmp/tokenizer-cache.sha256 && \
    adduser -D -u 1000 -h /home/nanobot -s /bin/bash nanobot && \
    mkdir -p /data /home/nanobot/.nanobot && chown -R nanobot:nanobot /data /home/nanobot
ENV HOME=/home/nanobot
ENV NANOBOT_STATE=/data/nanobot.db
ENV NANOBOT_RUN_LISTEN_ADDRESS=0.0.0.0:8080
WORKDIR /home/nanobot
EXPOSE 8080
VOLUME ["/data"]

FROM cli-tools AS cli
ARG VERSION=v0.0.92-fragai.4.4-rc.1
ARG SOURCE_REVISION=local
LABEL org.opencontainers.image.title="FragAI Nanobot CLI" \
      org.opencontainers.image.source="https://github.com/yugantb24/Nanobot" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="Apache-2.0 AND MIT" \
      ai.fragai.upstream.revision="00a40e47b82581ffdf52860eae08ec500d76dd7b"
COPY --from=go-build /out/nanobot /usr/local/bin/nanobot
COPY --from=go-build /out/licenses/ /licenses/
COPY --from=go-build /out/build-info.txt /usr/local/share/fragai/build-info.txt
USER nanobot
ENTRYPOINT ["/usr/local/bin/nanobot"]
CMD ["run"]

FROM tools AS agent-runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb x11vnc x11-xserver-utils wmctrl fluxbox websockify \
      libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress \
      ghostscript libheif-examples && rm -rf /var/lib/apt/lists/*
COPY fragai/playwright-requirements.txt fragai/browser-use-requirements.txt /usr/local/share/fragai/
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/ms-playwright
RUN python3 -m venv /opt/playwright-venv && \
    /opt/playwright-venv/bin/pip install --no-cache-dir --no-deps -r /usr/local/share/fragai/playwright-requirements.txt && \
    /opt/playwright-venv/bin/pip check && \
    /opt/playwright-venv/bin/playwright install chromium --with-deps && \
    python3 -m venv /opt/browser-use-venv && \
    /opt/browser-use-venv/bin/pip install --no-cache-dir --no-deps -r /usr/local/share/fragai/browser-use-requirements.txt && \
    /opt/browser-use-venv/bin/pip check && \
    ln -sf /opt/browser-use-venv/bin/browser-use /usr/local/bin/browser-use
COPY scripts/agent-entrypoint.sh /usr/local/bin/nanobot
RUN chmod +x /usr/local/bin/nanobot
COPY fragai/build-inputs.lock.json fragai/upstream-source.lock.json fragai/mcp-cli-source.lock.json /usr/local/share/fragai/
ARG VERSION=v0.0.92-fragai.4.4-rc.1
ARG SOURCE_REVISION=local
LABEL org.opencontainers.image.title="FragAI Nanobot agent runtime" \
      org.opencontainers.image.source="https://github.com/yugantb24/Nanobot" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="Apache-2.0 AND MIT" \
      ai.fragai.upstream.revision="00a40e47b82581ffdf52860eae08ec500d76dd7b"
ENV DISPLAY=:99
ENV PATH="/home/nanobot/.local/bin:$PATH"
ENTRYPOINT ["/usr/local/bin/nanobot"]
CMD ["run"]

FROM agent-runtime AS agent
ARG VERSION=v0.0.92-fragai.4.4-rc.1
ARG SOURCE_REVISION=local
LABEL org.opencontainers.image.title="FragAI Nanobot agent" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${VERSION}"
COPY --from=go-build /out/nanobot /usr/local/libexec/nanobot
COPY --from=go-build /out/licenses/ /licenses/
COPY --from=go-build /out/build-info.txt /usr/local/share/fragai/build-info.txt
