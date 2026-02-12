# Use official Python slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (for Pillow and potential image handling)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY sonarr_calendar.py .
COPY sonarr_calendar_config.py .

# Create directories for output and cache
RUN mkdir -p /output /config /cache

# Set environment variables (can be overridden at runtime)
ENV SONARR_URL=""
ENV SONARR_API_KEY=""
ENV DAYS_PAST=7
ENV DAYS_FUTURE=30
ENV REFRESH_INTERVAL_HOURS=6
ENV OUTPUT_HTML_FILE=/output/sonarr_calendar.html
ENV OUTPUT_JSON_FILE=/output/sonarr_calendar_data.json
ENV IMAGE_CACHE_DIR=/cache

# Expose port for simple HTTP server (optional)
EXPOSE 8000

# Copy entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]