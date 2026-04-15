FROM mcr.microsoft.com/mirror/docker/library/python:3.11-slim AS builder

# Inject uv binary for high-speed dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation for faster cold starts
ENV UV_COMPILE_BYTECODE=1

# Install git, ca-certificates, curl, and Node.js (for Agent Lightning dashboard build)
RUN apt-get update && \
    apt-get install -y git ca-certificates curl build-essential && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Clone Microsoft Agent Lightning from GitHub (building from source per Gemini.MD)
RUN git clone https://github.com/microsoft/agent-lightning.git /tmp/agent-lightning

# Build the Agent Lightning dashboard (Vite)
WORKDIR /tmp/agent-lightning/dashboard
RUN npm ci && npm run build

# The dashboard artifacts are generated at /tmp/agent-lightning/agentlightning/dashboard
# Move them to our app directory
WORKDIR /app
RUN mv /tmp/agent-lightning/agentlightning/dashboard /app/agentlightning_dashboard

# Install standard dependencies
COPY requirements.txt .
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Install Agent Lightning from source with APO support
RUN uv pip install --system --no-cache-dir /tmp/agent-lightning[apo]


# ─── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM mcr.microsoft.com/mirror/docker/library/python:3.11-slim

WORKDIR /app

# Copy the installed site-packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the built Agent Lightning dashboard
COPY --from=builder /app/agentlightning_dashboard /app/agentlightning_dashboard

# Copy agent logic
COPY . .

# Execution: 3 workers for 2.0 vCPUs; uvloop enforces C-level async I/O for maximum throughput.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "3", "--loop", "uvloop"]
