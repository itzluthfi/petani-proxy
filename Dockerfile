FROM python:3.11-slim

LABEL maintainer="itzluthfi"
LABEL description="PetaniProxy - High-Performance Rotating Proxy Gateway, WARP & Scraper Suite"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8888

WORKDIR /app

# Install system utilities needed for networking & audio decoding
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose gateway port
EXPOSE 8888

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://127.0.0.1:8888/api/status || exit 1

# Default command: run rotating proxy gateway
CMD ["python", "main.py", "--gateway", "--port", "8888", "--background"]
