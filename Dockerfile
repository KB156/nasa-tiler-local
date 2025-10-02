# Start from a newer version of Debian which has updated, working packages
FROM debian:bookworm-slim

# Install system packages and python
RUN apt-get update && apt-get install -y \
    libvips-dev \
    libvips-tools \
    libopenjp2-7 \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy your Python scripts
# NOTE: Ensure you still have the 'make_manifest.py' file in your project folder
COPY make_manifest.py /app/make_manifest.py
COPY server.py /app/server.py

# Install Python libraries using pip
RUN pip install flask gunicorn

# Expose the port Gunicorn will run on
EXPOSE 8080

# Use Gunicorn to run the app. It's much more powerful than the default Flask server.
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:8080", "server:app"]