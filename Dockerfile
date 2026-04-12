# ==========================================
# Phase 1: Build Frontend (Vue 3 + Vite)
# ==========================================
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

# Install dependencies (leverage cache)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy source and build
COPY frontend/ ./
RUN npm run build

# ==========================================
# Phase 2: Build Backend & Serve
# ==========================================
FROM python:3.11-slim

# Install system dependencies (e.g., ffmpeg for TTS if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend assets — served by FastAPI StaticFiles
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

# Set up data directories and copy default configs
RUN mkdir -p /app/data/logs /app/data/exports /app/data/media /app/data/prompts
# Copy example configs so first-run generates correct defaults
COPY backend/data/config.example.json /app/data/config.example.json
COPY backend/data/prompts/soul.md     /app/data/prompts/soul.md
VOLUME /app/data

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend
ENV FRONTEND_DIST_DIR=/app/frontend_dist
ENV OMNIFLOW_DATA_DIR=/app/data

EXPOSE 8000

# Start Uvicorn (PYTHONPATH is /app/backend, so module is app.main)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
