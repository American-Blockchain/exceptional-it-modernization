# Stage 1: Builder
FROM python:3.11-slim AS builder

# Inject uv binary for high-speed dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation for faster cold starts
ENV UV_COMPILE_BYTECODE=1

# Use requirements.txt for now as per current project structure,
# but utilize cache mounts to speed up iterative builds.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-cache-dir -r requirements.txt

# Stage 2: Runtime
# Using the same base image to ensure library compatibility
FROM python:3.11-slim

WORKDIR /app

# Copy the installed site-packages from the builder stage.
# This keeps the final image lean and excludes the uv binary.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy agent logic
COPY . .

# Execution: 3 workers is a safer middle ground for 2.0 vCPUs to avoid contention.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "3"]
