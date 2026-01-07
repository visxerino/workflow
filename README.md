# YouTube Breakthrough Research Pipeline

A quota-optimized pipeline for discovering and analyzing breakthrough patterns in new YouTube channels using YouTube Data API v3.

## 🎯 Goal

Identify which topics, titles, and patterns correlate with early breakthroughs for longform "for sleep" documentary channels created after **2025-07-15**.

## 🏗️ Architecture

### Two-Pass Design (Quota Optimized)

**PASS 1: Discovery + Prefilter** (Cheap)
- Search for candidate channels (search.list: 100 units/call)
- Apply cohort and cheap filters
- Preflight eligibility check (only newest 100 videos)

**PASS 2: Deep Scrape** (Only Eligible Channels)
- Fetch ALL uploads for eligible channels
- Full video metadata extraction
- Breakthrough calculation
- Topic labeling
- Pattern analysis

### Quota Costs
- `search.list`: 100 units/call (expensive!)
- `channels.list`: 1 unit/call
- `playlistItems.list`: 1 unit/call
- `videos.list`: 1 unit/call

**Default target: <10,000 units/day**

## 📋 Requirements

### API Key
Get a YouTube Data API v3 key from [Google Cloud Console](https://console.developers.google.com/apis/credentials).

### Python Dependencies
```bash
pip install -r requirements.txt
```

### Environment Setup
```bash
cp .env.example .env
# Edit .env and add your API key
```

## 🚀 Quick Start

### Full Pipeline (Recommended)
```bash
python main.py run_all
```

This runs all steps in sequence:
1. Discovery
2. Preflight
3. Deep fetch
4. Analysis
5. Export

### Individual Steps

#### Step 1: Discovery
```bash
python main.py discover \
  --queries queries.txt \
  --target-channels 1200 \
  --pages-per-query 1
```

Discovers ~1,200 unique channels by searching with seed queries. Only fetches 1 page per query by default (50 results) to minimize quota usage.

**Filters applied:**
- Channel created >= 2025-07-15 (HARD)
- Video count <= 500 (skip shorts spam)
- Subscribers <= 500,000 (skip outliers)

#### Step 2: Preflight Eligibility
```bash
python main.py preflight \
  --max-channels 1200 \
  --min-duration-min 20 \
  --min-qualifying 10
```

Quickly scans newest 100 videos per channel. Only channels with >=10 qualifying longform videos (>=20 min, not made for kids) are marked eligible.

**Why?** Prevents wasting quota on channels that can't meet breakthrough criteria.

#### Step 3: Deep Fetch
```bash
python main.py deep_fetch \
  --max-deep-channels 400 \
  --min-duration-min 20 \
  --max-upload-items 300
```

Deep scrapes eligible channels:
- Fetches up to 300 uploads per channel (prevents runaway quota)
- Full video metadata (title, description, tags, stats, duration, topics)
- Computes derived fields (views_per_day, like_rate, etc.)

#### Step 4: Analysis
```bash
python main.py analyze \
  --noise-threshold 50 \
  --min-threshold 2000 \
  --n-clusters 12
```

Runs three analyses:

1. **Breakthrough Detection**
   - For each qualifying video (sorted oldest→newest)
   - Needs >=10 prior qualifying videos
   - `prev10_avg_views` = mean(prior 10 views)
   - If `prev10_avg_views < 50`: skip (noise)
   - `threshold = max(2000, 10 × prev10_avg_views)`
   - Breakthrough if `views >= threshold`

2. **Topic Labeling** (3 methods)
   - Rule-based buckets (ocean, true_crime, space, etc.)
   - TF-IDF + KMeans clustering on titles
   - API `topicDetails.topicCategories`

3. **Title Pattern Analysis** (with control group!)
   - Compare breakthrough titles vs previous 10
   - Patterns: question marks, colons, intensity words, authority words, numbers, etc.
   - Calculate uplift ratios

#### Step 5: Export
```bash
python main.py export --out-dir ./out
```

Exports CSV files:
- `channels_discovered.csv`
- `channels_filtered.csv`
- `channels_eligible.csv`
- `videos_qualifying.csv`
- `breakthroughs_all.csv`
- `breakthroughs_first_per_channel.csv`
- `breakthroughs_with_topics.csv`
- `title_pattern_uplift.csv`

## 📊 Output Files

### channels_discovered.csv
All channels found via search, before filtering.

### channels_filtered.csv
Channels after cohort cutoff + cheap filters.

### channels_eligible.csv
Channels with >=10 qualifying longform videos in newest 100.

### videos_qualifying.csv
All qualifying videos (duration >= min, not made for kids).

### breakthroughs_all.csv
All breakthrough events detected.

Columns:
- `video_id`, `channel_id`, `title`, `published_at`
- `view_count`, `prev10_avg_views`, `threshold`, `ratio`
- `is_first_breakthrough`, `position_in_sequence`

### breakthroughs_first_per_channel.csv
First breakthrough per channel only.

### breakthroughs_with_topics.csv
Breakthroughs with topic labels aggregated.

### title_pattern_uplift.csv
Pattern analysis comparing breakthrough vs previous 10 titles.

Columns:
- `pattern` (e.g., contains_question_mark)
- `breakthrough_rate`, `prev10_rate`
- `uplift_ratio` (breakthrough_rate / prev10_rate)

## 🔧 Configuration Options

### Discovery
- `--target-channels`: Target number of unique channels (default: 1200)
- `--pages-per-query`: Pages per query (default: 1, max: varies)
- `--max-video-count`: Filter out channels with >N videos (default: 500)
- `--max-subscribers`: Filter out channels with >N subs (default: 500000)

### Preflight
- `--min-duration-min`: Minimum video duration in minutes (default: 20)
- `--min-qualifying`: Minimum qualifying videos for eligibility (default: 10)

### Deep Fetch
- `--max-deep-channels`: Max eligible channels to scrape (default: 400)
- `--max-upload-items`: Max uploads per channel (default: 300)

### Analysis
- `--noise-threshold`: Min prev10_avg_views (default: 50)
- `--min-threshold`: Min absolute threshold (default: 2000)
- `--n-clusters`: Number of title clusters (default: 12)

### Global
- `--db`: Database file path (default: youtube_research.db)
- `--no-cache`: Disable API response caching

## 🎛️ Advanced Usage

### Resume-Safe Operations
All data is stored in SQLite. If a step fails, just re-run it. Already-fetched data is cached.

### Disable Caching
```bash
python main.py --no-cache discover
```

### Custom Queries
Edit `queries.txt` to add/remove search queries. One query per line. Lines starting with `#` are comments.

### Adjust Quota Budget

**To reduce quota:**
- Decrease `--target-channels`
- Use `--pages-per-query 1` (default)
- Decrease `--max-deep-channels`
- Decrease `--max-upload-items`

**To increase coverage:**
- Increase `--pages-per-query` (expensive!)
- Increase `--max-deep-channels`
- Add more queries to `queries.txt`

## 📈 Expected Quota Usage

### Conservative (Default)
- **Discovery**: ~35 queries × 1 page × 100 units = 3,500 units
- **Channel metadata**: 1,200 / 50 × 1 = 24 units
- **Preflight**: 1,200 × 2 pages × 1 + 1,200 × 2 batches × 1 = 4,800 units
- **Deep fetch**: 400 channels × 6 pages × 1 + 400 × 6 batches × 1 = 4,800 units
- **Total**: ~13,000 units

### Aggressive (High Coverage)
- Discovery: 50 queries × 2 pages = 10,000 units
- Preflight: same
- Deep fetch: 800 channels = 9,600 units
- **Total**: ~24,000 units

YouTube API default quota: **10,000 units/day**. Request increase if needed.

## 🧩 Module Overview

### youtube_api.py
API wrapper with:
- SHA256-based response caching
- Exponential backoff retry (429, 5xx)
- Token bucket rate limiting
- Quota tracking
- Field filtering for payload reduction

### db.py
SQLite schema and operations. Tables:
- `channels_discovered`, `channels_filtered`, `channels_eligible`
- `videos`
- `breakthroughs`
- `video_topics`
- `progress` (resume markers)

### discover.py
PASS 1A+1B:
- Load queries
- Search for videos (expensive!)
- Dedupe channel IDs
- Fetch channel metadata
- Apply cohort + cheap filters

### preflight.py
PASS 1C:
- Fetch newest 100 videos per channel
- Count qualifying longform
- Mark eligible if >=10 qualifying

### fetch.py
PASS 2:
- Fetch ALL uploads (up to max)
- Get full video metadata
- Compute derived fields (views_per_day, rates)
- Filter to qualifying only

### breakthroughs.py
Breakthrough detection:
- Sort qualifying videos oldest→newest
- Rolling 10-video average
- Threshold calculation
- Breakthrough detection
- Mark first breakthrough

### topics.py
3 topic labeling methods:
- Rule-based (keywords → buckets)
- TF-IDF + KMeans clustering
- API `topicCategories`

### patterns.py
Title pattern analysis:
- Extract patterns (?, :, intensity words, etc.)
- Compare breakthrough vs prev10
- Calculate uplift ratios

### main.py
CLI with Click:
- Subcommands for each step
- Parameter validation
- Progress reporting
- CSV export

## 🛡️ Best Practices

1. **Start small**: Run with `--target-channels 100` first to test.
2. **Monitor quota**: Check `api.get_quota_used()` outputs.
3. **Use caching**: Don't use `--no-cache` unless necessary.
4. **Incremental runs**: Run discovery, check results, then proceed.
5. **Backup database**: Copy `youtube_research.db` before major changes.

## 🐛 Troubleshooting

### "YouTube API key not found"
Create `.env` file with `YOUTUBE_API_KEY=your_key`.

### HTTP 429 (Rate Limited)
Pipeline automatically retries with exponential backoff. If persistent, reduce concurrency or increase delays in `youtube_api.py`.

### Quota Exceeded
Wait until quota resets (midnight PT) or request increase from Google Cloud Console.

### Empty Results
- Check queries.txt has valid queries
- Verify cohort cutoff date (2025-07-15) matches your target
- Check API key has YouTube Data API v3 enabled

## 📚 Research Questions

This pipeline helps answer:

1. **Which topics breakthrough fastest?**
   - Analyze `breakthroughs_with_topics.csv`
   - Group by topic, compute median `position_in_sequence`

2. **What title patterns predict breakthroughs?**
   - Review `title_pattern_uplift.csv`
   - Look for high uplift ratios (>1.5x)

3. **What's the typical breakthrough ratio?**
   - Analyze `ratio` distribution in `breakthroughs_all.csv`

4. **How many videos until first breakthrough?**
   - Analyze `position_in_sequence` in `breakthroughs_first_per_channel.csv`

5. **Which clusters perform best?**
   - Join breakthroughs with kmeans topics
   - Compute breakthrough rate per cluster

## 📜 License

MIT License - feel free to modify and extend!

## 🤝 Contributing

Suggestions for improvement:
- Add more topic buckets to `topics.py`
- Enhance pattern detection in `patterns.py`
- Optimize quota usage further
- Add visualization scripts

## 📞 Support

For issues with:
- **YouTube API**: Check [official docs](https://developers.google.com/youtube/v3)
- **Pipeline bugs**: Review code comments and error messages
- **Quota limits**: Request increase via Google Cloud Console

---

**Happy researching!** 🚀
