#!/bin/bash
set -e

# If configuration file does not exist, create it from environment variables
if [ ! -f /config/.sonarr_calendar_config.json ]; then
    echo "Creating configuration from environment variables..."
    python -c "
import json, os
config = {
    'sonarr_url': os.environ.get('SONARR_URL', ''),
    'sonarr_api_key': os.environ.get('SONARR_API_KEY', ''),
    'days_past': int(os.environ.get('DAYS_PAST', 7)),
    'days_future': int(os.environ.get('DAYS_FUTURE', 30)),
    'output_html_file': os.environ.get('OUTPUT_HTML_FILE', '/output/sonarr_calendar.html'),
    'output_json_file': os.environ.get('OUTPUT_JSON_FILE', '/output/sonarr_calendar_data.json'),
    'image_cache_dir': os.environ.get('IMAGE_CACHE_DIR', '/cache'),
    'refresh_interval_hours': int(os.environ.get('REFRESH_INTERVAL_HOURS', 6)),
    'html_title': 'Sonarr Calendar Pro',
    'html_theme': 'dark',
    'grid_columns': 4,
    'image_quality': 'poster',
    'image_size': '500',
    'enable_image_cache': True
}
os.makedirs('/config', exist_ok=True)
with open('/config/.sonarr_calendar_config.json', 'w') as f:
    json.dump(config, f, indent=4)
print('Configuration saved.')
"
fi

# Link the configuration file to the working directory
ln -sf /config/.sonarr_calendar_config.json /app/.sonarr_calendar_config.json

# Start the calendar tracker in the background
python /app/sonarr_calendar.py &

# Optional: start a simple HTTP server to serve the generated HTML
if [ "$ENABLE_HTTP_SERVER" = "true" ]; then
    cd /output
    python -m http.server 8000
else
    # Keep container alive
    wait
fi