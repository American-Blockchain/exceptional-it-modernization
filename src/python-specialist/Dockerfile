FROM mcr.microsoft.com/mirror/docker/library/python:3.11-slim AS builder

# Inject uv binary for high-speed dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation for faster cold starts
ENV UV_COMPILE_BYTECODE=1

# Install git and ca-certificates for uv to pull git-based dependencies
RUN apt-get update && apt-get install -y git ca-certificates && rm -rf /var/lib/apt/lists/*

# Use requirements.txt for now as per current project structure,
COPY requirements.txt .
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM mcr.microsoft.com/mirror/docker/library/python:3.11-slim

WORKDIR /app

# Copy the installed site-packages from the builder stage.
# This keeps the final image lean and excludes the uv binary.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy agent logic
COPY . .

# Execution: 3 workers is a safer middle ground for 2.0 vCPUs to avoid contention.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "3"]
