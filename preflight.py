"""
PASS 1B: Preflight eligibility check.
Quickly scan newest 100 videos to count qualifying longform videos.
Only deep scrape channels with >= 10 qualifying videos.
"""
from typing import List, Dict, Any
from tqdm import tqdm

from youtube_api import YouTubeAPI
from db import Database


def check_eligibility(api: YouTubeAPI, db: Database,
                      min_duration_min: int = 20,
                      min_qualifying: int = 10,
                      max_channels: int = 1200) -> int:
    """
    Preflight check: scan newest 100 videos per channel to count qualifying longform.

    Args:
        api: YouTubeAPI instance
        db: Database instance
        min_duration_min: Minimum duration in minutes for qualifying videos
        min_qualifying: Minimum qualifying videos needed to be eligible
        max_channels: Max channels to check

    Returns:
        Number of eligible channels
    """
    filtered = db.get_filtered_channels(passed_only=True)
    filtered = filtered[:max_channels]

    print(f"\nPreflight checking {len(filtered)} channels...")
    print(f"Min duration: {min_duration_min} minutes")
    print(f"Min qualifying videos: {min_qualifying}")
    print(f"Checking newest 100 videos per channel (2 pages)")

    min_duration_sec = min_duration_min * 60
    eligible_count = 0

    for channel in tqdm(filtered, desc="Preflight check"):
        channel_id = channel['channel_id']
        channel_title = channel.get('channel_title', '')
        uploads_playlist_id = channel.get('uploads_playlist_id', '')

        if not uploads_playlist_id:
            db.insert_eligible_channel(channel_id, channel_title, 0, False)
            continue

        # Fetch newest 100 videos (2 pages of 50)
        video_ids = []
        page_token = None

        try:
            for page_num in range(2):  # 2 pages = 100 videos max
                result = api.get_playlist_items(
                    playlist_id=uploads_playlist_id,
                    max_results=50,
                    page_token=page_token
                )

                items = result.get('items', [])
                for item in items:
                    video_id = item['contentDetails']['videoId']
                    video_ids.append(video_id)

                page_token = result.get('nextPageToken')
                if not page_token:
                    break

        except Exception as e:
            print(f"\nError fetching playlist items for {channel_id}: {e}")
            db.insert_eligible_channel(channel_id, channel_title, 0, False)
            continue

        # Fetch video details in batches of 50
        qualifying_count = 0
        batch_size = 50

        try:
            for i in range(0, len(video_ids), batch_size):
                batch = video_ids[i:i + batch_size]
                videos = api.get_videos(batch)

                for video in videos:
                    # Parse duration
                    duration_str = video.get('contentDetails', {}).get('duration', 'PT0S')
                    duration_sec = api.parse_duration(duration_str)

                    # Check if made for kids
                    made_for_kids = video.get('status', {}).get('madeForKids', False)

                    # Qualifying: duration >= min AND not made for kids
                    if duration_sec >= min_duration_sec and not made_for_kids:
                        qualifying_count += 1

        except Exception as e:
            print(f"\nError fetching videos for {channel_id}: {e}")
            db.insert_eligible_channel(channel_id, channel_title, qualifying_count, False)
            continue

        # Determine eligibility
        is_eligible = qualifying_count >= min_qualifying
        db.insert_eligible_channel(channel_id, channel_title, qualifying_count, is_eligible)

        if is_eligible:
            eligible_count += 1

    print(f"\nEligible channels: {eligible_count}")
    print(f"Quota used: {api.get_quota_used()} units")

    return eligible_count
