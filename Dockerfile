# Wall-E Companion - Docker Image
# Multi-stage build for smaller final image

# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopencv-dev \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopencv-core4.10 \
    libopencv-imgproc4.10 \
    libopencv-videoio4.10 \
    libopencv-dnn4.10 \
    portaudio19 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Create non-root user
RUN useradd -m -u 1000 wall-e && \
    mkdir -p /app/logs /app/models /app/sounds && \
    chown -R wall-e:wall-e /app

# Copy application code
COPY --chown=wall-e:wall-e . .

# Create directories for models and logs
RUN mkdir -p models sounds logs

USER wall-e

# Expose ports
EXPOSE 5173 5174

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5173/api/status', timeout=5)" || exit 1

# Default command
CMD ["python", "main.py"]