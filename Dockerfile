# Stage 1: Build Frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Final Image
FROM python:3.12-slim

# Install system dependencies: ffmpeg, nginx, supervisor, curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nginx \
    supervisor \
    curl \
    build-essential \
    cmake \
    && curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --extra whisper 2>/dev/null || uv sync --no-dev --extra whisper

# Copy source code
COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
COPY nginx/nginx.conf /etc/nginx/sites-available/default

# Remove default nginx site link and re-link (standard debian/ubuntu nginx setup)
RUN ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

# Copy built frontend from Stage 1
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Create storage directories
RUN mkdir -p storage/originals storage/audio storage/temp data

ENV STORAGE_BASE_PATH=/app/storage
ENV DATABASE_URL=sqlite:////app/data/data.db

EXPOSE 80

ENTRYPOINT ["/app/entrypoint.sh"]
