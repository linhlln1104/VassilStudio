FROM node:24-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43 AS studio-build

WORKDIR /app/frontend/studio-react

COPY frontend/studio-react/package.json frontend/studio-react/package-lock.json ./
RUN npm ci

COPY frontend/studio-react ./
RUN npm run build

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ARG TORCH_VERSION=2.11.0
ARG PIP_VERSION=26.2.1
ARG VASSIL_VERSION=0.1.0

LABEL org.opencontainers.image.title="VassilStudio" \
      org.opencontainers.image.description="Local-first ZipFormer ASR and ZipVoice TTS studio" \
      org.opencontainers.image.version="${VASSIL_VERSION}" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/linhlln1104/VassilStudio"

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

COPY docker/runtime-linux-cpu.constraints.txt ./docker/runtime-linux-cpu.constraints.txt

RUN python -m pip install --upgrade "pip==${PIP_VERSION}" \
    && python -m pip install \
      --constraint docker/runtime-linux-cpu.constraints.txt \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==${TORCH_VERSION}" "torchaudio==${TORCH_VERSION}"

COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY backend ./backend

RUN python -m pip install \
      --constraint docker/runtime-linux-cpu.constraints.txt \
      ".[runtime]"

COPY config ./config
COPY docs ./docs
COPY scripts ./scripts
COPY --from=studio-build /app/frontend/studio-react/dist ./frontend/studio-react/dist

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "vvoice.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
