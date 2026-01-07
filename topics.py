"""
Topic labeling for breakthrough videos.
3 methods:
1. Rule-based bucket tagger (title + description + tags)
2. TF-IDF + KMeans clustering on breakthrough titles
3. Preserve topicDetails.topicCategories from API
"""
import re
import json
from typing import List, Dict, Any, Set
from collections import Counter
from tqdm import tqdm

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

from db import Database


# Rule-based topic keywords
TOPIC_KEYWORDS = {
    'ocean_abyss': [
        'ocean', 'abyss', 'deep sea', 'mariana', 'underwater', 'marine',
        'submarine', 'depths', 'seafloor', 'trench', 'diving'
    ],
    'true_crime': [
        'murder', 'killer', 'crime', 'detective', 'investigation', 'criminal',
        'FBI', 'serial killer', 'unsolved', 'mystery death', 'homicide'
    ],
    'prison': [
        'prison', 'jail', 'inmate', 'correctional', 'behind bars', 'convict',
        'sentenced', 'maximum security', 'cell block', 'lockdown'
    ],
    'hidden_history': [
        'forgotten', 'erased', 'hidden history', 'lost', 'suppressed',
        'covered up', 'untold story', 'buried', 'rediscovered', 'ancient'
    ],
    'space_shock': [
        'space', 'NASA', 'universe', 'galaxy', 'black hole', 'asteroid',
        'planet', 'cosmic', 'telescope', 'astronomy', 'alien', 'mars'
    ],
    'earth_mystery': [
        'bermuda', 'unexplained', 'phenomenon', 'paranormal', 'mysterious',
        'strange', 'bizarre', 'anomaly', 'supernatural', 'enigma'
    ],
    'wildlife': [
        'animal', 'wildlife', 'predator', 'species', 'nature', 'jungle',
        'safari', 'creature', 'beast', 'wild', 'habitat', 'endangered'
    ],
    'psychology_brain': [
        'psychology', 'brain', 'mind', 'mental', 'cognitive', 'neuroscience',
        'behavior', 'consciousness', 'memory', 'intelligence', 'psychologist'
    ],
    'war_history': [
        'war', 'battle', 'military', 'soldier', 'combat', 'army', 'navy',
        'world war', 'veteran', 'invasion', 'operation', 'regiment'
    ],
    'disaster': [
        'disaster', 'catastrophe', 'tragedy', 'accident', 'crash', 'collapse',
        'explosion', 'incident', 'emergency', 'evacuation', 'survivor'
    ],
    'conspiracy': [
        'conspiracy', 'cover-up', 'secret', 'classified', 'government secret',
        'illuminati', 'hidden agenda', 'whistleblower', 'leaked'
    ],
    'technology': [
        'technology', 'AI', 'robot', 'computer', 'silicon valley', 'innovation',
        'algorithm', 'digital', 'cyber', 'hacker', 'invention'
    ]
}


def rule_based_topics(text: str, tags: List[str] = None) -> List[str]:
    """
    Apply rule-based topic detection.

    Args:
        text: Combined text (title + description)
        tags: Video tags

    Returns:
        List of matched topic labels
    """
    text_lower = text.lower()
    tags_lower = [t.lower() for t in (tags or [])]
    combined = text_lower + ' ' + ' '.join(tags_lower)

    matched_topics = []

    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in combined:
                matched_topics.append(topic)
                break  # Only count once per topic

    return matched_topics


def cluster_breakthrough_titles(db: Database, n_clusters: int = 12) -> Dict[str, int]:
    """
    Cluster breakthrough titles using TF-IDF + KMeans.

    Args:
        db: Database instance
        n_clusters: Number of clusters

    Returns:
        Dict mapping video_id -> cluster_id
    """
    breakthroughs = db.get_all_breakthroughs()

    if len(breakthroughs) < n_clusters:
        print(f"Not enough breakthroughs ({len(breakthroughs)}) for {n_clusters} clusters")
        return {}

    print(f"\nClustering {len(breakthroughs)} breakthrough titles into {n_clusters} clusters...")

    # Extract titles
    video_ids = []
    titles = []
    for bt in breakthroughs:
        video_ids.append(bt['video_id'])
        titles.append(bt['title'] or '')

    # TF-IDF vectorization
    vectorizer = TfidfVectorizer(
        max_features=200,
        stop_words='english',
        ngram_range=(1, 2),
        min_df=2
    )

    try:
        X = vectorizer.fit_transform(titles)

        # KMeans clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        cluster_labels = kmeans.fit_predict(X)

        # Build mapping
        video_cluster_map = {}
        for video_id, cluster_id in zip(video_ids, cluster_labels):
            video_cluster_map[video_id] = int(cluster_id)

        # Print cluster sizes
        cluster_counts = Counter(cluster_labels)
        print(f"Cluster distribution: {dict(cluster_counts)}")

        return video_cluster_map

    except Exception as e:
        print(f"Clustering error: {e}")
        return {}


def label_all_topics(db: Database, n_clusters: int = 12):
    """
    Apply all topic labeling methods to breakthrough videos.

    1. Rule-based topics
    2. KMeans clustering
    3. API topic categories

    Args:
        db: Database instance
        n_clusters: Number of clusters for KMeans
    """
    print("\n=== TOPIC LABELING ===")

    breakthroughs = db.get_all_breakthroughs()
    print(f"Labeling {len(breakthroughs)} breakthrough videos...")

    # Method 1: Rule-based topics
    print("\n1. Rule-based topic detection...")
    for bt in tqdm(breakthroughs, desc="Rule-based"):
        video_id = bt['video_id']

        # Get full video data
        videos = db.conn.execute(
            "SELECT title, description, tags FROM videos WHERE video_id = ?",
            (video_id,)
        ).fetchone()

        if videos:
            title = videos['title'] or ''
            description = videos['description'] or ''
            tags_str = videos['tags'] or '[]'
            tags = json.loads(tags_str) if isinstance(tags_str, str) else tags_str

            combined_text = f"{title} {description}"
            topics = rule_based_topics(combined_text, tags)

            for topic in topics:
                db.insert_video_topic(video_id, 'rule_based', topic, confidence=1.0)

    # Method 2: KMeans clustering
    print("\n2. TF-IDF + KMeans clustering...")
    cluster_map = cluster_breakthrough_titles(db, n_clusters=n_clusters)

    for video_id, cluster_id in tqdm(cluster_map.items(), desc="Clustering"):
        cluster_label = f"cluster_{cluster_id}"
        db.insert_video_topic(video_id, 'kmeans', cluster_label, confidence=1.0)

    # Method 3: API topic categories
    print("\n3. API topic categories...")
    for bt in tqdm(breakthroughs, desc="API topics"):
        video_id = bt['video_id']

        videos = db.conn.execute(
            "SELECT topic_categories FROM videos WHERE video_id = ?",
            (video_id,)
        ).fetchone()

        if videos:
            topic_categories_str = videos['topic_categories'] or '[]'
            topic_categories = json.loads(topic_categories_str) if isinstance(topic_categories_str, str) else topic_categories_str

            for topic_url in topic_categories:
                # Extract topic name from URL (e.g., https://en.wikipedia.org/wiki/Music -> Music)
                topic_name = topic_url.split('/')[-1] if topic_url else 'unknown'
                db.insert_video_topic(video_id, 'api_category', topic_name, confidence=1.0)

    print("\nTopic labeling complete!")
