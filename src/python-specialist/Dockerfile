# Use the slim Python 3.11 base image
FROM python:3.11-slim

# 1. Inject the 'uv' binary directly from Astral's official builder image
# This is drastically faster than running 'pip install uv'
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 2. Copy dependencies first to leverage Docker layer caching
COPY requirements.txt .

# 3. Utilize 'uv pip install' to resolve and install packages.
# The '--system' flag is critical because Docker containers do not require virtual environments.
# The '--no-cache' flag ensures the image remains small by dropping downloaded wheels.
RUN uv pip install --system --no-cache -r requirements.txt

# 4. Copy the agent logic
COPY . .

# 5. Boot the ASGI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]