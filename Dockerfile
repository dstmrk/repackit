# Multi-stage build for minimal final image
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies in a virtual environment
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -e .

# Stage 2: Runtime - Minimal production image
FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
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
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 repackit && \
    mkdir -p /app/data/logs && \
    chown -R repackit:repackit /app

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=repackit:repackit . .

# Switch to non-root user
USER repackit

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Install Playwright browsers (as non-root user)
RUN playwright install chromium && \
    playwright install-deps chromium || true

# Expose ports
EXPOSE 8443 8444

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8444/health', timeout=5.0)" || exit 1

# Run the bot
CMD ["python", "bot.py"]
