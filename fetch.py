"""
PASS 2: Deep fetch - scrape all uploads from eligible channels.
Fetch full video metadata for qualifying longform videos only.
"""
from typing import List, Dict, Any
from datetime import datetime
from tqdm import tqdm

from youtube_api import YouTubeAPI
from db import Database


def compute_derived_fields(video: Dict[str, Any], api: YouTubeAPI) -> Dict[str, Any]:
    """Compute derived fields for a video."""
    snippet = video.get('snippet', {})
    statistics = video.get('statistics', {})
    content_details = video.get('contentDetails', {})
    status = video.get('status', {})
    topic_details = video.get('topicDetails', {})

    # Parse published date
    published_at_str = snippet.get('publishedAt', '')
    try:
        published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
        days_since_publish = (datetime.now(published_at.tzinfo) - published_at).days
        days_since_publish = max(1, days_since_publish)  # Avoid division by zero
    except Exception:
        days_since_publish = 1

    # Parse counts
    view_count = int(statistics.get('viewCount', 0))
    like_count = int(statistics.get('likeCount', 0))
    comment_count = int(statistics.get('commentCount', 0))

    # Compute rates
    views_per_day = view_count / days_since_publish if days_since_publish > 0 else 0
    like_rate_per_1k = (like_count / view_count * 1000) if view_count > 0 else 0
    comment_rate_per_1k = (comment_count / view_count * 1000) if view_count > 0 else 0

    # Parse duration
    duration_str = content_details.get('duration', 'PT0S')
    duration_sec = api.parse_duration(duration_str)

    # Build result
    result = {
        'video_id': video['id'],
        'channel_id': snippet.get('channelId', ''),
        'title': snippet.get('title', ''),
        'description': snippet.get('description', ''),
        'published_at': published_at_str,
        'duration_sec': duration_sec,
        'view_count': view_count,
        'like_count': like_count,
        'comment_count': comment_count,
        'tags': snippet.get('tags', []),
        'category_id': snippet.get('categoryId', ''),
        'default_language': snippet.get('defaultLanguage', ''),
        'default_audio_language': snippet.get('defaultAudioLanguage', ''),
        'caption': 1 if content_details.get('caption') == 'true' else 0,
        'made_for_kids': 1 if status.get('madeForKids', False) else 0,
        'topic_categories': topic_details.get('topicCategories', []),
        'days_since_publish': days_since_publish,
        'views_per_day': views_per_day,
        'like_rate_per_1k': like_rate_per_1k,
        'comment_rate_per_1k': comment_rate_per_1k,
        'is_qualifying': 0  # Will be set by caller
    }

    return result


def deep_fetch_channels(api: YouTubeAPI, db: Database,
                        max_deep_channels: int = 400,
                        max_upload_items: int = 300,
                        min_duration_min: int = 20) -> int:
    """
    PASS 2: Deep scrape eligible channels.

    Args:
        api: YouTubeAPI instance
        db: Database instance
        max_deep_channels: Max number of eligible channels to deep scrape
        max_upload_items: Max upload items to fetch per channel (prevents runaway)
        min_duration_min: Minimum duration for qualifying videos

    Returns:
        Number of channels deep scraped
    """
    eligible = db.get_eligible_channels()
    eligible = eligible[:max_deep_channels]

    print(f"\nDeep fetching {len(eligible)} eligible channels...")
    print(f"Max upload items per channel: {max_upload_items}")
    print(f"Min duration: {min_duration_min} minutes")

    min_duration_sec = min_duration_min * 60
    channels_scraped = 0
    total_videos = 0
    total_qualifying = 0

    for channel in tqdm(eligible, desc="Deep fetch"):
        channel_id = channel['channel_id']

        # Get uploads playlist ID from channels_filtered
        filtered_channels = db.get_filtered_channels(passed_only=True)
        uploads_playlist_id = None
        for fc in filtered_channels:
            if fc['channel_id'] == channel_id:
                uploads_playlist_id = fc.get('uploads_playlist_id', '')
                break

        if not uploads_playlist_id:
            print(f"\nNo uploads playlist for {channel_id}")
            continue

        # Fetch ALL uploads (up to max_upload_items)
        video_ids = []
        page_token = None
        items_fetched = 0

        try:
            while items_fetched < max_upload_items:
                result = api.get_playlist_items(
                    playlist_id=uploads_playlist_id,
                    max_results=50,
                    page_token=page_token
                )

                items = result.get('items', [])
                for item in items:
                    video_id = item['contentDetails']['videoId']
                    video_ids.append(video_id)
                    items_fetched += 1

                    if items_fetched >= max_upload_items:
                        break

                page_token = result.get('nextPageToken')
                if not page_token:
                    break

        except Exception as e:
            print(f"\nError fetching uploads for {channel_id}: {e}")
            continue

        # Fetch full video details in batches
        batch_size = 50
        qualifying_count = 0

        try:
            for i in range(0, len(video_ids), batch_size):
                batch = video_ids[i:i + batch_size]
                videos = api.get_videos(batch)

                for video in videos:
                    # Compute derived fields
                    video_data = compute_derived_fields(video, api)

                    # Check if qualifying
                    is_qualifying = (
                        video_data['duration_sec'] >= min_duration_sec and
                        video_data['made_for_kids'] == 0
                    )

                    video_data['is_qualifying'] = 1 if is_qualifying else 0

                    # Save to database
                    db.insert_video(video_data)
                    total_videos += 1

                    if is_qualifying:
                        qualifying_count += 1
                        total_qualifying += 1

        except Exception as e:
            print(f"\nError fetching video details for {channel_id}: {e}")
            continue

        channels_scraped += 1

    print(f"\nChannels scraped: {channels_scraped}")
    print(f"Total videos: {total_videos}")
    print(f"Total qualifying videos: {total_qualifying}")
    print(f"Quota used: {api.get_quota_used()} units")

    return channels_scraped
