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

# Copy built frontend assets into the backend static directory
# We need to mount these in FastAPI to serve the SPA
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

# Set up data directories
RUN mkdir -p /app/data/logs /app/data/exports
VOLUME /app/data

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend
# Let backend know where frontend dist is
ENV FRONTEND_DIST_DIR=/app/frontend_dist

EXPOSE 8000

# Start Uvicorn
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
