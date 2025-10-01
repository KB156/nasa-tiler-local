# Start from a newer version of Debian which has updated, working packages
FROM debian:bookworm-slim

# Install system packages, including python3-flask for the web server
RUN apt-get update && apt-get install -y \
    libvips-dev \
    libvips-tools \
    libopenjp2-7 \
    ca-certificates \
    curl \
    unzip \
    python3 \
    python3-pip \
    python3-flask \
    gdal-bin \
&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy your Python scripts
COPY make_manifest.py /app/make_manifest.py
COPY server.py /app/server.py

# Download OpenSeadragon for the viewer
RUN mkdir -p /app/static && \
    curl -L -o /tmp/osd.zip https://github.com/openseadragon/openseadragon/releases/download/v4.0.0/openseadragon-bin-4.0.0.zip && \
    unzip /tmp/osd.zip -d /tmp && \
    mv /tmp/openseadragon-bin-4.0.0/openseadragon.min.js /app/static/openseadragon.min.js && \
    rm -rf /tmp/osd.zip /tmp/openseadragon-bin-4.0.0

EXPOSE 8080
CMD ["python3", "/app/server.py"]