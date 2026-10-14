# Dockerfile

FROM node:20-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim

# System deps: ffmpeg for audio, Pango + Cairo for WeasyPrint, build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# uv for fast pip installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python deps first (cache layer)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy app code
COPY app/ ./app/
COPY templates/ ./templates/
COPY data/ ./data/
COPY --from=web-build /app/static/ ./app/static/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]