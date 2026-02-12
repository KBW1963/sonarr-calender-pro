#!/usr/bin/env python3
"""
Sonarr Calendar Tracker Pro - Enhanced Version with Grid Layout and Theme Toggle
Fetches upcoming episodes from Sonarr and generates an HTML file with detailed progress tracking
Click on any show card to open its Sonarr detail page
Uses configuration from hidden .sonarr_calendar_config.json file
MINIMAL JAVASCRIPT - Only 10 lines for theme persistence
"""

import requests
import json
import os
import sys
import time
import re
from datetime import datetime, timedelta, UTC
from pathlib import Path
from urllib.parse import urljoin, quote
from collections import defaultdict

# ============================================================================
# CONFIGURATION - LOAD FROM HIDDEN CONFIG FILE
# ============================================================================

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / '.sonarr_calendar_config.json'

def load_config():
    """Load configuration from hidden file"""
    if not CONFIG_FILE.exists():
        print(f"❌ Configuration file not found: {CONFIG_FILE}")
        print("\nPlease run the configuration setup tool first:")
        print("  python sonarr_calendar_config.py")
        sys.exit(1)
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        print("\nPlease reconfigure using:")
        print("  python sonarr_calendar_config.py")
        sys.exit(1)

# Load configuration
CONFIG = load_config()

# Sonarr configuration
SONARR_URL = CONFIG['sonarr_url']
SONARR_API_KEY = CONFIG['sonarr_api_key']

# Date range configuration
DAYS_PAST = CONFIG['days_past']
DAYS_FUTURE = CONFIG['days_future']
OUTPUT_HTML_FILE = CONFIG['output_html_file']
OUTPUT_JSON_FILE = CONFIG.get('output_json_file')
IMAGE_CACHE_DIR = CONFIG.get('image_cache_dir', 'sonarr_images/')
REFRESH_INTERVAL_HOURS = CONFIG.get('refresh_interval_hours', 6)
REFRESH_INTERVAL = REFRESH_INTERVAL_HOURS * 3600

# Display configuration
IMAGE_QUALITY = CONFIG.get('image_quality', 'poster')
IMAGE_SIZE = CONFIG.get('image_size', '500')
ENABLE_IMAGE_CACHE = CONFIG.get('enable_image_cache', True)

# HTML Template configuration
HTML_TITLE = CONFIG.get('html_title', 'Sonarr Calendar Pro')
HTML_THEME = CONFIG.get('html_theme', 'dark')
GRID_COLUMNS = CONFIG.get('grid_columns', 4)

# ============================================================================
# CONSTANTS
# ============================================================================
MAX_EPISODE_TITLE_LENGTH = 25
MAX_SHOW_TITLE_LENGTH = 30
MAX_MULTI_EPISODE_DISPLAY = 2
MAX_EPISODE_LIST_LENGTH = 15

# ============================================================================
# GLOBAL VARIABLES
# ============================================================================
current_days_past = DAYS_PAST
current_days_future = DAYS_FUTURE

# ============================================================================
# FUNCTIONS
# ============================================================================

def truncate_text(text, max_length):
    """Truncate text to specified length and add ellipsis if needed"""
    if not text:
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def format_multi_episode_display(episodes_info):
    """
    Format multiple episodes on the same date for consistent display
    Returns a dictionary with formatted display strings
    """
    episode_count = len(episodes_info['episodes'])
    season_num = episodes_info['seasons'][0] if episodes_info['seasons'] else 0
    
    # Format episode range (e.g., S01E01-E05 or S01E01, E03, E05)
    if len(episodes_info['episodes']) == 1:
        episode_range = f"E{episodes_info['episodes'][0]:02d}"
    else:
        # Check if episodes are consecutive
        ep_list = sorted(episodes_info['episodes'])
        consecutive = all(ep_list[i] + 1 == ep_list[i + 1] for i in range(len(ep_list) - 1))
        
        if consecutive and len(ep_list) > 1:
            episode_range = f"E{ep_list[0]:02d}-E{ep_list[-1]:02d}"
        else:
            # Non-consecutive episodes - show first few with +X more
            if len(ep_list) > 3:
                first_few = [f"E{e:02d}" for e in ep_list[:2]]
                episode_range = f"{', '.join(first_few)} +{len(ep_list)-2} more"
            else:
                episode_range = f"{', '.join([f'E{e:02d}' for e in ep_list])}"
    
    formatted_number = f"S{season_num:02d} {episode_range}"
    
    # Format titles display
    titles = episodes_info.get('titles', [])
    truncated_titles = episodes_info.get('truncated_titles', [])
    
    if episode_count == 1:
        titles_display = truncated_titles[0] if truncated_titles else "Episode"
    else:
        # Show count and truncated list
        if episode_count <= MAX_MULTI_EPISODE_DISPLAY:
            titles_display = f"{episode_count} Episodes: {', '.join(truncated_titles[:MAX_MULTI_EPISODE_DISPLAY])}"
        else:
            titles_display = f"{episode_count} Episodes: {', '.join(truncated_titles[:MAX_MULTI_EPISODE_DISPLAY])} +{episode_count - MAX_MULTI_EPISODE_DISPLAY} more"
    
    # Truncate titles display if too long
    if len(titles_display) > MAX_EPISODE_LIST_LENGTH:
        titles_display = titles_display[:MAX_EPISODE_LIST_LENGTH-3] + "..."
    
    # Create full tooltip with all episode titles
    full_tooltip = f"Season {season_num}\n"
    for i, (ep_num, title) in enumerate(zip(episodes_info['episodes'], titles), 1):
        full_tooltip += f"E{ep_num:02d}: {title}\n"
    
    return {
        'formatted_number': formatted_number,
        'titles_display': titles_display,
        'full_tooltip': full_tooltip.strip(),
        'episode_count': episode_count
    }

def slugify(title):
    """Convert show title to Sonarr URL format (lowercase, spaces to hyphens)"""
    if not title:
        return ""
    slug = re.sub(r'[^\w\s-]', '', title)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-').lower()

def test_sonarr_connection():
    """Test connection to Sonarr API"""
    try:
        headers = {"X-Api-Key": SONARR_API_KEY}
        response = requests.get(f"{SONARR_URL}/api/v3/system/status", headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False

def fetch_sonarr_calendar():
    """Fetch calendar data from Sonarr including show information"""
    global current_days_past, current_days_future
    
    headers = {"X-Api-Key": SONARR_API_KEY}
    
    today = datetime.now(UTC)
    start_date = today - timedelta(days=DAYS_PAST)
    end_date = today + timedelta(days=DAYS_FUTURE)
    
    global_date_range = {
        'start': start_date.strftime("%Y-%m-%d"),
        'end': end_date.strftime("%Y-%m-%d"),
        'start_display': start_date.strftime("%b %d, %Y"),
        'end_display': end_date.strftime("%b %d, %Y"),
        'total_days': DAYS_PAST + DAYS_FUTURE + 1,
        'days_past': DAYS_PAST,
        'days_future': DAYS_FUTURE
    }
    
    current_days_past = DAYS_PAST
    current_days_future = DAYS_FUTURE
    
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    calendar_url = f"{SONARR_URL}/api/v3/calendar"
    params = {
        "start": start_date_str,
        "end": end_date_str,
        "includeSeries": "true",
        "includeEpisodeFile": "true",
        "includeEpisodeImages": "true",
        "unmonitored": "true"
    }
    
    try:
        response = requests.get(calendar_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        calendar_data = response.json()
        return calendar_data, global_date_range
    except requests.exceptions.RequestException as e:
        print(f"Error fetching calendar: {e}")
        return [], global_date_range

def fetch_all_series():
    """Fetch all series from Sonarr to get poster URLs and detailed information"""
    headers = {"X-Api-Key": SONARR_API_KEY}
    series_url = f"{SONARR_URL}/api/v3/series"
    
    try:
        response = requests.get(series_url, headers=headers, timeout=30)
        response.raise_for_status()
        series_data = response.json()
        
        series_dict = {}
        for series in series_data:
            series_dict[series['id']] = {
                'title': series['title'],
                'year': series.get('year', ''),
                'overview': series.get('overview', ''),
                'status': series.get('status', ''),
                'network': series.get('network', ''),
                'runtime': series.get('runtime', 0),
                'genres': series.get('genres', []),
                'ratings': series.get('ratings', {}),
                'images': series.get('images', []),
                'remotePoster': series.get('remotePoster', ''),
                'seasons': series.get('seasons', []),
                'seasonCount': series.get('seasonCount', 0),
                'episodeFileCount': series.get('episodeFileCount', 0),
                'episodeCount': series.get('episodeCount', 0),
                'totalEpisodeCount': series.get('totalEpisodeCount', 0),
                'sizeOnDisk': series.get('sizeOnDisk', 0)
            }
        return series_dict
    except Exception as e:
        print(f"Error fetching series: {e}")
        return {}

def fetch_series_details(series_id):
    """Fetch detailed information for a specific series including episodes"""
    headers = {"X-Api-Key": SONARR_API_KEY}
    series_url = f"{SONARR_URL}/api/v3/series/{series_id}"
    
    try:
        response = requests.get(series_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching series {series_id} details: {e}")
        return {}

def fetch_series_episodes(series_id):
    """Fetch all episodes for a series"""
    headers = {"X-Api-Key": SONARR_API_KEY}
    episodes_url = f"{SONARR_URL}/api/v3/episode"
    params = {"seriesId": series_id}
    
    try:
        response = requests.get(episodes_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching episodes for series {series_id}: {e}")
        return []

def get_poster_url(series_info, image_size="500"):
    """Extract poster URL from series information"""
    if not series_info:
        return None
    
    remote_poster = series_info.get('remotePoster', '')
    if remote_poster:
        if 'thetvdb.com' in remote_poster and image_size:
            return remote_poster.replace('/banners/', f'/banners/_cache/')
        return remote_poster
    
    images = series_info.get('images', [])
    for image in images:
        if image.get('coverType') == 'poster':
            url = image.get('url', '')
            if url:
                if url.startswith('/'):
                    return urljoin(SONARR_URL, url)
                return url
    
    return None

def cache_image(image_url, series_id, image_type="poster"):
    """Download and cache an image locally"""
    if not image_url or not ENABLE_IMAGE_CACHE:
        return None
    
    os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
    
    filename = f"{series_id}_{image_type}.jpg"
    cache_path = os.path.join(IMAGE_CACHE_DIR, filename)
    
    if os.path.exists(cache_path):
        file_age = time.time() - os.path.getmtime(cache_path)
        if file_age < 7 * 24 * 3600:
            return f"{os.path.basename(IMAGE_CACHE_DIR)}/{filename}"
    
    try:
        headers = {"X-Api-Key": SONARR_API_KEY} if SONARR_URL in image_url else {}
        response = requests.get(image_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            with open(cache_path, 'wb') as f:
                f.write(response.content)
            return f"{os.path.basename(IMAGE_CACHE_DIR)}/{filename}"
        else:
            print(f"Failed to download image: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error caching image: {e}")
        return None

def calculate_series_progress(series_info, series_details):
    """Calculate progress for a series including unmonitored seasons"""
    if not series_info or not series_details:
        return {
            'total_episodes': 0,
            'downloaded_episodes': 0,
            'percentage': 0,
            'status': 'unknown',
            'unmonitored_seasons': 0,
            'monitored_seasons': 0,
            'total_seasons': 0,
            'season_progress': [],
            'current_season': 0,
            'current_season_progress': 0,
            'current_season_complete': False,
            'current_season_episodes': 0,
            'current_season_downloaded': 0
        }
    
    seasons = series_details.get('seasons', [])
    total_episodes = 0
    downloaded_episodes = 0
    unmonitored_seasons = 0
    monitored_seasons = 0
    total_seasons = 0
    season_progress = []
    current_season = 0
    current_season_progress = 0
    current_season_complete = False
    current_season_episodes = 0
    current_season_downloaded = 0
    
    for season in seasons:
        season_number = season.get('seasonNumber', 0)
        if season_number < 0:
            continue
            
        if season_number > current_season:
            statistics = season.get('statistics', {})
            if statistics.get('totalEpisodeCount', 0) > 0:
                current_season = season_number
    
    for season in seasons:
        season_number = season.get('seasonNumber', 0)
        if season_number < 0:
            continue
            
        total_seasons += 1
        monitored = season.get('monitored', False)
        statistics = season.get('statistics', {})
        
        season_total = statistics.get('totalEpisodeCount', 0)
        season_downloaded = statistics.get('episodeFileCount', 0)
        
        total_episodes += season_total
        downloaded_episodes += season_downloaded
        
        if not monitored:
            unmonitored_seasons += 1
            downloaded_episodes += season_total
            season_downloaded = season_total
        else:
            monitored_seasons += 1
        
        season_percentage = 0
        if season_total > 0:
            season_percentage = min(100, (season_downloaded / season_total) * 100)
        
        if season_number == current_season:
            current_season_progress = season_percentage
            current_season_episodes = season_total
            current_season_downloaded = season_downloaded
            current_season_complete = season_percentage >= 100
        
        season_progress.append({
            'season': season_number,
            'monitored': monitored,
            'total': season_total,
            'downloaded': season_downloaded,
            'percentage': season_percentage,
            'complete': season_percentage >= 100
        })
    
    percentage = 0
    if total_episodes > 0:
        percentage = min(100, (downloaded_episodes / total_episodes) * 100)
    
    if percentage >= 100:
        status = 'complete'
    elif percentage >= 75:
        status = 'almost-complete'
    elif percentage >= 50:
        status = 'halfway'
    elif percentage >= 25:
        status = 'started'
    elif percentage > 0:
        status = 'just-started'
    else:
        status = 'not-started'
    
    return {
        'total_episodes': total_episodes,
        'downloaded_episodes': downloaded_episodes,
        'percentage': percentage,
        'status': status,
        'unmonitored_seasons': unmonitored_seasons,
        'monitored_seasons': monitored_seasons,
        'total_seasons': total_seasons,
        'season_progress': season_progress,
        'current_season': current_season,
        'current_season_progress': current_season_progress,
        'current_season_complete': current_season_complete,
        'current_season_episodes': current_season_episodes,
        'current_season_downloaded': current_season_downloaded
    }

def calculate_show_date_range_progress(series_id, episodes_data, date_range_start, date_range_end):
    """Calculate how many episodes for this show are in the date range and how many are downloaded"""
    try:
        start_date = datetime.strptime(date_range_start, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_range_end, "%Y-%m-%d").date()
        
        episodes_in_range = 0
        episodes_downloaded_in_range = 0
        
        for episode in episodes_data:
            if episode.get('seriesId') != series_id:
                continue
                
            air_date_str = episode.get('airDate')
            if not air_date_str:
                continue
                
            try:
                air_date = datetime.strptime(air_date_str, "%Y-%m-%d").date()
                if start_date <= air_date <= end_date:
                    episodes_in_range += 1
                    if episode.get('hasFile', False):
                        episodes_downloaded_in_range += 1
            except:
                continue
        
        percentage = 0
        if episodes_in_range > 0:
            percentage = min(100, (episodes_downloaded_in_range / episodes_in_range) * 100)
        
        return {
            'episodes_in_range': episodes_in_range,
            'downloaded_in_range': episodes_downloaded_in_range,
            'percentage': percentage,
            'color': get_progress_bar_color(percentage)
        }
    except Exception as e:
        print(f"Error calculating date range progress for series {series_id}: {e}")
        return {
            'episodes_in_range': 0,
            'downloaded_in_range': 0,
            'percentage': 0,
            'color': get_progress_bar_color(0)
        }

def calculate_completed_seasons_in_range(shows, calendar_data, date_range_start, date_range_end):
    """Calculate which shows have completed their current season within the date range"""
    try:
        start_date = datetime.strptime(date_range_start, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_range_end, "%Y-%m-%d").date()
        
        completed_season_shows = []
        
        for show in shows:
            series_id = show['series_id']
            current_season = show['current_season']
            current_season_complete = show['current_season_complete']
            
            if not current_season_complete:
                continue
            
            season_episodes = []
            for episode in calendar_data:
                if (episode.get('seriesId') == series_id and 
                    episode.get('seasonNumber') == current_season):
                    
                    air_date_str = episode.get('airDate')
                    if air_date_str:
                        try:
                            air_date = datetime.strptime(air_date_str, "%Y-%m-%d").date()
                            season_episodes.append({
                                'air_date': air_date,
                                'episode_number': episode.get('episodeNumber', 0)
                            })
                        except:
                            continue
            
            if season_episodes:
                latest_episode = max(season_episodes, key=lambda x: (x['air_date'], x['episode_number']))
                
                if start_date <= latest_episode['air_date'] <= end_date:
                    completed_season_shows.append({
                        'title': show['show_title'],
                        'series_id': series_id,
                        'season': current_season,
                        'completion_date': latest_episode['air_date'].strftime("%b %d, %Y"),
                        'total_episodes': show['current_season_episodes'],
                        'poster_url': show['poster_url']
                    })
        
        completed_season_shows.sort(key=lambda x: x['completion_date'], reverse=True)
        return completed_season_shows[:10]
        
    except Exception as e:
        print(f"Error calculating completed seasons: {e}")
        return []

def get_progress_bar_color(percentage):
    """Get color for progress bar based on percentage"""
    if percentage >= 100:
        return "#4CAF50"
    elif percentage >= 75:
        return "#8BC34A"
    elif percentage >= 50:
        return "#FFC107"
    elif percentage >= 25:
        return "#FF9800"
    elif percentage > 0:
        return "#FF5722"
    else:
        return "#F44336"

def group_episodes_by_show_and_date(calendar_data):
    """Group episodes by series and air date to consolidate multi-episode releases"""
    grouped = defaultdict(lambda: defaultdict(list))
    
    for episode in calendar_data:
        series_id = episode.get('seriesId')
        air_date = episode.get('airDate', '')
        
        if series_id and air_date:
            grouped[series_id][air_date].append(episode)
    
    return grouped

def process_calendar_data(calendar_data, series_info, date_range_start, date_range_end):
    """Process calendar data and enrich with show titles and poster URLs"""
    grouped_episodes = group_episodes_by_show_and_date(calendar_data)
    processed_shows = []
    
    for series_id, date_episodes in grouped_episodes.items():
        try:
            series_details = series_info.get(series_id, {})
            
            show_title = series_details.get('title', 'Unknown Show')
            truncated_show_title = truncate_text(show_title, MAX_SHOW_TITLE_LENGTH)
            
            poster_url = get_poster_url(series_details, IMAGE_SIZE)
            
            cached_image = None
            if poster_url and ENABLE_IMAGE_CACHE:
                cached_image = cache_image(poster_url, series_id, "poster")
            
            series_full_details = fetch_series_details(series_id)
            progress_info = calculate_series_progress(series_details, series_full_details)
            
            date_range_progress = calculate_show_date_range_progress(
                series_id, calendar_data, date_range_start, date_range_end
            )
            
            show_episodes = []
            for air_date, episodes in date_episodes.items():
                episodes.sort(key=lambda x: (x.get('seasonNumber', 0), x.get('episodeNumber', 0)))
                
                if len(episodes) == 1:
                    ep = episodes[0]
                    episode_title = ep.get('title', 'TBA')
                    truncated_episode_title = truncate_text(episode_title, MAX_EPISODE_TITLE_LENGTH)
                    
                    episode_info = {
                        'single_episode': True,
                        'title': episode_title,
                        'truncated_title': truncated_episode_title,
                        'full_title': episode_title,
                        'season': ep.get('seasonNumber', 0),
                        'episode': ep.get('episodeNumber', 0),
                        'has_file': ep.get('hasFile', False),
                        'monitored': ep.get('monitored', False),
                        'overview': ep.get('overview', ''),
                        'formatted_season_episode': f"S{ep.get('seasonNumber', 0):02d}E{ep.get('episodeNumber', 0):02d}"
                    }
                else:
                    titles = [ep.get('title', 'TBA') for ep in episodes]
                    truncated_titles = [truncate_text(title, MAX_EPISODE_TITLE_LENGTH) for title in titles]
                    
                    episodes_info = {
                        'titles': titles,
                        'truncated_titles': truncated_titles,
                        'seasons': list(set(ep.get('seasonNumber', 0) for ep in episodes)),
                        'episodes': [ep.get('episodeNumber', 0) for ep in episodes],
                        'episode_count': len(episodes)
                    }
                    
                    formatted_display = format_multi_episode_display(episodes_info)
                    
                    episode_info = {
                        'single_episode': False,
                        'titles': titles,
                        'truncated_titles': truncated_titles,
                        'full_titles': titles,
                        'seasons': episodes_info['seasons'],
                        'episodes': episodes_info['episodes'],
                        'has_file': all(ep.get('hasFile', False) for ep in episodes),
                        'monitored': any(ep.get('monitored', False) for ep in episodes),
                        'overview': episodes[0].get('overview', ''),
                        'formatted_season_episode': formatted_display['formatted_number'],
                        'titles_display': formatted_display['titles_display'],
                        'full_tooltip': formatted_display['full_tooltip'],
                        'episode_count': len(episodes)
                    }
                
                episode_info['air_date'] = air_date
                episode_info['formatted_date'] = format_air_date(air_date)
                episode_info['days_until'] = calculate_days_until(
                    episodes[0].get('airDateUtc', '') if episodes else ''
                )
                
                show_episodes.append(episode_info)
            
            show_episodes.sort(key=lambda x: x.get('air_date', ''))
            
            show_info = {
                'series_id': series_id,
                'show_title': show_title,
                'truncated_show_title': truncated_show_title,
                'show_title_slug': slugify(show_title),
                'show_year': series_details.get('year', ''),
                'show_status': series_details.get('status', ''),
                'show_network': series_details.get('network', ''),
                'show_runtime': series_details.get('runtime', 0),
                'show_genres': series_details.get('genres', []),
                'show_rating': series_details.get('ratings', {}).get('value', 0),
                'poster_url': cached_image or poster_url or '',
                'has_poster': bool(poster_url),
                'progress_percentage': progress_info['percentage'],
                'progress_status': progress_info['status'],
                'progress_color': get_progress_bar_color(progress_info['percentage']),
                'total_episodes': progress_info['total_episodes'],
                'downloaded_episodes': progress_info['downloaded_episodes'],
                'unmonitored_seasons': progress_info['unmonitored_seasons'],
                'monitored_seasons': progress_info['monitored_seasons'],
                'total_seasons': progress_info['total_seasons'],
                'current_season': progress_info['current_season'],
                'current_season_progress': progress_info['current_season_progress'],
                'current_season_complete': progress_info['current_season_complete'],
                'current_season_episodes': progress_info['current_season_episodes'],
                'current_season_downloaded': progress_info['current_season_downloaded'],
                'date_range_episodes': date_range_progress['episodes_in_range'],
                'date_range_downloaded': date_range_progress['downloaded_in_range'],
                'date_range_percentage': date_range_progress['percentage'],
                'date_range_color': date_range_progress['color'],
                'episodes': show_episodes
            }
            
            processed_shows.append(show_info)
            
        except Exception as e:
            print(f"Error processing show {series_id}: {e}")
            continue
    
    processed_shows.sort(key=lambda x: (-x['date_range_percentage'], x['show_title']))
    return processed_shows

def format_air_date(air_date_str):
    """Format air date for display"""
    try:
        date_obj = datetime.strptime(air_date_str, "%Y-%m-%d")
        return date_obj.strftime("%a, %b %d")
    except:
        return air_date_str

def calculate_days_until(air_date_utc_str):
    """Calculate days until air date"""
    try:
        air_date = datetime.strptime(air_date_utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta = air_date - now
        return delta.days
    except:
        return 0

def calculate_overall_statistics(shows, date_range):
    """Calculate overall statistics across all series"""
    total_series = len(shows)
    
    total_progress = sum(show['progress_percentage'] for show in shows)
    total_date_range_progress = sum(show['date_range_percentage'] for show in shows)
    total_episodes_all = sum(show['total_episodes'] for show in shows)
    total_downloaded_all = sum(show['downloaded_episodes'] for show in shows)
    total_seasons_all = sum(show['total_seasons'] for show in shows)
    total_monitored_seasons_all = sum(show['monitored_seasons'] for show in shows)
    total_unmonitored_seasons_all = sum(show['unmonitored_seasons'] for show in shows)
    
    total_episodes_in_range = sum(show['date_range_episodes'] for show in shows)
    total_downloaded_in_range = sum(show['date_range_downloaded'] for show in shows)
    
    shows_with_episodes = sum(1 for show in shows if show['date_range_episodes'] > 0)
    completed_current_seasons = sum(1 for show in shows if show['current_season_complete'])
    
    avg_progress = total_progress / total_series if total_series > 0 else 0
    avg_date_range_progress = total_date_range_progress / total_series if total_series > 0 else 0
    overall_progress = (total_downloaded_all / total_episodes_all * 100) if total_episodes_all > 0 else 0
    overall_date_range_progress = (total_downloaded_in_range / total_episodes_in_range * 100) if total_episodes_in_range > 0 else 0
    
    shows_complete = sum(1 for show in shows if show['progress_percentage'] >= 100)
    shows_high_progress = sum(1 for show in shows if 75 <= show['progress_percentage'] < 100)
    shows_medium_progress = sum(1 for show in shows if 25 <= show['progress_percentage'] < 75)
    shows_low_progress = sum(1 for show in shows if 0 < show['progress_percentage'] < 25)
    shows_not_started = sum(1 for show in shows if show['progress_percentage'] == 0)
    
    shows_date_range_complete = sum(1 for show in shows if show['date_range_percentage'] >= 100)
    shows_date_range_high = sum(1 for show in shows if 75 <= show['date_range_percentage'] < 100)
    shows_date_range_medium = sum(1 for show in shows if 25 <= show['date_range_percentage'] < 75)
    shows_date_range_low = sum(1 for show in shows if 0 < show['date_range_percentage'] < 25)
    shows_date_range_none = sum(1 for show in shows if show['date_range_percentage'] == 0)
    
    return {
        'date_range': date_range,
        'total_series': total_series,
        'avg_progress': avg_progress,
        'avg_date_range_progress': avg_date_range_progress,
        'overall_progress': overall_progress,
        'overall_date_range_progress': overall_date_range_progress,
        'total_episodes_all': total_episodes_all,
        'total_downloaded_all': total_downloaded_all,
        'total_seasons_all': total_seasons_all,
        'total_monitored_seasons': total_monitored_seasons_all,
        'total_unmonitored_seasons': total_unmonitored_seasons_all,
        'episodes_in_range': total_episodes_in_range,
        'downloaded_in_range': total_downloaded_in_range,
        'shows_with_episodes': shows_with_episodes,
        'completed_current_seasons': completed_current_seasons,
        'shows_complete': shows_complete,
        'shows_high_progress': shows_high_progress,
        'shows_medium_progress': shows_medium_progress,
        'shows_low_progress': shows_low_progress,
        'shows_not_started': shows_not_started,
        'shows_date_range_complete': shows_date_range_complete,
        'shows_date_range_high': shows_date_range_high,
        'shows_date_range_medium': shows_date_range_medium,
        'shows_date_range_low': shows_date_range_low,
        'shows_date_range_none': shows_date_range_none
    }

def generate_html_file(shows, overall_stats, calendar_data):
    """Generate a complete HTML file with the calendar data and progress bars"""
    completed_seasons = calculate_completed_seasons_in_range(
        shows, calendar_data, overall_stats['date_range']['start'], overall_stats['date_range']['end']
    )
    
    # Generate show filter dropdown options with anchor links
    show_filter_options = '<option value="#all" selected>All Shows</option>'
    for show in sorted(shows, key=lambda x: x['show_title']):
        show_filter_options += f'<option value="#show-{show["series_id"]}">{show["truncated_show_title"]}</option>'
    
    shows_html = ""
    for show in shows:
        sonarr_detail_url = f"{SONARR_URL}/series/{show['show_title_slug']}"
        
        genres_html = ""
        for genre in show['show_genres'][:3]:
            genres_html += f'<span class="genre-tag">{genre}</span>'
        
        poster_html = ""
        if show['poster_url']:
            poster_html = f'''
            <div class="poster-container">
                <img src="{show["poster_url"]}" alt="{show["show_title"]}" class="card-poster" loading="lazy">
            </div>
            '''
        else:
            poster_html = f'''
            <div class="poster-container">
                <div class="poster-placeholder" style="background: {show['progress_color']}">
                    <span class="placeholder-icon">🎬</span>
                    <div class="placeholder-title">{show['truncated_show_title']}</div>
                </div>
            </div>
            '''
        
        episodes_html = ""
        if show['episodes']:
            for episode in show['episodes']:
                if episode['has_file']:
                    status_class = "status-downloaded"
                elif episode.get('monitored', False):
                    status_class = "status-monitored"
                else:
                    status_class = "status-missing"
                
                days = episode['days_until']
                if days == 0:
                    days_text = "Today"
                    days_class = "days-today"
                elif days == 1:
                    days_text = "Tomorrow"
                    days_class = "days-tomorrow"
                elif days > 0:
                    days_text = f"In {days} days"
                    days_class = "days-future"
                elif days == -1:
                    days_text = "Yesterday"
                    days_class = "days-yesterday"
                else:
                    days_text = f"{abs(days)} days ago"
                    days_class = "days-past"
                
                if episode['single_episode']:
                    episodes_html += f'''
                    <div class="episode-item {status_class}" title="{episode['full_title']}">
                        <div class="episode-header">
                            <span class="episode-number">{episode['formatted_season_episode']}</span>
                            <span class="episode-date">{episode['formatted_date']}</span>
                            <span class="episode-days {days_class}">{days_text}</span>
                        </div>
                        <div class="episode-title">{episode['truncated_title']}</div>
                    </div>
                    '''
                else:
                    episodes_html += f'''
                    <div class="episode-item {status_class} episode-multiple" title="{episode['full_tooltip']}">
                        <div class="episode-header">
                            <span class="episode-number">{episode['formatted_season_episode']}</span>
                            <span class="episode-date">{episode['formatted_date']}</span>
                            <span class="episode-days {days_class}">{days_text}</span>
                        </div>
                        <div class="episode-titles">
                            {episode['titles_display']}
                        </div>
                    </div>
                    '''
        else:
            episodes_html = '<div class="no-episodes">No episodes in date range</div>'
        
        season_badge = ""
        if show['current_season_complete']:
            season_badge = f'<span class="season-complete-badge-inline" title="Season {show["current_season"]} Complete">✓</span>'
        
        # Add anchor ID for filtering
        shows_html += f'''
        <div id="show-{show['series_id']}" class="show-card-wrapper">
            <a href="{sonarr_detail_url}" target="_blank" class="show-card-link">
                <div class="show-card" data-progress="{show['progress_percentage']}" data-date-range-progress="{show['date_range_percentage']}">
                    <div class="card-header">
                        {poster_html}
                        <div class="show-badge" title="Current Season">S{show['current_season']:02d}</div>
                        <div class="status-overall" style="background: {show['progress_color']}" 
                             title="Overall Progress: {show['progress_percentage']:.1f}%"></div>
                    </div>
                    <div class="card-content">
                        <div class="title-container">
                            <h3 class="show-title" title="{show['show_title']}">{show['truncated_show_title']}</h3>
                            {season_badge}
                        </div>
                        <div class="show-meta">
                            {show['show_year'] if show['show_year'] else ''}
                            {(' • ' + show['show_network']) if show['show_network'] else ''}
                            {(' • ' + str(show['show_runtime']) + ' min') if show['show_runtime'] else ''}
                            {(' • ⭐ ' + str(round(show['show_rating'], 1))) if show['show_rating'] > 0 else ''}
                        </div>
                        
                        <div class="episodes-section">
                            <div class="section-title">Episodes in Date Range</div>
                            <div class="episodes-list">
                                {episodes_html}
                            </div>
                        </div>
                        
                        <div class="progress-section">
                            <div class="progress-item">
                                <div class="progress-header">
                                    <span>Overall Progress</span>
                                    <span class="progress-percentage">{show['progress_percentage']:.1f}%</span>
                                </div>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: {show['progress_percentage']}%; background: {show['progress_color']};"></div>
                                </div>
                                <div class="progress-stats">
                                    {show['downloaded_episodes']}/{show['total_episodes']} episodes • 
                                    Season {show['current_season']}: {show['current_season_progress']:.0f}%
                                </div>
                            </div>
                            
                            <div class="progress-item">
                                <div class="progress-header">
                                    <span>Date Range Progress</span>
                                    <span class="progress-percentage">{show['date_range_percentage']:.1f}%</span>
                                </div>
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: {show['date_range_percentage']}%; background: {show['date_range_color']};"></div>
                                </div>
                                <div class="progress-stats">
                                    {show['date_range_downloaded']}/{show['date_range_episodes']} episodes in date range
                                </div>
                            </div>
                        </div>
                        
                        {('<div class="genres">' + genres_html + '</div>') if genres_html else ''}
                        
                        <div class="show-footer">
                            <div class="season-info">
                                <span class="seasons-count">{show['total_seasons']} seasons</span>
                                <span class="monitored-count">{show['monitored_seasons']} monitored</span>
                                <span class="unmonitored-count">{show['unmonitored_seasons']} unmonitored*</span>
                            </div>
                        </div>
                    </div>
                </div>
            </a>
        </div>
        '''
    
    completed_seasons_html = ""
    if completed_seasons:
        for show in completed_seasons[:6]:
            sonarr_detail_url = f"{SONARR_URL}/series/{slugify(show['title'])}"
            truncated_title = truncate_text(show['title'], MAX_SHOW_TITLE_LENGTH)
            completed_seasons_html += f'''
            <a href="{sonarr_detail_url}" target="_blank" class="completed-season-link">
                <div class="completed-season-item">
                    <div class="completed-season-poster">
                        {f'<img src="{show["poster_url"]}" alt="{show["title"]}" loading="lazy" class="completed-season-img">' if show['poster_url'] else '<div class="poster-placeholder-small">🎬</div>'}
                    </div>
                    <div class="completed-season-info">
                        <div class="completed-season-title" title="{show['title']}">{truncated_title}</div>
                        <div class="completed-season-details">Season {show['season']} • {show['total_episodes']} episodes</div>
                        <div class="completed-season-date">Completed: {show['completion_date']}</div>
                    </div>
                </div>
            </a>
            '''
    else:
        completed_seasons_html = '<div class="no-completed-seasons">No seasons completed in date range</div>'
    
    html_template = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{HTML_TITLE}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary-color: #00b4db;
            --primary-dark: #0083b0;
            --secondary-color: #1a1a2e;
            --background-color: #0f0f1e;
            --card-bg: #1a1a2e;
            --text-color: #ffffff;
            --text-secondary: #aaaaaa;
            --border-color: #2d2d4d;
            --shadow-color: rgba(0,0,0,0.3);
            --progress-complete: #4CAF50;
            --progress-almost: #8BC34A;
            --progress-halfway: #FFC107;
            --progress-started: #FF9800;
            --progress-just-started: #FF5722;
            --progress-not-started: #F44336;
        }}
        
        .theme-light {{
            --secondary-color: #f8f9fa;
            --background-color: #ffffff;
            --card-bg: #ffffff;
            --text-color: #333333;
            --text-secondary: #666666;
            --border-color: #e0e0e0;
            --shadow-color: rgba(0,0,0,0.1);
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        html {{
            scroll-behavior: smooth;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--background-color);
            color: var(--text-color);
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
            transition: background-color 0.3s ease, color 0.3s ease;
        }}
        
        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}
        
        .header-top {{
            display: flex;
            justify-content: flex-end;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }}
        
        .theme-toggle {{
            background: var(--card-bg);
            border: 2px solid var(--border-color);
            color: var(--text-color);
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
            text-decoration: none;
            cursor: pointer;
        }}
        
        .theme-toggle:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px var(--shadow-color);
        }}
        
        /* Show Filter Dropdown */
        .filter-dropdown {{
            display: flex;
            align-items: center;
            gap: 10px;
            background: var(--card-bg);
            padding: 5px 15px;
            border-radius: 20px;
            border: 2px solid var(--border-color);
        }}
        
        .filter-dropdown i {{
            color: var(--primary-color);
        }}
        
        .show-filter {{
            background: var(--background-color);
            color: var(--text-color);
            border: 1px solid var(--border-color);
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 0.95em;
            cursor: pointer;
            outline: none;
            min-width: 200px;
        }}
        
        .show-filter:hover {{
            border-color: var(--primary-color);
        }}
        
        /* CSS-only Return to Top Button */
        .return-to-top {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--primary-color);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
            box-shadow: 0 4px 15px rgba(0, 180, 219, 0.3);
            transition: all 0.3s ease;
            z-index: 1000;
            border: 2px solid var(--border-color);
            text-decoration: none;
            opacity: 0.9;
        }}
        
        .return-to-top:hover {{
            background: var(--primary-dark);
            transform: translateY(-5px);
            box-shadow: 0 6px 20px rgba(0, 180, 219, 0.4);
            opacity: 1;
        }}
        
        header {{
            margin-bottom: 40px;
            padding: 30px;
            background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
            border-radius: 15px;
            color: white;
            box-shadow: 0 10px 30px var(--shadow-color);
        }}
        
        h1 {{
            font-size: 2.8em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }}
        
        .date-range {{
            text-align: center;
            font-size: 1.4em;
            margin-bottom: 20px;
            background: rgba(255, 255, 255, 0.1);
            padding: 10px 20px;
            border-radius: 10px;
            display: inline-block;
            margin: 0 auto 20px;
            backdrop-filter: blur(10px);
        }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            grid-template-rows: repeat(2, auto);
            gap: 15px;
            margin-bottom: 30px;
        }}
        
        @media (max-width: 1200px) {{
            .summary-grid {{
                grid-template-columns: repeat(2, 1fr);
                grid-template-rows: repeat(4, auto);
            }}
        }}
        
        @media (max-width: 600px) {{
            .summary-grid {{
                grid-template-columns: 1fr;
                grid-template-rows: repeat(8, auto);
            }}
        }}
        
        .summary-card {{
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s ease;
        }}
        
        .summary-card:hover {{
            transform: translateY(-5px);
        }}
        
        .summary-number {{
            font-size: 2.2em;
            font-weight: bold;
            margin-bottom: 8px;
        }}
        
        .summary-label {{
            font-size: 0.95em;
            opacity: 0.9;
            margin-bottom: 5px;
        }}
        
        .summary-subtext {{
            font-size: 0.85em;
            opacity: 0.7;
        }}
        
        .completed-seasons-section {{
            background: rgba(255, 255, 255, 0.05);
            padding: 25px;
            border-radius: 15px;
            margin: 30px 0;
            border: 1px solid var(--border-color);
        }}
        
        .section-title {{
            font-size: 1.4em;
            font-weight: 600;
            margin-bottom: 20px;
            color: var(--primary-color);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .completed-seasons-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        
        .show-card-wrapper {{
            display: block;
            scroll-margin-top: 20px;
        }}
        
        .show-card-link {{
            text-decoration: none;
            color: inherit;
            display: block;
        }}
        
        .completed-season-link {{
            text-decoration: none;
            color: inherit;
            display: block;
        }}
        
        .completed-season-item {{
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 15px;
            background: var(--card-bg);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            transition: transform 0.3s ease;
            cursor: pointer;
        }}
        
        .completed-season-item:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 20px var(--shadow-color);
            border-color: var(--primary-color);
        }}
        
        .completed-season-poster {{
            width: 60px;
            height: 90px;
            border-radius: 5px;
            overflow: hidden;
            flex-shrink: 0;
            background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .completed-season-img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        
        .poster-placeholder-small {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5em;
            color: white;
        }}
        
        .completed-season-info {{
            flex-grow: 1;
        }}
        
        .completed-season-title {{
            font-weight: 600;
            margin-bottom: 5px;
            font-size: 1.1em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .completed-season-details {{
            font-size: 0.9em;
            color: var(--text-secondary);
            margin-bottom: 5px;
        }}
        
        .completed-season-date {{
            font-size: 0.85em;
            color: var(--progress-complete);
            font-weight: 500;
        }}
        
        .no-completed-seasons {{
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
            font-style: italic;
            grid-column: 1 / -1;
        }}
        
        .overall-progress-section {{
            margin: 30px 0;
        }}
        
        .stat-progress {{
            background: rgba(255, 255, 255, 0.05);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 15px;
            border: 1px solid var(--border-color);
        }}
        
        .stat-progress-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-weight: 600;
        }}
        
        .stat-progress-bar {{
            height: 20px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 8px;
        }}
        
        .stat-progress-fill {{
            height: 100%;
            border-radius: 10px;
            transition: width 1s ease-in-out;
        }}
        
        .stat-progress-stats {{
            font-size: 0.9em;
            color: var(--text-secondary);
        }}
        
        /* Original Filter Buttons - RESTORED */
        .filters {{
            display: flex;
            justify-content: center;
            gap: 12px;
            margin: 25px 0;
            flex-wrap: wrap;
        }}
        
        .filter-btn {{
            padding: 8px 16px;
            border: none;
            background: var(--card-bg);
            color: var(--text-color);
            border-radius: 20px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            border: 2px solid var(--border-color);
            font-size: 0.9em;
            text-decoration: none;
            display: inline-block;
        }}
        
        .filter-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px var(--shadow-color);
        }}
        
        .filter-btn.active {{
            background: var(--primary-color);
            color: white;
            border-color: var(--primary-color);
        }}
        
        /* CSS-only filter: hide/show based on radio buttons */
        .filter-radio {{
            display: none;
        }}
        
        #filter-all:checked ~ .shows-grid .show-card-wrapper {{
            display: block;
        }}
        
        #filter-complete:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress] {{
            display: none;
        }}
        #filter-complete:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress="100"] {{
            display: flex;
        }}
        
        #filter-high-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress] {{
            display: none;
        }}
        #filter-high-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="7"],
        #filter-high-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="8"],
        #filter-high-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="9"] {{
            display: flex;
        }}
        
        #filter-medium-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress] {{
            display: none;
        }}
        #filter-medium-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="2"],
        #filter-medium-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="3"],
        #filter-medium-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="4"],
        #filter-medium-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="5"],
        #filter-medium-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="6"] {{
            display: flex;
        }}
        
        #filter-low-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress] {{
            display: none;
        }}
        #filter-low-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="1"],
        #filter-low-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="2"],
        #filter-low-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="3"],
        #filter-low-progress:checked ~ .shows-grid .show-card-wrapper .show-card[data-progress^="4"] {{
            display: flex;
        }}
        
        #filter-date-range-high:checked ~ .shows-grid .show-card-wrapper .show-card[data-date-range-progress] {{
            display: none;
        }}
        #filter-date-range-high:checked ~ .shows-grid .show-card-wrapper .show-card[data-date-range-progress^="7"],
        #filter-date-range-high:checked ~ .shows-grid .show-card-wrapper .show-card[data-date-range-progress^="8"],
        #filter-date-range-high:checked ~ .shows-grid .show-card-wrapper .show-card[data-date-range-progress^="9"] {{
            display: flex;
        }}
        
        #filter-date-range-low:checked ~ .shows-grid .show-card-wrapper .show-card[data-date-range-progress] {{
            display: none;
        }}
        #filter-date-range-low:checked ~ .shows-grid .show-card-wrapper .show-card[data-date-range-progress^="1"],
        #filter-date-range-low:checked ~ .shows-grid .show-card-wrapper .show-card[data-date-range-progress^="2"] {{
            display: flex;
        }}
        
        #filter-has-episodes:checked ~ .shows-grid .show-card-wrapper .show-card {{
            display: none;
        }}
        #filter-has-episodes:checked ~ .shows-grid .show-card-wrapper:has(.episode-item) {{
            display: block;
        }}
        
        .shows-grid {{
            display: grid;
            grid-template-columns: repeat({GRID_COLUMNS}, 1fr);
            gap: 25px;
            margin-bottom: 40px;
        }}
        
        @media (max-width: 1400px) {{
            .shows-grid {{
                grid-template-columns: repeat(3, 1fr);
            }}
        }}
        
        @media (max-width: 1000px) {{
            .shows-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        @media (max-width: 700px) {{
            .shows-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .show-card {{
            background: var(--card-bg);
            border-radius: 15px;
            overflow: hidden;
            transition: all 0.3s ease;
            border: 1px solid var(--border-color);
            box-shadow: 0 5px 15px var(--shadow-color);
            display: flex;
            flex-direction: column;
            height: 100%;
        }}
        
        .show-card-link:hover .show-card {{
            transform: translateY(-10px);
            box-shadow: 0 15px 35px var(--shadow-color);
            border-color: var(--primary-color);
        }}
        
        .card-header {{
            position: relative;
            height: 250px;
            overflow: hidden;
            flex-shrink: 0;
            background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
        }}
        
        .poster-container {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
        }}
        
        .card-poster {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            object-position: center;
            background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
            transition: transform 0.5s ease;
        }}
        
        .show-card-link:hover .card-poster {{
            transform: scale(1.05);
        }}
        
        .poster-placeholder {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: white;
            padding: 20px;
            text-align: center;
        }}
        
        .placeholder-icon {{
            font-size: 4em;
            margin-bottom: 15px;
        }}
        
        .placeholder-title {{
            font-size: 1.2em;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 90%;
        }}
        
        .show-badge {{
            position: absolute;
            top: 15px;
            right: 15px;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 6px 12px;
            border-radius: 15px;
            font-weight: bold;
            font-size: 0.9em;
            backdrop-filter: blur(5px);
            z-index: 10;
        }}
        
        .status-overall {{
            position: absolute;
            top: 15px;
            left: 15px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            box-shadow: 0 0 10px currentColor;
            z-index: 10;
        }}
        
        .card-content {{
            padding: 20px;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
        }}
        
        .title-container {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 5px;
        }}
        
        .show-title {{
            font-size: 1.4em;
            color: var(--text-color);
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex: 1;
        }}
        
        .season-complete-badge-inline {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--progress-complete);
            color: white;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            font-weight: bold;
            font-size: 0.9em;
            box-shadow: 0 0 10px var(--progress-complete);
            flex-shrink: 0;
        }}
        
        .show-meta {{
            color: var(--primary-color);
            font-size: 0.9em;
            margin-bottom: 20px;
            min-height: 1.5em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .episodes-section {{
            margin-bottom: 20px;
            flex-grow: 1;
        }}
        
        .episodes-section .section-title {{
            font-size: 0.95em;
            margin-bottom: 10px;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 5px;
        }}
        
        .episodes-list {{
            max-height: 200px;
            overflow-y: auto;
            padding-right: 5px;
        }}
        
        .episode-item {{
            padding: 8px 10px;
            margin-bottom: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            border-left: 4px solid;
            transition: transform 0.2s ease;
        }}
        
        .episode-item:hover {{
            transform: translateX(5px);
        }}
        
        .episode-item.status-downloaded {{
            border-left-color: var(--progress-complete);
        }}
        
        .episode-item.status-monitored {{
            border-left-color: var(--progress-halfway);
        }}
        
        .episode-item.status-missing {{
            border-left-color: var(--progress-not-started);
        }}
        
        .episode-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
            font-size: 0.85em;
        }}
        
        .episode-number {{
            font-weight: bold;
            color: var(--primary-color);
        }}
        
        .episode-date {{
            color: var(--text-secondary);
        }}
        
        .episode-days {{
            font-weight: 600;
        }}
        
        .days-today {{
            color: var(--progress-complete);
        }}
        
        .days-tomorrow {{
            color: var(--progress-almost);
        }}
        
        .days-future {{
            color: var(--progress-started);
        }}
        
        .days-past {{
            color: var(--text-secondary);
            opacity: 0.7;
        }}
        
        .days-yesterday {{
            color: var(--progress-just-started);
        }}
        
        .episode-title {{
            font-size: 0.95em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .episode-multiple .episode-titles {{
            font-size: 0.9em;
            color: var(--text-secondary);
            font-style: italic;
            margin-top: 4px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .no-episodes {{
            text-align: center;
            color: var(--text-secondary);
            font-style: italic;
            padding: 20px;
            font-size: 0.9em;
        }}
        
        .progress-section {{
            margin: 15px 0;
        }}
        
        .progress-item {{
            margin-bottom: 15px;
        }}
        
        .progress-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
            font-weight: 600;
            font-size: 0.9em;
        }}
        
        .progress-bar {{
            height: 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 5px;
            overflow: hidden;
            margin-bottom: 6px;
        }}
        
        .progress-fill {{
            height: 100%;
            border-radius: 5px;
            transition: width 0.5s ease;
        }}
        
        .progress-stats {{
            font-size: 0.8em;
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .genres {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin: 15px 0;
        }}
        
        .genre-tag {{
            background: rgba(0, 180, 219, 0.1);
            color: var(--primary-color);
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 500;
        }}
        
        .show-footer {{
            margin-top: auto;
            padding-top: 15px;
            border-top: 1px solid var(--border-color);
            font-size: 0.85em;
            color: var(--text-secondary);
        }}
        
        .season-info {{
            display: flex;
            justify-content: space-between;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .monitored-count {{
            color: var(--progress-complete);
        }}
        
        .unmonitored-count {{
            color: var(--progress-started);
        }}
        
        .progress-legend {{
            display: flex;
            justify-content: center;
            gap: 15px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85em;
        }}
        
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 2px;
        }}
        
        footer {{
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            font-size: 0.9em;
            border-top: 1px solid var(--border-color);
            margin-top: 40px;
        }}
        
        .last-updated {{
            margin-top: 10px;
            font-size: 0.9em;
            opacity: 0.7;
        }}
        
        .refresh-btn {{
            background: var(--primary-color);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            cursor: pointer;
            font-weight: 600;
            margin-top: 15px;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
        }}
        
        .refresh-btn:hover {{
            background: var(--primary-dark);
            transform: translateY(-2px);
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .show-card {{
            animation: fadeIn 0.5s ease-out;
        }}
        
        .loading {{
            display: none;
            text-align: center;
            padding: 40px;
            color: var(--primary-color);
        }}
        
        .spinner {{
            border: 3px solid var(--border-color);
            border-top: 3px solid var(--primary-color);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        
        .episodes-list::-webkit-scrollbar {{
            width: 6px;
        }}
        
        .episodes-list::-webkit-scrollbar-track {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 3px;
        }}
        
        .episodes-list::-webkit-scrollbar-thumb {{
            background: var(--primary-color);
            border-radius: 3px;
        }}
        
        .episodes-list::-webkit-scrollbar-thumb:hover {{
            background: var(--primary-dark);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-top">
            <div class="filter-dropdown">
                <i class="fas fa-search"></i>
                <select id="showFilter" class="show-filter" onchange="window.location.href=this.value">
                    {show_filter_options}
                </select>
            </div>
            <button id="themeToggle" class="theme-toggle">
                <i class="fas fa-moon"></i>
                <span>Toggle Theme</span>
            </button>
        </div>
        
        <a href="#" class="return-to-top" title="Return to top">
            <i class="fas fa-arrow-up"></i>
        </a>
        
        <!-- Hidden radio inputs for CSS-only filtering -->
        <input type="radio" name="filter" id="filter-all" class="filter-radio" checked>
        <input type="radio" name="filter" id="filter-complete" class="filter-radio">
        <input type="radio" name="filter" id="filter-high-progress" class="filter-radio">
        <input type="radio" name="filter" id="filter-medium-progress" class="filter-radio">
        <input type="radio" name="filter" id="filter-low-progress" class="filter-radio">
        <input type="radio" name="filter" id="filter-date-range-high" class="filter-radio">
        <input type="radio" name="filter" id="filter-date-range-low" class="filter-radio">
        <input type="radio" name="filter" id="filter-has-episodes" class="filter-radio">
        
        <header>
            <h1><i class="fas fa-tv"></i> {HTML_TITLE}</h1>
            <div class="date-range">
                <i class="fas fa-calendar-alt"></i> Date Range: {overall_stats['date_range']['start_display']} to {overall_stats['date_range']['end_display']}
                ({overall_stats['date_range']['total_days']} days total)
            </div>
            
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="summary-number">{overall_stats['total_series']}</div>
                    <div class="summary-label">Total Shows</div>
                    <div class="summary-subtext">{overall_stats['shows_with_episodes']} with episodes in range</div>
                </div>
                <div class="summary-card">
                    <div class="summary-number">{overall_stats['episodes_in_range']}</div>
                    <div class="summary-label">Episodes in Range</div>
                    <div class="summary-subtext">{overall_stats['downloaded_in_range']} downloaded</div>
                </div>
                <div class="summary-card">
                    <div class="summary-number">{overall_stats['shows_complete']}</div>
                    <div class="summary-label">Complete Shows</div>
                    <div class="summary-subtext">{overall_stats['completed_current_seasons']} current seasons complete</div>
                </div>
                <div class="summary-card">
                    <div class="summary-number">{overall_stats['shows_high_progress']}</div>
                    <div class="summary-label">High Progress</div>
                    <div class="summary-subtext">75-99% downloaded</div>
                </div>
                <div class="summary-card">
                    <div class="summary-number">{overall_stats['shows_medium_progress']}</div>
                    <div class="summary-label">Medium Progress</div>
                    <div class="summary-subtext">25-74% downloaded</div>
                </div>
                <div class="summary-card">
                    <div class="summary-number">{overall_stats['shows_low_progress']}</div>
                    <div class="summary-label">Low Progress</div>
                    <div class="summary-subtext">1-24% downloaded</div>
                </div>
                <div class="summary-card">
                    <div class="summary-number">{overall_stats['shows_not_started']}</div>
                    <div class="summary-label">Not Started</div>
                    <div class="summary-subtext">0% downloaded</div>
                </div>
                <div class="summary-card">
                    <div class="summary-number">{len(completed_seasons)}</div>
                    <div class="summary-label">Seasons Completed</div>
                    <div class="summary-subtext">In date range</div>
                </div>
            </div>
            
            <div style="margin-top: 25px; font-size: 0.9em; opacity: 0.9; text-align: center;">
                * Unmonitored seasons are counted as 100% complete in progress calculations
            </div>
        </header>
        
        <div class="completed-seasons-section">
            <div class="section-title">
                <i class="fas fa-trophy"></i>
                <span>Recently Completed Seasons ({len(completed_seasons)})</span>
            </div>
            <div class="completed-seasons-grid">
                {completed_seasons_html}
            </div>
        </div>
        
        <div class="progress-legend">
            <div class="legend-item"><div class="legend-color" style="background: var(--progress-complete);"></div><span>Complete (100%)</span></div>
            <div class="legend-item"><div class="legend-color" style="background: var(--progress-almost);"></div><span>Almost Complete (75-99%)</span></div>
            <div class="legend-item"><div class="legend-color" style="background: var(--progress-halfway);"></div><span>Halfway (50-74%)</span></div>
            <div class="legend-item"><div class="legend-color" style="background: var(--progress-started);"></div><span>Started (25-49%)</span></div>
            <div class="legend-item"><div class="legend-color" style="background: var(--progress-just-started);"></div><span>Just Started (1-24%)</span></div>
            <div class="legend-item"><div class="legend-color" style="background: var(--progress-not-started);"></div><span>Not Started (0%)</span></div>
        </div>
        
        <div class="overall-progress-section">
            <div class="stat-progress">
                <div class="stat-progress-header">
                    <span>Complete Library Progress</span>
                    <span class="stat-progress-percentage">{overall_stats['overall_progress']:.1f}%</span>
                </div>
                <div class="stat-progress-bar">
                    <div class="stat-progress-fill" style="width: {overall_stats['overall_progress']}%; 
                         background: {get_progress_bar_color(overall_stats['overall_progress'])};"></div>
                </div>
                <div class="stat-progress-stats">
                    {overall_stats['total_downloaded_all']:,}/{overall_stats['total_episodes_all']:,} episodes • 
                    {overall_stats['total_series']} series
                </div>
            </div>
            
            <div class="stat-progress">
                <div class="stat-progress-header">
                    <span>Date Range Progress ({overall_stats['date_range']['start_display']} to {overall_stats['date_range']['end_display']})</span>
                    <span class="stat-progress-percentage">{overall_stats['overall_date_range_progress']:.1f}%</span>
                </div>
                <div class="stat-progress-bar">
                    <div class="stat-progress-fill" style="width: {overall_stats['overall_date_range_progress']}%; 
                         background: {get_progress_bar_color(overall_stats['overall_date_range_progress'])};"></div>
                </div>
                <div class="stat-progress-stats">
                    {overall_stats['downloaded_in_range']}/{overall_stats['episodes_in_range']} episodes in date range
                </div>
            </div>
        </div>
        
        <!-- Original Filter Buttons - RESTORED -->
        <div class="filters">
            <label for="filter-all" class="filter-btn active">All Shows ({overall_stats['total_series']})</label>
            <label for="filter-complete" class="filter-btn">Complete ({overall_stats['shows_complete']})</label>
            <label for="filter-high-progress" class="filter-btn">High Progress ({overall_stats['shows_high_progress']})</label>
            <label for="filter-medium-progress" class="filter-btn">Medium Progress ({overall_stats['shows_medium_progress']})</label>
            <label for="filter-low-progress" class="filter-btn">Low Progress ({overall_stats['shows_low_progress']})</label>
            <label for="filter-date-range-high" class="filter-btn">Date Range ≥75%</label>
            <label for="filter-date-range-low" class="filter-btn">Date Range <25%</label>
            <label for="filter-has-episodes" class="filter-btn">Has Episodes ({overall_stats['shows_with_episodes']})</label>
        </div>
        
        <div class="shows-grid" id="showsGrid">
            {shows_html if shows_html else '''
            <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 60px 20px;">
                <div style="font-size: 4em; margin-bottom: 20px;">📺</div>
                <h3 style="font-size: 1.8em; margin-bottom: 15px; color: var(--text-color);">No Shows with Episodes in Date Range</h3>
                <p style="font-size: 1.2em; color: var(--text-secondary); margin-bottom: 10px;">
                    No shows have episodes scheduled from {overall_stats['date_range']['start_display']} to {overall_stats['date_range']['end_display']}.
                </p>
                <p style="font-size: 1em; color: var(--text-secondary);">
                    Try adjusting your date range in the configuration.
                </p>
            </div>
            '''}
        </div>
        
        <div class="loading" id="loadingIndicator">
            <div class="spinner"></div>
            <div>Updating calendar...</div>
        </div>
        
        <footer>
            <div>Powered by Sonarr • Auto-refreshes every {REFRESH_INTERVAL_HOURS} hour{'s' if REFRESH_INTERVAL_HOURS != 1 else ''}</div>
            <div class="last-updated" id="lastUpdated">Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
            <a href="#" class="refresh-btn" onclick="location.reload()">
                <i class="fas fa-sync-alt"></i> Refresh Now
            </a>
            <div style="margin-top: 15px; font-size: 0.85em; opacity: 0.7;">
                Showing {DAYS_PAST} days past and {DAYS_FUTURE} days future ({overall_stats['date_range']['total_days']} day range)
            </div>
        </footer>
    </div>

    <!-- MINIMAL JAVASCRIPT - ONLY 10 LINES FOR THEME PERSISTENCE -->
    <script>
        // Set theme from localStorage on page load
        const savedTheme = localStorage.getItem('sonarr-theme') || '{HTML_THEME}';
        document.body.classList.add('theme-' + savedTheme);
        
        // Theme toggle button
        document.getElementById('themeToggle').addEventListener('click', function() {{
            const isDark = document.body.classList.contains('theme-dark');
            document.body.classList.remove('theme-dark', 'theme-light');
            const newTheme = isDark ? 'light' : 'dark';
            document.body.classList.add('theme-' + newTheme);
            localStorage.setItem('sonarr-theme', newTheme);
        }});
        
        // Update active filter button based on radio selection
        document.querySelectorAll('.filter-radio').forEach(radio => {{
            radio.addEventListener('change', function() {{
                document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
                const label = document.querySelector('label[for="' + this.id + '"]');
                if (label) label.classList.add('active');
            }});
        }});
    </script>
</body>
</html>'''
    
    return html_template

def write_html_file(html_content):
    """Write HTML content to output file"""
    try:
        output_dir = os.path.dirname(OUTPUT_HTML_FILE)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        with open(OUTPUT_HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ HTML file written to {OUTPUT_HTML_FILE}")
        return True
    except Exception as e:
        print(f"❌ Error writing HTML file: {e}")
        return False

def write_json_file(data):
    """Optional: Write JSON data to file"""
    if not OUTPUT_JSON_FILE:
        return True
    
    try:
        output_dir = os.path.dirname(OUTPUT_JSON_FILE)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            
        with open(OUTPUT_JSON_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ JSON data written to {OUTPUT_JSON_FILE}")
        return True
    except Exception as e:
        print(f"❌ Error writing JSON file: {e}")
        return False

def cleanup_old_images(days_old=30):
    """Remove cached images older than specified days"""
    if not os.path.exists(IMAGE_CACHE_DIR):
        return
    
    cutoff_time = time.time() - (days_old * 24 * 3600)
    
    for filename in os.listdir(IMAGE_CACHE_DIR):
        filepath = os.path.join(IMAGE_CACHE_DIR, filename)
        if os.path.isfile(filepath):
            if os.path.getmtime(filepath) < cutoff_time:
                try:
                    os.remove(filepath)
                    print(f"Removed old cached image: {filename}")
                except Exception as e:
                    print(f"Error removing {filename}: {e}")

def main():
    """Main execution function"""
    global current_days_past, current_days_future
    
    current_days_past = DAYS_PAST
    current_days_future = DAYS_FUTURE
    
    print("=" * 60)
    print("🎬 Sonarr Calendar Tracker Pro")
    print("=" * 60)
    print(f"📁 Config: {CONFIG_FILE}")
    print(f"🔗 Sonarr: {SONARR_URL}")
    print(f"📅 Range: {DAYS_PAST} days back, {DAYS_FUTURE} days forward")
    print(f"📊 Output: {OUTPUT_HTML_FILE}")
    if OUTPUT_JSON_FILE:
        print(f"📋 JSON: {OUTPUT_JSON_FILE}")
    print(f"🔄 Refresh: Every {REFRESH_INTERVAL_HOURS} hour{'s' if REFRESH_INTERVAL_HOURS != 1 else ''}")
    print("=" * 60)
    
    if not test_sonarr_connection():
        print("\n❌ Cannot connect to Sonarr. Please check your configuration.")
        print("   Run: python sonarr_calendar_config.py")
        sys.exit(1)
    
    print("✅ Connected to Sonarr successfully!")
    
    if datetime.now(UTC).weekday() == 0:
        cleanup_old_images()
    
    while True:
        try:
            print(f"\n[{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}] Fetching calendar data...")
            
            calendar_data, date_range = fetch_sonarr_calendar()
            print(f"   📅 Date Range: {date_range['start_display']} to {date_range['end_display']}")
            print(f"   📺 Found {len(calendar_data)} episodes in date range")
            
            series_info = fetch_all_series()
            print(f"   📚 Loaded information for {len(series_info)} series")
            
            processed_shows = process_calendar_data(
                calendar_data, series_info, date_range['start'], date_range['end']
            )
            print(f"   🎯 Processed {len(processed_shows)} shows with grouped episodes")
            
            overall_stats = calculate_overall_statistics(processed_shows, date_range)
            print(f"   📊 Overall progress: {overall_stats['overall_progress']:.1f}%")
            print(f"   📈 Date range progress: {overall_stats['overall_date_range_progress']:.1f}%")
            
            print("   💾 Generating HTML file...")
            html_content = generate_html_file(processed_shows, overall_stats, calendar_data)
            
            if write_html_file(html_content):
                print(f"   ✅ Success! {len(processed_shows)} shows processed")
                print(f"      Complete: {overall_stats['shows_complete']} | High: {overall_stats['shows_high_progress']} | "
                      f"Medium: {overall_stats['shows_medium_progress']} | Low: {overall_stats['shows_low_progress']}")
                print(f"      🏆 Seasons completed: {len(calculate_completed_seasons_in_range(processed_shows, calendar_data, date_range['start'], date_range['end']))}")
                
                write_json_file({
                    'last_updated': datetime.now(UTC).isoformat(),
                    'date_range': date_range,
                    'overall_stats': overall_stats,
                    'total_shows': len(processed_shows),
                    'shows': processed_shows
                })
                
                print(f"\n⏰ Next update in {REFRESH_INTERVAL_HOURS} hour{'s' if REFRESH_INTERVAL_HOURS != 1 else ''}...")
            
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            print(f"\n⏰ Retrying in {REFRESH_INTERVAL_HOURS} hour{'s' if REFRESH_INTERVAL_HOURS != 1 else ''}...")
        
        time.sleep(REFRESH_INTERVAL)

if __name__ == "__main__":
    main()