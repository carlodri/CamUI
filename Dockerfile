# CamUI for PiCamera2 - Docker
# Must be built and run on a Raspberry Pi (ARM) with camera connected.
#
# Build:
#   docker build -t camui .
#
# Run (camera access requires --privileged or explicit device mapping):
#   docker run --rm -it --privileged \
#     -p 8080:8080 \
#     -v /run/udev:/run/udev:ro \
#     -v ./data:/app/data \
#     -e CAMUI_DATA_DIR=/app/data \
#     camui

FROM debian:bookworm

# Add Raspberry Pi apt repository for libcamera / picamera2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg curl ca-certificates \
    && curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key \
       | gpg --dearmor -o /usr/share/keyrings/raspberrypi-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.gpg] http://archive.raspberrypi.com/debian/ bookworm main" \
       > /etc/apt/sources.list.d/raspi.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-picamera2 \
    python3-libcamera \
    python3-flask \
    python3-pil \
    libcamera-tools \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pyproject.toml first to leverage Docker layer caching
COPY pyproject.toml .
COPY src/ src/

# Install the camui package (picamera2 already installed via apt above)
RUN pip3 install --break-system-packages --no-deps .

# Runtime data directory (gallery images, camera profiles, last-config)
# Mount a volume here for persistence: -v ./data:/app/data
RUN mkdir -p /app/data/gallery /app/data/camera_profiles

EXPOSE 8080

ENV CAMUI_DATA_DIR=/app/data

CMD ["python3", "-m", "camui", "--ip", "0.0.0.0", "--port", "8080"]
