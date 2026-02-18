# Ranker & Crawler Pipeline

An automated pipeline that discovers, ranks, crawls, and filters downloadable financial documents (PDFs, Excel, etc.) from the **investor relations** pages of listed companies.

The project is fully compatible with **Windows** and **Ubuntu/Linux**.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Pipeline Flow](#pipeline-flow)
- [Data Output Format](#data-output-format)
- [Modules](#modules)
- [Usage](#usage)
- [Configuration](#configuration-env)
- [Logging](#logging)
- [Troubleshooting](#troubleshooting)

---

## Overview

Given raw search-engine results for a company (stored as JSON), this pipeline:

1. **Ranks** the URLs to find the most relevant investor-relations pages.
2. **Crawls** the top-ranked pages using a scored priority-queue BFS to build a site tree.
3. **Filters & Extracts** high-value financial documents using keyword scoring and regex pattern matching.

Each company is processed **end-to-end** (Rank -> Crawl -> Filter) before moving to the next.

---

## How It Works

```
Raw Search Results (JSON)
        │
        ▼
┌───────────────┐
│   RANKER      │  Score URLs by domain match, investor-path patterns,
│  (ranker.py)  │  page quality, and authority signals.
└───────┬───────┘
        │  Ranked JSON (top N URLs)
        ▼
┌───────────────┐
│   CRAWLER     │  Priority-queue BFS: visit pages, extract links,
│ (scraper.py)  │  stay on the same domain, collect raw downloadables.
└───────┬───────┘
        │  Crawled JSON (site tree + all raw links)
        ▼
┌───────────────┐
│  LINK FILTER  │  Scan raw links for financial keywords (Annual Report,
│(link_filter.py)│  Results, FY24) and categorize them (Useful/Uncertain/Removed).
└───────────────┘
```

---

## Project Structure

```
Ranker_Crawler/
├── .env                # Configurable settings
├── main.py             # Entry point — orchestrates the full pipeline
├── ranker.py           # URL ranking logic
├── scraper.py          # Web crawler (priority BFS)
├── link_filter.py      # [NEW] Financial link filtering & scoring logic
├── utils.py            # Helpers (I/O, URL normalization, delays)
├── logger.py           # Logging setup
├── README.md           # This file
├── logs/               # Auto-generated log files
└── DATA/
    ├── Raw/            # INPUT  — one subfolder per company with search-result JSON
    ├── Ranked/         # OUTPUT — ranked results per company
    ├── Crawled/        # OUTPUT — crawled site structure per company
    ├── Pdf_links/      # OUTPUT — FINAL filtered financial links per company
    └── progress.json   # Auto-managed — tracks completed companies
```

---

## Pipeline Flow

### Full Pipeline (default)
Run `python main.py` to process all companies in `DATA/Raw/` sequentially:

```
Company 1: Rank → Crawl → Filter & Save Links  ✓
Company 2: Rank → Crawl → Filter & Save Links  ✓
...
```

### Steps Explained

1.  **Ranking**: Reads raw search results, scores URLs, saves `_ranked.json`.
2.  **Crawling**: Visits top URLs, extracts all links, saves `_crawled.json`.
3.  **Filtering**: Scans crawled links for financial keywords (e.g., "annual report", "Q3", "FY24"), scores them, and saves the final categorized output in `DATA/Pdf_links/`.

---

## Data Output Format

### Final Output: `DATA/Pdf_links/`

One JSON file per company containing categorized links:

```json
{
  "company": "Reliance Industries",
  "metadata": {
    "total_links_scanned": 1500,
    "useful_links_count": 50,
    "uncertain_links_count": 10,
    "removed_links_count": 1440
  },
  "all_links": [ ... ],       // Complete list of unique links found
  "useful_links": [           // High score (Score >= 3)
    "https://www.ril.com/ar2024/annual-report.pdf",
    "https://www.ril.com/results/Q3FY25.xlsx"
  ],
  "uncertain_links": [ ... ], // Medium/Low score (Score 1-2)
  "removed_links": [ ... ]    // Discarded (Score <= 0, or ignore keywords)
}
```

---

## Modules

### `main.py`
The pipeline coordinator.
- Iterates over companies.
- Orchestrates `ranker`, `scraper`, and `link_filter`.
- Handles resume/progress tracking and graceful shutdown (`Ctrl+C`).

### `link_filter.py` (New)
A pure-Python multiprocessing module for identifying financial documents.
- **Scoring**: Assigns points for keywords (`investor`, `financial`, `annual`), patterns (`FY24`, `Q3`), and years.
- **Categorization**: Sorts links into `useful`, `uncertain`, or `removed`.
- **Parallelism**: Can process thousands of files quickly using multiprocessing.

### `ranker.py`
Scores and ranks search results to find the best entry point (e.g., "Investor Relations Home").
- Uses domain similarity, path keywords, and authority checks.

### `scraper.py`
A multi-threaded priority-queue web crawler.
- Fetches pages, extracts links, and discovers downloadable files.
- Stays within the company domain.

---

## Usage

### 1. Full Pipeline (Recommended)
Process all companies from scratch or resume from last stop.
```bash
python main.py
```

### 2. Single Company
Process a specific company by name (fuzzy match).
```bash
python main.py --company_name "reliance"
```

### 3. Individual Steps
Run specific parts of the pipeline (advanced usage).

| Command | Description |
|---------|-------------|
| `python main.py --rank` | Only rank URLs for all companies. |
| `python main.py --crawl` | Crawl ranked companies and filter links. |
| `python main.py --pdf` | **Re-run Filter Only**: Re-process existing crawl data to extract/score PDF links. |

---

## Configuration (.env)

Key settings in `.env`:

```dotenv
# Crawler Settings
MAX_WORKERS=60             # Concurrent crawl threads
TOP_URLS_TO_VISIT=3        # Max starting URLs per company
DELAY_MIN=0.5              # Min delay between requests

# Pipeline Settings
RESUME=true                # true = skip completed companies
SAVE_TO_JSON=true          # Save results locally

# Paths
DATA_RAW_PATH=DATA/Raw
DATA_PDF_LINKS_PATH=DATA/Pdf_links
```

---

## Logging

Logs are saved to `logs/` and printed to the console.
- **Format**: `2026-02-18 10:00:00 | INFO | Ranker_Crawler [Company Name] | Message`
- **File**: `logs/ranker_crawler_YYYYMMDD_HHMMSS.log`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Link Filter Error** | Ensure python 3.8+ is installed. On Windows, the script handles multiprocessing using `spawn`. |
| **No PDF Output** | Check `DATA/Crawled/` to see if links were found first. If crawling failed, filtering has no input. |
| **Resume Issues** | Delete `DATA/progress.json` to force a full restart. |
