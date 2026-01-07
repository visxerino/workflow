"""
Title pattern analysis with control group.
Compare breakthrough titles vs previous 10 qualifying titles.
"""
import re
from typing import List, Dict, Any
from collections import defaultdict
from tqdm import tqdm

from db import Database


# Pattern detection functions
def contains_question_mark(title: str) -> bool:
    """Check if title contains ?"""
    return '?' in title


def contains_pipe(title: str) -> bool:
    """Check if title contains |"""
    return '|' in title


def contains_colon(title: str) -> bool:
    """Check if title contains :"""
    return ':' in title


def contains_intensity_words(title: str) -> bool:
    """Check if title contains intensity/shock words."""
    intensity_words = [
        'terrifying', 'disturbing', 'brutal', 'dangerous', 'shocked',
        'impossible', 'secrets', 'hidden', 'erased', 'unexplained',
        "can't explain", 'never happen again', 'unbelievable', 'shocking',
        'horrifying', 'devastating', 'deadly', 'catastrophic', 'mysterious',
        'bizarre', 'strange', 'weird', 'insane', 'extreme', 'ultimate'
    ]
    title_lower = title.lower()
    return any(word in title_lower for word in intensity_words)


def contains_authority_words(title: str) -> bool:
    """Check if title contains authority/expert words."""
    authority_words = [
        'scientists', 'investigators', 'physicist', 'harvard', 'MIT',
        'experts', 'researchers', 'professor', 'doctor', 'NASA',
        'study', 'research', 'official', 'government', 'military'
    ]
    title_lower = title.lower()
    return any(word in title_lower for word in authority_words)


def contains_numbers_or_years(title: str) -> bool:
    """Check if title contains numbers or years."""
    # Match 4-digit years or other numbers
    return bool(re.search(r'\b\d{4}\b|\b\d+\b', title))


def contains_all_caps_words(title: str) -> bool:
    """Check if title contains words in ALL CAPS."""
    words = title.split()
    return any(word.isupper() and len(word) > 2 for word in words)


def contains_brackets(title: str) -> bool:
    """Check if title contains brackets []"""
    return '[' in title or ']' in title


def contains_parentheses(title: str) -> bool:
    """Check if title contains parentheses ()"""
    return '(' in title or ')' in title


# Pattern extractors
PATTERN_EXTRACTORS = {
    'contains_question_mark': contains_question_mark,
    'contains_pipe': contains_pipe,
    'contains_colon': contains_colon,
    'contains_intensity_words': contains_intensity_words,
    'contains_authority_words': contains_authority_words,
    'contains_numbers_or_years': contains_numbers_or_years,
    'contains_all_caps_words': contains_all_caps_words,
    'contains_brackets': contains_brackets,
    'contains_parentheses': contains_parentheses,
}


def extract_patterns(title: str) -> Dict[str, bool]:
    """Extract all patterns from a title."""
    patterns = {}
    for pattern_name, extractor in PATTERN_EXTRACTORS.items():
        patterns[pattern_name] = extractor(title)
    return patterns


def analyze_title_patterns(db: Database) -> Dict[str, Any]:
    """
    Analyze title patterns comparing breakthroughs vs previous 10 videos.

    Returns:
        Dict with pattern statistics and uplift ratios
    """
    print("\n=== TITLE PATTERN ANALYSIS ===")

    breakthroughs = db.get_all_breakthroughs()
    print(f"Analyzing {len(breakthroughs)} breakthroughs...")

    # Collect pattern counts
    breakthrough_counts = defaultdict(int)
    breakthrough_total = 0

    prev10_counts = defaultdict(int)
    prev10_total = 0

    for bt in tqdm(breakthroughs, desc="Analyzing patterns"):
        video_id = bt['video_id']
        channel_id = bt['channel_id']
        position = bt['position_in_sequence']

        # Get all qualifying videos for this channel
        videos = db.get_videos_for_channel(channel_id, qualifying_only=True)

        if position < 10:
            continue  # Should not happen, but safety check

        # Current breakthrough video
        current_video = videos[position]
        current_title = current_video['title']
        current_patterns = extract_patterns(current_title)

        for pattern_name, has_pattern in current_patterns.items():
            if has_pattern:
                breakthrough_counts[pattern_name] += 1
        breakthrough_total += 1

        # Previous 10 qualifying videos
        prev_10_videos = videos[position-10:position]
        for prev_video in prev_10_videos:
            prev_title = prev_video['title']
            prev_patterns = extract_patterns(prev_title)

            for pattern_name, has_pattern in prev_patterns.items():
                if has_pattern:
                    prev10_counts[pattern_name] += 1
            prev10_total += 1

    # Calculate rates and uplift
    results = []

    for pattern_name in PATTERN_EXTRACTORS.keys():
        bt_count = breakthrough_counts[pattern_name]
        prev_count = prev10_counts[pattern_name]

        bt_rate = (bt_count / breakthrough_total) if breakthrough_total > 0 else 0
        prev_rate = (prev_count / prev10_total) if prev10_total > 0 else 0

        uplift_ratio = (bt_rate / prev_rate) if prev_rate > 0 else 0

        results.append({
            'pattern': pattern_name,
            'breakthrough_count': bt_count,
            'breakthrough_total': breakthrough_total,
            'breakthrough_rate': bt_rate,
            'prev10_count': prev_count,
            'prev10_total': prev10_total,
            'prev10_rate': prev_rate,
            'uplift_ratio': uplift_ratio
        })

    # Sort by uplift ratio descending
    results.sort(key=lambda x: x['uplift_ratio'], reverse=True)

    print("\n=== PATTERN UPLIFT (Breakthrough vs Previous 10) ===")
    print(f"{'Pattern':<30} {'BT Rate':<10} {'Prev Rate':<10} {'Uplift':<10}")
    print("-" * 60)
    for r in results:
        print(f"{r['pattern']:<30} {r['breakthrough_rate']:.1%}     "
              f"{r['prev10_rate']:.1%}      {r['uplift_ratio']:.2f}x")

    return {
        'patterns': results,
        'breakthrough_total': breakthrough_total,
        'prev10_total': prev10_total
    }
