# 程星 ONVIF / ChengXing ONVIF
# 纯网页版 Docker 镜像（含 FFmpeg + MediaMTX）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    CXONVIF_HOME=/data \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "opencv-python-headless>=4.9"

# MediaMTX（按平台下载）
ARG TARGETARCH=amd64
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) ASSET="linux_amd64.tar.gz" ;; \
      arm64) ASSET="linux_arm64v8.tar.gz" ;; \
      *) ASSET="linux_amd64.tar.gz" ;; \
    esac; \
    URL="$(curl -fsSL -H 'User-Agent: cxonvif' https://api.github.com/repos/bluenviron/mediamtx/releases/latest | grep -o "https://[^\"]*${ASSET}" | head -1)"; \
    mkdir -p /app/vendor/mediamtx; \
    curl -fsSL "$URL" -o /tmp/mediamtx.tar.gz; \
    tar -xzf /tmp/mediamtx.tar.gz -C /tmp; \
    cp /tmp/mediamtx /app/vendor/mediamtx/mediamtx; \
    chmod +x /app/vendor/mediamtx/mediamtx; \
    rm -f /tmp/mediamtx.tar.gz

COPY . .

VOLUME ["/data"]
EXPOSE 5552 8554 8888 8889 8189/udp
EXPOSE 8001-8020

CMD ["python", "-m", "cxonvif", "serve", "--no-browser"]
