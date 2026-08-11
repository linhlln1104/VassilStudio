FROM node:24-alpine AS studio-build

WORKDIR /app/frontend/studio-react

COPY frontend/studio-react/package.json frontend/studio-react/package-lock.json ./
RUN npm ci

COPY frontend/studio-react ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV VASSIL_ROOT=/app
ENV VASSIL_CONFIG=/app/config/vassil.example.json
ENV VASSIL_STUDIO_DIR=/app/frontend/studio-react/dist
ENV VASSIL_ENV=docker
ENV VASSIL_LOG_LEVEL=INFO
ENV VVOICE_ROOT=/app
ENV VVOICE_CONFIG=/app/config/vvoice.example.json
ENV VVOICE_STUDIO_DIR=/app/frontend/studio-react/dist

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY frontend ./frontend
COPY config ./config
COPY docs ./docs
COPY scripts ./scripts
COPY --from=studio-build /app/frontend/studio-react/dist ./frontend/studio-react/dist

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[runtime]"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "vvoice.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
