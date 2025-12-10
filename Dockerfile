# Multi-stage build for minimal final image
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files (README.md needed by hatchling)
COPY pyproject.toml README.md ./

# Install dependencies in a virtual environment
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -e .

# Stage 2: Runtime - Minimal production image
FROM python:3.11-slim

# Install system dependencies for Playwright and create non-root user
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-liberation \
    gnupg \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    wget \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 repackit \
    && mkdir -p /app \
    && chown -R repackit:repackit /app

# Set working directory
WORKDIR /app

# Copy virtual environment from builder (read-only for all users)
COPY --from=builder --chown=root:root --chmod=555 /opt/venv /opt/venv

# Copy application code (read-only for security - prevents tampering)
COPY --chown=root:root --chmod=555 pyproject.toml ./
COPY --chown=root:root --chmod=555 *.py ./
COPY --chown=root:root --chmod=555 handlers/ ./handlers/
COPY --chown=root:root --chmod=555 utils/ ./utils/

# Install gosu and create entrypoint script in a single layer
# This reduces image size and satisfies SonarCloud S7031
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/* && \
    echo '#!/bin/bash\n\
set -e\n\
# Create data directory with correct ownership (runs as root)\n\
mkdir -p /app/data\n\
chown -R 1000:1000 /app/data 2>/dev/null || true\n\
# Drop privileges and execute main command as repackit user\n\
exec gosu 1000:1000 "$@"' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Switch to non-root user for Playwright installation
USER repackit

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Install Playwright browsers (as non-root user)
RUN playwright install chromium && \
    playwright install-deps chromium || true

# Expose ports
EXPOSE 8443 8444

# Switch to root for entrypoint execution only
# IMPORTANT: The entrypoint immediately drops privileges to repackit user (uid 1000)
# This is necessary to handle Docker volume permissions automatically on startup
# The actual bot process runs as non-root user for security
USER root

# Set entrypoint to handle permissions, then drop to repackit user
ENTRYPOINT ["/entrypoint.sh"]

# Run the bot (executed as repackit user via entrypoint)
CMD ["python", "bot.py"]
