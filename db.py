"""
Database schema and operations for YouTube research pipeline.
Uses SQLite for persistence and resume capability.
"""
import sqlite3
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
import os


class Database:
    def __init__(self, db_path: str = "youtube_research.db"):
        self.db_path = db_path
        self.conn = None
        self.init_db()

    def init_db(self):
        """Initialize database schema."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # Channels discovered table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels_discovered (
                channel_id TEXT PRIMARY KEY,
                channel_title TEXT,
                description TEXT,
                published_at TEXT,
                subscriber_count INTEGER,
                video_count INTEGER,
                view_count INTEGER,
                uploads_playlist_id TEXT,
                discovered_via_query TEXT,
                discovered_at TEXT,
                created_at TEXT
            )
        """)

        # Channels filtered (after cutoff + cheap filters)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels_filtered (
                channel_id TEXT PRIMARY KEY,
                channel_title TEXT,
                description TEXT,
                published_at TEXT,
                subscriber_count INTEGER,
                video_count INTEGER,
                view_count INTEGER,
                uploads_playlist_id TEXT,
                discovered_via_query TEXT,
                filter_reason TEXT,
                passed_filter INTEGER DEFAULT 1
            )
        """)

        # Channels eligible (after preflight check)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels_eligible (
                channel_id TEXT PRIMARY KEY,
                channel_title TEXT,
                qualifying_longform_count_in_newest_100 INTEGER,
                is_eligible INTEGER DEFAULT 0,
                preflight_checked_at TEXT
            )
        """)

        # Videos table (deep scrape results)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT,
                title TEXT,
                description TEXT,
                published_at TEXT,
                duration_sec INTEGER,
                view_count INTEGER,
                like_count INTEGER,
                comment_count INTEGER,
                tags TEXT,
                category_id TEXT,
                default_language TEXT,
                default_audio_language TEXT,
                caption INTEGER,
                made_for_kids INTEGER,
                topic_categories TEXT,
                days_since_publish REAL,
                views_per_day REAL,
                like_rate_per_1k REAL,
                comment_rate_per_1k REAL,
                is_qualifying INTEGER DEFAULT 0,
                FOREIGN KEY (channel_id) REFERENCES channels_discovered(channel_id)
            )
        """)

        # Breakthroughs table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS breakthroughs (
                breakthrough_id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                channel_id TEXT,
                title TEXT,
                published_at TEXT,
                view_count INTEGER,
                prev10_avg_views REAL,
                threshold REAL,
                ratio REAL,
                is_first_breakthrough INTEGER DEFAULT 0,
                position_in_sequence INTEGER,
                FOREIGN KEY (video_id) REFERENCES videos(video_id),
                FOREIGN KEY (channel_id) REFERENCES channels_discovered(channel_id)
            )
        """)

        # Topics table (for breakthrough videos)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS video_topics (
                video_id TEXT,
                topic_method TEXT,
                topic_label TEXT,
                confidence REAL,
                PRIMARY KEY (video_id, topic_method, topic_label),
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            )
        """)

        # Progress tracking
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)

        # Create indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_videos_published ON videos(published_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_breakthroughs_channel ON breakthroughs(channel_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_breakthroughs_first ON breakthroughs(is_first_breakthrough)")

        self.conn.commit()

    def insert_discovered_channel(self, channel: Dict[str, Any]):
        """Insert a discovered channel."""
        self.conn.execute("""
            INSERT OR REPLACE INTO channels_discovered
            (channel_id, channel_title, description, published_at, subscriber_count,
             video_count, view_count, uploads_playlist_id, discovered_via_query,
             discovered_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            channel['channel_id'],
            channel.get('channel_title', ''),
            channel.get('description', ''),
            channel.get('published_at', ''),
            channel.get('subscriber_count', 0),
            channel.get('video_count', 0),
            channel.get('view_count', 0),
            channel.get('uploads_playlist_id', ''),
            channel.get('discovered_via_query', ''),
            datetime.utcnow().isoformat(),
            channel.get('published_at', '')
        ))
        self.conn.commit()

    def insert_filtered_channel(self, channel: Dict[str, Any], passed: bool = True, reason: str = ""):
        """Insert a filtered channel."""
        self.conn.execute("""
            INSERT OR REPLACE INTO channels_filtered
            (channel_id, channel_title, description, published_at, subscriber_count,
             video_count, view_count, uploads_playlist_id, discovered_via_query,
             filter_reason, passed_filter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            channel['channel_id'],
            channel.get('channel_title', ''),
            channel.get('description', ''),
            channel.get('published_at', ''),
            channel.get('subscriber_count', 0),
            channel.get('video_count', 0),
            channel.get('view_count', 0),
            channel.get('uploads_playlist_id', ''),
            channel.get('discovered_via_query', ''),
            reason,
            1 if passed else 0
        ))
        self.conn.commit()

    def insert_eligible_channel(self, channel_id: str, channel_title: str,
                                 qualifying_count: int, is_eligible: bool):
        """Insert preflight eligibility result."""
        self.conn.execute("""
            INSERT OR REPLACE INTO channels_eligible
            (channel_id, channel_title, qualifying_longform_count_in_newest_100,
             is_eligible, preflight_checked_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            channel_id,
            channel_title,
            qualifying_count,
            1 if is_eligible else 0,
            datetime.utcnow().isoformat()
        ))
        self.conn.commit()

    def insert_video(self, video: Dict[str, Any]):
        """Insert a video record."""
        self.conn.execute("""
            INSERT OR REPLACE INTO videos
            (video_id, channel_id, title, description, published_at, duration_sec,
             view_count, like_count, comment_count, tags, category_id, default_language,
             default_audio_language, caption, made_for_kids, topic_categories,
             days_since_publish, views_per_day, like_rate_per_1k, comment_rate_per_1k,
             is_qualifying)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video['video_id'],
            video['channel_id'],
            video.get('title', ''),
            video.get('description', ''),
            video.get('published_at', ''),
            video.get('duration_sec', 0),
            video.get('view_count', 0),
            video.get('like_count', 0),
            video.get('comment_count', 0),
            json.dumps(video.get('tags', [])),
            video.get('category_id', ''),
            video.get('default_language', ''),
            video.get('default_audio_language', ''),
            video.get('caption', 0),
            video.get('made_for_kids', 0),
            json.dumps(video.get('topic_categories', [])),
            video.get('days_since_publish', 0),
            video.get('views_per_day', 0),
            video.get('like_rate_per_1k', 0),
            video.get('comment_rate_per_1k', 0),
            video.get('is_qualifying', 0)
        ))
        self.conn.commit()

    def insert_breakthrough(self, breakthrough: Dict[str, Any]):
        """Insert a breakthrough record."""
        cursor = self.conn.execute("""
            INSERT INTO breakthroughs
            (video_id, channel_id, title, published_at, view_count, prev10_avg_views,
             threshold, ratio, is_first_breakthrough, position_in_sequence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            breakthrough['video_id'],
            breakthrough['channel_id'],
            breakthrough.get('title', ''),
            breakthrough.get('published_at', ''),
            breakthrough.get('view_count', 0),
            breakthrough.get('prev10_avg_views', 0),
            breakthrough.get('threshold', 0),
            breakthrough.get('ratio', 0),
            breakthrough.get('is_first_breakthrough', 0),
            breakthrough.get('position_in_sequence', 0)
        ))
        self.conn.commit()
        return cursor.lastrowid

    def insert_video_topic(self, video_id: str, topic_method: str,
                           topic_label: str, confidence: float = 1.0):
        """Insert a video topic label."""
        self.conn.execute("""
            INSERT OR REPLACE INTO video_topics
            (video_id, topic_method, topic_label, confidence)
            VALUES (?, ?, ?, ?)
        """, (video_id, topic_method, topic_label, confidence))
        self.conn.commit()

    def get_discovered_channels(self) -> List[Dict[str, Any]]:
        """Get all discovered channels."""
        cursor = self.conn.execute("SELECT * FROM channels_discovered")
        return [dict(row) for row in cursor.fetchall()]

    def get_filtered_channels(self, passed_only: bool = True) -> List[Dict[str, Any]]:
        """Get filtered channels."""
        if passed_only:
            cursor = self.conn.execute("SELECT * FROM channels_filtered WHERE passed_filter = 1")
        else:
            cursor = self.conn.execute("SELECT * FROM channels_filtered")
        return [dict(row) for row in cursor.fetchall()]

    def get_eligible_channels(self) -> List[Dict[str, Any]]:
        """Get eligible channels."""
        cursor = self.conn.execute("SELECT * FROM channels_eligible WHERE is_eligible = 1")
        return [dict(row) for row in cursor.fetchall()]

    def get_videos_for_channel(self, channel_id: str, qualifying_only: bool = False) -> List[Dict[str, Any]]:
        """Get all videos for a channel."""
        if qualifying_only:
            cursor = self.conn.execute(
                "SELECT * FROM videos WHERE channel_id = ? AND is_qualifying = 1 ORDER BY published_at",
                (channel_id,)
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM videos WHERE channel_id = ? ORDER BY published_at",
                (channel_id,)
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_all_breakthroughs(self) -> List[Dict[str, Any]]:
        """Get all breakthrough records."""
        cursor = self.conn.execute("SELECT * FROM breakthroughs ORDER BY published_at")
        return [dict(row) for row in cursor.fetchall()]

    def get_first_breakthroughs(self) -> List[Dict[str, Any]]:
        """Get first breakthrough per channel."""
        cursor = self.conn.execute(
            "SELECT * FROM breakthroughs WHERE is_first_breakthrough = 1 ORDER BY published_at"
        )
        return [dict(row) for row in cursor.fetchall()]

    def set_progress(self, key: str, value: str):
        """Set a progress marker."""
        self.conn.execute("""
            INSERT OR REPLACE INTO progress (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.utcnow().isoformat()))
        self.conn.commit()

    def get_progress(self, key: str) -> Optional[str]:
        """Get a progress marker."""
        cursor = self.conn.execute("SELECT value FROM progress WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else None

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
