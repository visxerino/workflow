"""
Breakthrough detection using the v1 rule.
For each qualifying video (sorted oldest->newest):
- Need at least 10 prior qualifying videos
- prev10_avg_views = mean(views of prior 10 qualifying videos)
- If prev10_avg_views < 50: ignore (noise filter)
- threshold = max(2000, 10 * prev10_avg_views)
- breakthrough if current views >= threshold
- ratio = views / prev10_avg_views
"""
from typing import List, Dict, Any
from tqdm import tqdm

from db import Database


def calculate_breakthroughs(db: Database, noise_threshold: int = 50,
                            min_threshold: int = 2000) -> int:
    """
    Calculate breakthroughs for all eligible channels.

    Args:
        db: Database instance
        noise_threshold: Minimum prev10_avg_views to consider (default 50)
        min_threshold: Minimum absolute threshold (default 2000)

    Returns:
        Number of breakthroughs detected
    """
    eligible_channels = db.get_eligible_channels()

    print(f"\nCalculating breakthroughs for {len(eligible_channels)} eligible channels...")
    print(f"Noise threshold: {noise_threshold} views")
    print(f"Minimum threshold: {min_threshold} views")

    total_breakthroughs = 0
    channels_with_breakthroughs = 0

    for channel in tqdm(eligible_channels, desc="Analyzing"):
        channel_id = channel['channel_id']

        # Get qualifying videos sorted by published_at (oldest first)
        videos = db.get_videos_for_channel(channel_id, qualifying_only=True)

        if len(videos) < 11:  # Need at least 11 (10 prior + 1 current)
            continue

        breakthroughs = []

        # Iterate through videos starting from position 10 (index 10)
        for i in range(10, len(videos)):
            current_video = videos[i]
            current_views = current_video['view_count']

            # Get prior 10 qualifying videos
            prior_10 = videos[i-10:i]
            prior_views = [v['view_count'] for v in prior_10]
            prev10_avg_views = sum(prior_views) / 10

            # Noise filter
            if prev10_avg_views < noise_threshold:
                continue

            # Calculate threshold
            threshold = max(min_threshold, 10 * prev10_avg_views)

            # Check for breakthrough
            if current_views >= threshold:
                ratio = current_views / prev10_avg_views if prev10_avg_views > 0 else 0

                breakthrough = {
                    'video_id': current_video['video_id'],
                    'channel_id': channel_id,
                    'title': current_video['title'],
                    'published_at': current_video['published_at'],
                    'view_count': current_views,
                    'prev10_avg_views': prev10_avg_views,
                    'threshold': threshold,
                    'ratio': ratio,
                    'is_first_breakthrough': 0,
                    'position_in_sequence': i
                }

                breakthroughs.append(breakthrough)

        # Mark first breakthrough
        if breakthroughs:
            breakthroughs[0]['is_first_breakthrough'] = 1
            channels_with_breakthroughs += 1

            # Save all breakthroughs for this channel
            for bt in breakthroughs:
                db.insert_breakthrough(bt)
                total_breakthroughs += 1

    print(f"\nTotal breakthroughs: {total_breakthroughs}")
    print(f"Channels with breakthroughs: {channels_with_breakthroughs}")

    return total_breakthroughs
