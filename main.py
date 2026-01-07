#!/usr/bin/env python3
"""
YouTube Breakthrough Research Pipeline
Main CLI entry point with subcommands.
"""
import click
import os
import csv
import json
from pathlib import Path

from youtube_api import YouTubeAPI, get_api_key
from db import Database
from discover import discover_channels, filter_channels
from preflight import check_eligibility
from fetch import deep_fetch_channels
from breakthroughs import calculate_breakthroughs
from topics import label_all_topics
from patterns import analyze_title_patterns


@click.group()
@click.option('--db', default='youtube_research.db', help='Database file path')
@click.option('--no-cache', is_flag=True, help='Disable API response caching')
@click.pass_context
def cli(ctx, db, no_cache):
    """YouTube Breakthrough Research Pipeline - Quota Optimized"""
    ctx.ensure_object(dict)
    ctx.obj['db_path'] = db
    ctx.obj['use_cache'] = not no_cache


@cli.command()
@click.option('--queries', default='queries.txt', help='Query file path')
@click.option('--target-channels', default=1200, help='Target number of unique channels')
@click.option('--pages-per-query', default=1, help='Pages to fetch per query (quota intensive!)')
@click.option('--max-video-count', default=500, help='Max video count filter')
@click.option('--max-subscribers', default=500000, help='Max subscriber count filter')
@click.pass_context
def discover(ctx, queries, target_channels, pages_per_query, max_video_count, max_subscribers):
    """PASS 1: Discover and filter channels"""
    db_path = ctx.obj['db_path']
    use_cache = ctx.obj['use_cache']

    try:
        api_key = get_api_key()
        api = YouTubeAPI(api_key, use_cache=use_cache)
        db = Database(db_path)

        print("\n" + "=" * 60)
        print("PASS 1A: CHANNEL DISCOVERY")
        print("=" * 60)

        discovered = discover_channels(
            api, db, queries,
            target_channels=target_channels,
            pages_per_query=pages_per_query
        )

        print("\n" + "=" * 60)
        print("PASS 1B: CHANNEL FILTERING")
        print("=" * 60)

        filtered = filter_channels(
            api, db,
            max_video_count=max_video_count,
            max_subscriber_count=max_subscribers
        )

        db.close()

        print("\n" + "=" * 60)
        print("DISCOVERY COMPLETE")
        print(f"Discovered: {discovered}")
        print(f"Passed filters: {filtered}")
        print(f"Quota used: {api.get_quota_used()} units")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        raise


@cli.command()
@click.option('--max-channels', default=1200, help='Max channels to check')
@click.option('--min-duration-min', default=20, help='Min duration in minutes')
@click.option('--min-qualifying', default=10, help='Min qualifying videos for eligibility')
@click.pass_context
def preflight(ctx, max_channels, min_duration_min, min_qualifying):
    """PASS 1C: Preflight eligibility check"""
    db_path = ctx.obj['db_path']
    use_cache = ctx.obj['use_cache']

    try:
        api_key = get_api_key()
        api = YouTubeAPI(api_key, use_cache=use_cache)
        db = Database(db_path)

        print("\n" + "=" * 60)
        print("PASS 1C: PREFLIGHT ELIGIBILITY CHECK")
        print("=" * 60)

        eligible = check_eligibility(
            api, db,
            min_duration_min=min_duration_min,
            min_qualifying=min_qualifying,
            max_channels=max_channels
        )

        db.close()

        print("\n" + "=" * 60)
        print("PREFLIGHT COMPLETE")
        print(f"Eligible channels: {eligible}")
        print(f"Quota used: {api.get_quota_used()} units")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        raise


@cli.command()
@click.option('--max-deep-channels', default=400, help='Max eligible channels to deep scrape')
@click.option('--min-duration-min', default=20, help='Min duration in minutes')
@click.option('--max-upload-items', default=300, help='Max upload items per channel')
@click.pass_context
def deep_fetch(ctx, max_deep_channels, min_duration_min, max_upload_items):
    """PASS 2: Deep fetch eligible channels"""
    db_path = ctx.obj['db_path']
    use_cache = ctx.obj['use_cache']

    try:
        api_key = get_api_key()
        api = YouTubeAPI(api_key, use_cache=use_cache)
        db = Database(db_path)

        print("\n" + "=" * 60)
        print("PASS 2: DEEP FETCH")
        print("=" * 60)

        scraped = deep_fetch_channels(
            api, db,
            max_deep_channels=max_deep_channels,
            max_upload_items=max_upload_items,
            min_duration_min=min_duration_min
        )

        db.close()

        print("\n" + "=" * 60)
        print("DEEP FETCH COMPLETE")
        print(f"Channels scraped: {scraped}")
        print(f"Quota used: {api.get_quota_used()} units")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        raise


@cli.command()
@click.option('--noise-threshold', default=50, help='Minimum prev10_avg_views threshold')
@click.option('--min-threshold', default=2000, help='Minimum absolute threshold')
@click.option('--n-clusters', default=12, help='Number of title clusters')
@click.pass_context
def analyze(ctx, noise_threshold, min_threshold, n_clusters):
    """Calculate breakthroughs, topics, and patterns"""
    db_path = ctx.obj['db_path']

    try:
        db = Database(db_path)

        print("\n" + "=" * 60)
        print("BREAKTHROUGH CALCULATION")
        print("=" * 60)

        breakthroughs = calculate_breakthroughs(
            db,
            noise_threshold=noise_threshold,
            min_threshold=min_threshold
        )

        print("\n" + "=" * 60)
        print("TOPIC LABELING")
        print("=" * 60)

        label_all_topics(db, n_clusters=n_clusters)

        print("\n" + "=" * 60)
        print("PATTERN ANALYSIS")
        print("=" * 60)

        pattern_results = analyze_title_patterns(db)

        db.close()

        print("\n" + "=" * 60)
        print("ANALYSIS COMPLETE")
        print(f"Breakthroughs found: {breakthroughs}")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        raise


@cli.command()
@click.option('--out-dir', default='./out', help='Output directory for CSVs')
@click.pass_context
def export(ctx, out_dir):
    """Export all data to CSV files"""
    db_path = ctx.obj['db_path']

    try:
        db = Database(db_path)
        out_path = Path(out_dir)
        out_path.mkdir(exist_ok=True)

        print(f"\nExporting to {out_path}...")

        # Export channels_discovered
        _export_table(db, 'channels_discovered', out_path / 'channels_discovered.csv')

        # Export channels_filtered
        _export_table(db, 'channels_filtered', out_path / 'channels_filtered.csv')

        # Export channels_eligible
        _export_table(db, 'channels_eligible', out_path / 'channels_eligible.csv')

        # Export videos (qualifying only)
        _export_videos_qualifying(db, out_path / 'videos_qualifying.csv')

        # Export all breakthroughs
        _export_table(db, 'breakthroughs', out_path / 'breakthroughs_all.csv')

        # Export first breakthroughs
        _export_first_breakthroughs(db, out_path / 'breakthroughs_first_per_channel.csv')

        # Export breakthroughs with topics
        _export_breakthroughs_with_topics(db, out_path / 'breakthroughs_with_topics.csv')

        # Export title pattern uplift
        _export_pattern_uplift(db, out_path / 'title_pattern_uplift.csv')

        db.close()

        print("\nExport complete!")

    except Exception as e:
        print(f"\nError: {e}")
        raise


def _export_table(db: Database, table_name: str, output_path: Path):
    """Generic table export."""
    cursor = db.conn.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    if not rows:
        print(f"  {table_name}: No data")
        return

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    print(f"  {table_name}: {len(rows)} rows -> {output_path.name}")


def _export_videos_qualifying(db: Database, output_path: Path):
    """Export qualifying videos only."""
    cursor = db.conn.execute("SELECT * FROM videos WHERE is_qualifying = 1")
    rows = cursor.fetchall()

    if not rows:
        print(f"  videos_qualifying: No data")
        return

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    print(f"  videos_qualifying: {len(rows)} rows -> {output_path.name}")


def _export_first_breakthroughs(db: Database, output_path: Path):
    """Export first breakthroughs per channel."""
    cursor = db.conn.execute("SELECT * FROM breakthroughs WHERE is_first_breakthrough = 1")
    rows = cursor.fetchall()

    if not rows:
        print(f"  breakthroughs_first: No data")
        return

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    print(f"  breakthroughs_first: {len(rows)} rows -> {output_path.name}")


def _export_breakthroughs_with_topics(db: Database, output_path: Path):
    """Export breakthroughs with topic labels."""
    cursor = db.conn.execute("""
        SELECT b.*,
               GROUP_CONCAT(DISTINCT vt.topic_label) as topics
        FROM breakthroughs b
        LEFT JOIN video_topics vt ON b.video_id = vt.video_id
        GROUP BY b.breakthrough_id
    """)
    rows = cursor.fetchall()

    if not rows:
        print(f"  breakthroughs_with_topics: No data")
        return

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    print(f"  breakthroughs_with_topics: {len(rows)} rows -> {output_path.name}")


def _export_pattern_uplift(db: Database, output_path: Path):
    """Export title pattern uplift analysis."""
    from patterns import analyze_title_patterns

    results = analyze_title_patterns(db)
    patterns = results.get('patterns', [])

    if not patterns:
        print(f"  title_pattern_uplift: No data")
        return

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=patterns[0].keys())
        writer.writeheader()
        for pattern in patterns:
            writer.writerow(pattern)

    print(f"  title_pattern_uplift: {len(patterns)} rows -> {output_path.name}")


@cli.command()
@click.pass_context
def run_all(ctx):
    """Run full pipeline: discover -> preflight -> deep_fetch -> analyze -> export"""
    print("\n" + "=" * 60)
    print("RUNNING FULL PIPELINE")
    print("=" * 60)

    # Pass 1A+1B: Discovery and filtering
    ctx.invoke(discover)

    # Pass 1C: Preflight
    ctx.invoke(preflight)

    # Pass 2: Deep fetch
    ctx.invoke(deep_fetch)

    # Analysis
    ctx.invoke(analyze)

    # Export
    ctx.invoke(export)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE!")
    print("=" * 60)


if __name__ == '__main__':
    cli(obj={})
