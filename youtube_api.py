"""
YouTube Data API v3 wrapper with caching, retry, and rate limiting.
Quota-optimized design.
"""
import os
import json
import hashlib
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import threading
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import isodate


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, requests_per_second: float = 2.0):
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.max_tokens = requests_per_second
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self):
        """Acquire permission to make a request (blocks if necessary)."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.rate
                time.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class YouTubeAPI:
    """
    YouTube Data API v3 wrapper with quota optimization.

    Quota costs:
    - search.list: 100 units
    - channels.list: 1 unit
    - playlistItems.list: 1 unit
    - videos.list: 1 unit
    """

    def __init__(self, api_key: str, cache_dir: str = "./cache", use_cache: bool = True):
        self.api_key = api_key
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self.rate_limiter = RateLimiter(requests_per_second=2.0)  # Conservative
        self.quota_used = 0

        if self.use_cache:
            self.cache_dir.mkdir(exist_ok=True)

    def _cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate cache key from endpoint and sorted params."""
        sorted_params = json.dumps(params, sort_keys=True)
        key_str = f"{endpoint}:{sorted_params}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _get_cache(self, cache_key: str) -> Optional[Dict]:
        """Retrieve from cache if available."""
        if not self.use_cache:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _set_cache(self, cache_key: str, data: Dict):
        """Store to cache."""
        if not self.use_cache:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Cache write error: {e}")

    def _retry_request(self, func, max_retries: int = 5):
        """Execute request with exponential backoff retry."""
        for attempt in range(max_retries):
            try:
                self.rate_limiter.acquire()
                return func()
            except HttpError as e:
                if e.resp.status == 429:  # Rate limit
                    wait_time = (2 ** attempt) * 2
                    print(f"Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                elif e.resp.status >= 500:  # Server error
                    wait_time = (2 ** attempt)
                    print(f"Server error {e.resp.status}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = (2 ** attempt)
                print(f"Error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

        raise Exception(f"Max retries ({max_retries}) exceeded")

    def search_videos(self, query: str, max_results: int = 50,
                      published_after: str = None, page_token: str = None) -> Dict:
        """
        Search for videos. Quota cost: 100 units.

        Args:
            query: Search query
            max_results: Max results per page (1-50)
            published_after: ISO 8601 datetime string
            page_token: Pagination token
        """
        params = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'order': 'date',
            'maxResults': min(max_results, 50),
            'fields': 'items(snippet(channelId,channelTitle,publishedAt,title)),nextPageToken,pageInfo'
        }

        if published_after:
            params['publishedAfter'] = published_after
        if page_token:
            params['pageToken'] = page_token

        cache_key = self._cache_key('search', params)
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        def _execute():
            result = self.youtube.search().list(**params).execute()
            self.quota_used += 100
            return result

        result = self._retry_request(_execute)
        self._set_cache(cache_key, result)
        return result

    def get_channels(self, channel_ids: List[str]) -> List[Dict]:
        """
        Get channel details. Quota cost: 1 unit per call.
        Supports batching up to 50 channels per call.

        Args:
            channel_ids: List of channel IDs (max 50)
        """
        if not channel_ids:
            return []

        # Batch max 50 at a time
        channel_ids = channel_ids[:50]

        params = {
            'part': 'snippet,statistics,contentDetails',
            'id': ','.join(channel_ids),
            'fields': 'items(id,snippet(title,description,publishedAt),' +
                     'statistics(subscriberCount,videoCount,viewCount),' +
                     'contentDetails(relatedPlaylists(uploads)))'
        }

        cache_key = self._cache_key('channels', params)
        cached = self._get_cache(cache_key)
        if cached:
            return cached.get('items', [])

        def _execute():
            result = self.youtube.channels().list(**params).execute()
            self.quota_used += 1
            return result

        result = self._retry_request(_execute)
        self._set_cache(cache_key, result)
        return result.get('items', [])

    def get_playlist_items(self, playlist_id: str, max_results: int = 50,
                           page_token: str = None) -> Dict:
        """
        Get playlist items. Quota cost: 1 unit.

        Args:
            playlist_id: Playlist ID
            max_results: Max results per page (1-50)
            page_token: Pagination token
        """
        params = {
            'part': 'contentDetails',
            'playlistId': playlist_id,
            'maxResults': min(max_results, 50),
            'fields': 'items(contentDetails(videoId)),nextPageToken,pageInfo'
        }

        if page_token:
            params['pageToken'] = page_token

        cache_key = self._cache_key('playlistItems', params)
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        def _execute():
            result = self.youtube.playlistItems().list(**params).execute()
            self.quota_used += 1
            return result

        result = self._retry_request(_execute)
        self._set_cache(cache_key, result)
        return result

    def get_videos(self, video_ids: List[str]) -> List[Dict]:
        """
        Get video details. Quota cost: 1 unit per call.
        Supports batching up to 50 videos per call.

        Args:
            video_ids: List of video IDs (max 50)
        """
        if not video_ids:
            return []

        # Batch max 50 at a time
        video_ids = video_ids[:50]

        params = {
            'part': 'snippet,statistics,contentDetails,status,topicDetails',
            'id': ','.join(video_ids),
            'fields': 'items(id,snippet(publishedAt,channelId,title,description,tags,' +
                     'categoryId,defaultLanguage,defaultAudioLanguage,thumbnails),' +
                     'statistics(viewCount,likeCount,commentCount),' +
                     'contentDetails(duration,caption),' +
                     'status(madeForKids),' +
                     'topicDetails(topicCategories))'
        }

        cache_key = self._cache_key('videos', params)
        cached = self._get_cache(cache_key)
        if cached:
            return cached.get('items', [])

        def _execute():
            result = self.youtube.videos().list(**params).execute()
            self.quota_used += 1
            return result

        result = self._retry_request(_execute)
        self._set_cache(cache_key, result)
        return result.get('items', [])

    def parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration to seconds."""
        try:
            duration = isodate.parse_duration(duration_str)
            return int(duration.total_seconds())
        except Exception:
            return 0

    def get_quota_used(self) -> int:
        """Get total quota units used in this session."""
        return self.quota_used


def get_api_key() -> str:
    """Get API key from environment or .env file."""
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        # Try loading from .env
        env_path = Path('.env')
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith('YOUTUBE_API_KEY='):
                        api_key = line.strip().split('=', 1)[1]
                        break

    if not api_key or api_key == 'YOUR_API_KEY_HERE':
        raise ValueError(
            "YouTube API key not found. Set YOUTUBE_API_KEY environment variable " +
            "or create a .env file with YOUTUBE_API_KEY=your_key"
        )

    return api_key
