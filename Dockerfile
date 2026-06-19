# Multi-stage build for minimal final image
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency manifests. uv.lock pins every (transitive) dependency to an
# exact, hash-verified version (README.md is needed by hatchling metadata).
COPY pyproject.toml uv.lock README.md ./

# Install locked dependencies into an isolated virtual environment.
#   --frozen         : use the committed uv.lock as-is (no version re-resolution)
#   --only-binary    : install pre-built wheels only, never build sdists / run setup scripts
#   --require-hashes : verify every artifact against the hashes pinned in the lockfile
# The application is launched via `python bot.py` from /app (all modules are
# top-level), so the project package itself does not need to be installed -- only
# its locked dependencies.
RUN uv venv /opt/venv && \
    uv export --frozen --no-dev --no-emit-project --format requirements-txt -o /tmp/requirements.txt && \
    VIRTUAL_ENV=/opt/venv uv pip install --no-deps --only-binary :all: --require-hashes -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Download the obscura headless browser binary (pinned release).
# obscura is a lightweight, CDP-compatible headless browser written in Rust that
# replaces the bundled Chromium previously installed via Playwright. Playwright is
# kept only as a CDP *client* that connects to this binary at runtime.
ARG OBSCURA_VERSION=v0.1.8
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    case "${TARGETARCH:-amd64}" in \
      amd64) OBSCURA_ARCH=x86_64 ;; \
      arm64) OBSCURA_ARCH=aarch64 ;; \
      *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    # Follow GitHub's release redirect, but restrict both the initial request and
    # any redirect target to HTTPS so it can never be downgraded to an insecure URL.
    curl --proto '=https' --proto-redir '=https' -fsSL \
      -o /tmp/obscura.tar.gz \
      "https://github.com/h4ckf0r0day/obscura/releases/download/${OBSCURA_VERSION}/obscura-${OBSCURA_ARCH}-linux.tar.gz" && \
    mkdir -p /opt/obscura && tar xzf /tmp/obscura.tar.gz -C /opt/obscura && \
    rm /tmp/obscura.tar.gz && \
    chmod +x /opt/obscura/obscura /opt/obscura/obscura-worker

# Stage 2: Runtime - Minimal production image
FROM python:3.11-slim

# Install minimal system dependencies and create non-root user.
# No browser/X11 libraries are needed anymore: price scraping talks to the obscura
# sidecar over CDP instead of launching a local Chromium.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 repackit \
    && mkdir -p /app \
    && chown -R repackit:repackit /app

# Set working directory
WORKDIR /app

# Copy virtual environment from builder (read-only for all users)
COPY --from=builder --chown=root:root --chmod=555 /opt/venv /opt/venv

# Copy the obscura headless browser binaries (browser + render worker)
COPY --from=builder --chmod=555 /opt/obscura/obscura /usr/local/bin/obscura
COPY --from=builder --chmod=555 /opt/obscura/obscura-worker /usr/local/bin/obscura-worker

# Copy application code (read-only for security - prevents tampering)
COPY --chown=root:root --chmod=555 pyproject.toml ./
COPY --chown=root:root --chmod=555 *.py ./
COPY --chown=root:root --chmod=555 handlers/ ./handlers/
COPY --chown=root:root --chmod=555 utils/ ./utils/

# Install gosu and create the entrypoint script in a single layer.
# The entrypoint starts the obscura CDP sidecar in the background (as the non-root
# repackit user), waits for it to accept connections, then drops privileges and
# launches the bot. This reduces image size and satisfies SonarCloud S7031.
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/* && \
    printf '%s\n' \
    '#!/bin/bash' \
    'set -e' \
    '# Create data directory with correct ownership (runs as root)' \
    'mkdir -p /app/data' \
    'chown -R 1000:1000 /app/data 2>/dev/null || true' \
    'OBSCURA_PORT="${OBSCURA_PORT:-9222}"' \
    '# Start the obscura headless browser sidecar in the background (non-root)' \
    'gosu 1000:1000 obscura serve --port "${OBSCURA_PORT}" --stealth >/app/data/obscura.log 2>&1 &' \
    '# Wait for the CDP endpoint to accept connections before starting the bot' \
    'for _ in $(seq 1 30); do (echo > "/dev/tcp/127.0.0.1/${OBSCURA_PORT}") >/dev/null 2>&1 && break; sleep 0.5; done' \
    '# Drop privileges and execute the main command as the repackit user' \
    'exec gosu 1000:1000 "$@"' \
    > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Expose ports
EXPOSE 8443 8444

# Set entrypoint to start the obscura sidecar and handle permissions, then drop
# to the repackit user. The bot process itself runs as non-root (uid 1000).
ENTRYPOINT ["/entrypoint.sh"]

# Run the bot (executed as repackit user via entrypoint)
CMD ["python", "bot.py"]
