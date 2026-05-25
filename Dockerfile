FROM python:3.11-slim

# Install system deps for Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates \
    libnss3 libatk-bridge2.0-0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libxshmfence1 libasound2 libpangocairo-1.0-0 \
    libgtk-3-0 fonts-liberation libdrm2 libegl1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
# pytest is included so Docker is the canonical test environment; host Python
# may not have browser-agent dependencies installed.
RUN pip install --no-cache-dir browser-use playwright openai anthropic langchain-openai langchain-anthropic litellm pytest

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Create app directory
WORKDIR /app

# Copy scripts
COPY scripts/ /app/scripts/
COPY tasks/ /app/tasks/

# Persistent browser profiles
VOLUME ["/app/profiles"]
VOLUME ["/app/output"]

ENV PYTHONUNBUFFERED=1
ENV BROWSER_PROFILE_DIR=/app/profiles
ENV OUTPUT_DIR=/app/output

ENTRYPOINT ["python3"]
CMD ["--help"]
