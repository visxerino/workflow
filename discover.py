"""
PASS 1: Discovery module - find candidate channels using search.list.
Quota-optimized to minimize expensive search calls.
"""
from typing import List, Set, Dict, Any
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

from youtube_api import YouTubeAPI
from db import Database


# Cohort cutoff date
COHORT_CUTOFF = "2025-07-15T00:00:00Z"


def load_queries(queries_file: str) -> List[str]:
    """Load search queries from file."""
    queries_path = Path(queries_file)
    if not queries_path.exists():
        raise FileNotFoundError(f"Queries file not found: {queries_file}")

    with open(queries_path, 'r', encoding='utf-8') as f:
        queries = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    return queries


def discover_channels(api: YouTubeAPI, db: Database, queries_file: str,
                      target_channels: int = 1200, pages_per_query: int = 1) -> int:
    """
    PASS 1A: Discover channels via search.list.

    Args:
        api: YouTubeAPI instance
        db: Database instance
        queries_file: Path to queries.txt
        target_channels: Target number of unique channels to discover
        pages_per_query: Number of pages to fetch per query (default 1 to minimize quota)

    Returns:
        Number of channels discovered
    """
    queries = load_queries(queries_file)
    print(f"Loaded {len(queries)} search queries")
    print(f"Target: {target_channels} unique channels")
    print(f"Pages per query: {pages_per_query} (50 results/page)")
    print(f"Cohort cutoff: {COHORT_CUTOFF}")

    discovered_channel_ids: Set[str] = set()
    channel_query_map: Dict[str, str] = {}  # channel_id -> first query that found it

    # Search for videos and collect channel IDs
    for query in tqdm(queries, desc="Searching"):
        if len(discovered_channel_ids) >= target_channels:
            print(f"\nReached target of {target_channels} channels. Stopping search.")
            break

        page_token = None
        for page_num in range(pages_per_query):
            try:
                result = api.search_videos(
                    query=query,
                    max_results=50,
                    published_after=COHORT_CUTOFF,
                    page_token=page_token
                )

                items = result.get('items', [])
                for item in items:
                    channel_id = item['snippet']['channelId']
                    if channel_id not in discovered_channel_ids:
                        discovered_channel_ids.add(channel_id)
                        channel_query_map[channel_id] = query

                page_token = result.get('nextPageToken')
                if not page_token:
                    break

            except Exception as e:
                print(f"\nError searching '{query}': {e}")
                break

    print(f"\nDiscovered {len(discovered_channel_ids)} unique channels from search")

    # Fetch channel metadata in batches
    channel_ids_list = list(discovered_channel_ids)
    batch_size = 50
    channels_saved = 0

    print(f"Fetching channel metadata...")
    for i in tqdm(range(0, len(channel_ids_list), batch_size), desc="Fetching channels"):
        batch = channel_ids_list[i:i + batch_size]

        try:
            channels = api.get_channels(batch)

            for channel in channels:
                channel_id = channel['id']
                snippet = channel.get('snippet', {})
                statistics = channel.get('statistics', {})
                content_details = channel.get('contentDetails', {})

                channel_data = {
                    'channel_id': channel_id,
                    'channel_title': snippet.get('title', ''),
                    'description': snippet.get('description', ''),
                    'published_at': snippet.get('publishedAt', ''),
                    'subscriber_count': int(statistics.get('subscriberCount', 0)),
                    'video_count': int(statistics.get('videoCount', 0)),
                    'view_count': int(statistics.get('viewCount', 0)),
                    'uploads_playlist_id': content_details.get('relatedPlaylists', {}).get('uploads', ''),
                    'discovered_via_query': channel_query_map.get(channel_id, '')
                }

                db.insert_discovered_channel(channel_data)
                channels_saved += 1

        except Exception as e:
            print(f"\nError fetching channel batch: {e}")

    print(f"\nSaved {channels_saved} channels to database")
    print(f"Quota used: {api.get_quota_used()} units")

    return channels_saved


def filter_channels(api: YouTubeAPI, db: Database,
                    max_video_count: int = 500,
                    max_subscriber_count: int = 500000) -> int:
    """
    PASS 1B: Apply cohort filter and cheap skip rules.

    Filters:
    - HARD: channelCreatedAt >= COHORT_CUTOFF
    - Cheap skip: video_count > max_video_count (likely shorts spam)
    - Cheap skip: subscriber_count > max_subscriber_count (not "new" in practice)

    Returns:
        Number of channels that passed filters
    """
    discovered = db.get_discovered_channels()
    print(f"\nFiltering {len(discovered)} discovered channels...")
    print(f"Cohort cutoff: {COHORT_CUTOFF}")
    print(f"Max video count: {max_video_count}")
    print(f"Max subscriber count: {max_subscriber_count}")

    cutoff_dt = datetime.fromisoformat(COHORT_CUTOFF.replace('Z', '+00:00'))
    passed = 0
    failed = 0

    for channel in tqdm(discovered, desc="Filtering"):
        channel_id = channel['channel_id']
        published_at_str = channel.get('published_at', '')

        # Parse channel creation date
        try:
            channel_created = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
        except Exception:
            db.insert_filtered_channel(channel, passed=False, reason="invalid_date")
            failed += 1
            continue

        # HARD filter: cohort cutoff
        if channel_created < cutoff_dt:
            db.insert_filtered_channel(channel, passed=False, reason="before_cutoff")
            failed += 1
            continue

        # Cheap skip: too many videos (likely shorts spam)
        if channel.get('video_count', 0) > max_video_count:
            db.insert_filtered_channel(channel, passed=False, reason="too_many_videos")
            failed += 1
            continue

        # Cheap skip: too many subscribers (outlier)
        if channel.get('subscriber_count', 0) > max_subscriber_count:
            db.insert_filtered_channel(channel, passed=False, reason="too_many_subscribers")
            failed += 1
            continue

        # Passed all filters
        db.insert_filtered_channel(channel, passed=True, reason="")
        passed += 1

    print(f"\nPassed: {passed}")
    print(f"Failed: {failed}")

    return passed
