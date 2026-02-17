# Ranker & Crawler Pipeline

An automated pipeline that discovers, ranks, crawls, and extracts downloadable documents (PDFs, Excel, etc.) from the **investor relations** pages of Indian listed companies.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Pipeline Flow](#pipeline-flow)
- [Configuration (.env)](#configuration-env)
- [Data Folder Layout](#data-folder-layout)
- [Modules](#modules)
  - [main.py](#mainpy)
  - [ranker.py](#rankerpy)
  - [scraper.py](#scraperpy)
  - [utils.py](#utilspy)
  - [logger.py](#loggerpy)
- [Usage](#usage)
- [Resume Feature](#resume-feature)
- [Logging](#logging)
- [Troubleshooting](#troubleshooting)

---

## Overview

Given raw search-engine results for a company (stored as JSON), this pipeline:

1. **Ranks** the URLs to find the most relevant investor-relations pages.
2. **Crawls** the top-ranked pages using a scored priority-queue BFS.
3. **Extracts** all unique downloadable links (PDF, XLS, DOCX, CSV, etc.).

Each company is processed **end-to-end** before moving to the next, so you always have complete data for finished companies even if the run is interrupted.

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
│ (scraper.py)  │  stay on the same domain, collect downloadables.
└───────┬───────┘
        │  Crawled JSON (site tree + all links)
        ▼
┌───────────────┐
│  PDF LINKS    │  De-duplicate downloadable links across all
│  EXTRACTION   │  crawled pages → final clean list.
└───────────────┘
```

---

## Project Structure

```
Ranker_Crawler/
├── .env                # All configurable settings
├── main.py             # Entry point — orchestrates the full pipeline
├── ranker.py           # URL ranking logic (scoring, filtering, sorting)
├── scraper.py          # Web crawler (priority BFS, link extraction)
├── utils.py            # Helpers (I/O, URL normalization, delays)
├── logger.py           # Logging setup (file + console, company tag)
├── README.md           # This file
├── QUICKSTART.md       # Quick start guide
├── logs/               # Auto-generated log files
└── DATA/
    ├── Raw/            # INPUT  — one subfolder per company with search-result JSON
    │   ├── reliance_industries_limited_investor_relations/
    │   │   └── *.json
    │   ├── hdfc_bank_investor_relations/
    │   │   └── *.json
    │   └── ...
    ├── Ranked/         # OUTPUT — ranked results per company
    │   ├── Reliance Industries_ranked.json
    │   └── ...
    ├── Crawled/        # OUTPUT — crawled site structure per company
    │   ├── Reliance Industries_crawled.json
    │   └── ...
    ├── Pdf_links/      # OUTPUT — unique downloadable links per company
    │   ├── Reliance Industries.json
    │   └── ...
    └── progress.json   # Auto-managed — tracks completed companies (for RESUME)
```

---

## Pipeline Flow

### Full Pipeline (default: `python main.py`)

For **each** company folder in `DATA/Raw/`:

```
Company 1: Rank → Crawl → PDF Links  ✓
Company 2: Rank → Crawl → PDF Links  ✓
Company 3: Rank → Crawl → PDF Links  ✓
...
```

This means Company 2 only starts after Company 1 is fully done — ranking, crawling, and PDF extraction are all completed as a unit.

### Individual Steps

You can also run each step independently:

| Flag      | What it does                                    | Reads from       | Writes to         |
|-----------|-------------------------------------------------|------------------|--------------------|
| `--rank`  | Score & rank URLs from raw search results       | `DATA/Raw/`      | `DATA/Ranked/`     |
| `--crawl` | Crawl top-ranked URLs, build site tree          | `DATA/Ranked/`   | `DATA/Crawled/` + `DATA/Pdf_links/` |
| `--pdf`   | Re-extract downloadable links from crawled data | `DATA/Crawled/`  | `DATA/Pdf_links/`  |

All flags accept an optional `--company_name "name"` for fuzzy single-company matching.

---

## Configuration (.env)

| Variable                | Default   | Description                                              |
|-------------------------|-----------|----------------------------------------------------------|
| **Search**              |           |                                                          |
| `SEARCH_ENGINE`         | duckduckgo| Search engine used to get raw results                    |
| `MAX_SEARCH_RESULTS`    | 20        | Max results per search query                             |
| `TOP_URLS_TO_VISIT`     | 3         | Number of top-ranked URLs to crawl per company           |
| **Delays**              |           |                                                          |
| `DELAY_MIN`             | 0.5       | Minimum delay (seconds) between requests                 |
| `DELAY_MAX`             | 1         | Maximum delay (seconds) between requests                 |
| `LONG_DELAY_MIN`        | 0.0       | Long pause min (seconds) after N requests                |
| `LONG_DELAY_MAX`        | 0.5       | Long pause max (seconds)                                 |
| `LONG_DELAY_AFTER_COUNT`| 300       | Trigger long delay every N requests                      |
| **Workers**             |           |                                                          |
| `MAX_WORKERS`           | 60        | Concurrent threads for the BFS crawler                   |
| **Logging**             |           |                                                          |
| `LOG_ENABLED`           | true      | Master on/off for logging                                |
| `LOG_LEVEL`             | INFO      | Logging level (DEBUG, INFO, WARNING, ERROR)              |
| `LOG_TO_FILE`           | true      | Write logs to `logs/` folder                             |
| `LOG_TO_CONSOLE`        | true      | Print logs to terminal                                   |
| `LOG_FILE_PATH`         | logs/     | Directory for log files                                  |
| **Data Paths**          |           |                                                          |
| `DATA_RAW_PATH`         | DATA/Raw  | Input folder with raw search-result JSON                 |
| `DATA_RANKED_PATH`      | DATA/Ranked | Output folder for ranked results                       |
| `DATA_CRAWLED_PATH`     | DATA/Crawled | Output folder for crawled site structures              |
| `DATA_PDF_LINKS_PATH`   | DATA/Pdf_links | Output folder for unique downloadable links          |
| **Resume**              |           |                                                          |
| `RESUME`                | true      | `true` = skip already completed companies; `false` = start fresh |
| **Request**             |           |                                                          |
| `REQUEST_TIMEOUT`       | 30        | HTTP request timeout in seconds                          |
| `USER_AGENT`            | Chrome UA | User-Agent header sent with every request                |
| **Save Switches**       |           |                                                          |
| `SAVE_TO_JSON`          | true      | Save output as JSON files                                |
| `SAVE_TO_MONGO`         | false     | Save output to MongoDB                                   |
| `SAVE_TO_CSV`           | false     | Save output as CSV                                       |

---

## Data Folder Layout

### Input: `DATA/Raw/`

Each company has its own subfolder containing one or more JSON files with search engine results:

```
DATA/Raw/
└── reliance_industries_limited_investor_relations/
    └── reliance_industries_limited_investor_relations_20260216_124726.json
```

The JSON contains a `query` field (the search query) and a `search_results` array with URLs, titles, and snippets.

### Output: `DATA/Ranked/`

One JSON file per company with scored and sorted URL entries:

```json
[
  {
    "rank": 1,
    "company": "Reliance Industries",
    "investor_url": "https://www.ril.com/investors",
    "official_score": 0.95,
    "quality_score": 0.80,
    "authority_score": 0.70,
    "final_score": 0.85
  }
]
```

### Output: `DATA/Crawled/`

One JSON file per company containing metadata and a hierarchical site tree:

```json
{
  "company": "Reliance Industries",
  "metadata": {
    "total_pages_crawled": 42,
    "total_links_found": 380,
    "total_downloadables_found": 65,
    "unique_downloadable_links": 58,
    "time_taken": "2.5 minutes"
  },
  "crawled_results": [ ... ]
}
```

### Output: `DATA/Pdf_links/`

One JSON file per company with de-duplicated downloadable links:

```json
{
  "company": "Reliance Industries",
  "metadata": { "unique_links_count": 58 },
  "downloadable_links": [
    "https://www.ril.com/ar2024/annual-report.pdf",
    "https://www.ril.com/results/Q3FY25.xlsx"
  ]
}
```

---

## Modules

### main.py

The orchestrator. Parses CLI arguments, loads `.env`, and runs the pipeline. In full-pipeline mode, processes each company sequentially through all three steps. Handles resume/progress tracking.

**Key functions:**
- `step_rank(folder, logger)` — reads raw JSON, calls ranker, saves ranked output.
- `step_crawl(ranked_file, logger)` — reads ranked JSON, crawls top URLs, saves crawled output + PDF links.
- `step_pdf(crawled_file, logger)` — re-extracts unique downloadable links from an existing crawled file.
- `find_matching_folders(path, query)` — fuzzy folder matching (e.g., "reliance" matches `reliance_industries_limited_investor_relations`).

### ranker.py

Scores and ranks URLs from raw search results to identify the best investor-relations landing pages.

**Three scoring dimensions (combined into a final score):**
1. **Official Score** — how likely the domain is the company's own website (domain-name similarity).
2. **Quality Score** — how investor-relevant the URL path and title are (path pattern matching, keyword presence).
3. **Authority Score** — based on backlink count and domain frequency across results.

URLs from authority domains (BSE, NSE, Moneycontrol, etc.) are whitelisted but scored lower on the "official" axis so the company's own site is preferred.

### scraper.py

A multi-threaded priority-queue BFS web crawler.

**How it works:**
1. Starts from the top-ranked URLs.
2. Fetches each page, extracts all `<a href>` links.
3. Scores every discovered link using keyword matching (investor/financial = high, careers/shop = blocked).
4. Pushes high-scoring links onto a min-heap (priority queue) for further crawling.
5. Stays within the same domain; blacklists social media.
6. Collects all downloadable file links (PDF, XLS, DOC, CSV, etc.) across every page visited.

**Key classes:**
- `PageCrawler` — the main crawler with `crawl_page()`, `crawl_hierarchy()`, and `get_unique_downloadables()`.
- `score_url()` — assigns a relevance score to any URL based on path keywords.

### utils.py

Shared utilities used across the project:
- `clean_company_name(query)` — extracts a clean company name from a search query.
- `normalize_url(url)` — deduplicates URLs by normalizing scheme, port, path, query params.
- `extract_root_domain(url)` — strips subdomains and paths.
- `save_json(data, folder, filename)` / `load_json(filepath)` — JSON file I/O.
- `DelayManager` — rate-limiting with configurable random delays and periodic long pauses.

### logger.py

Configurable logging to console and/or file.

**Features:**
- Company-aware: every log line includes the company currently being processed in brackets.
- Format: `2026-02-17 11:30:00 | INFO     | Ranker_Crawler [Reliance Industries] | Crawling page: ...`
- Auto-creates timestamped log files in `logs/`.
- Controlled via `.env` (`LOG_LEVEL`, `LOG_TO_FILE`, `LOG_TO_CONSOLE`, etc.).

---

## Usage

### Full pipeline — all companies
```bash
python main.py
```

### Full pipeline — single company (fuzzy match)
```bash
python main.py --company_name "reliance"
python main.py --company_name "hdfc bank"
```

### Individual steps
```bash
python main.py --rank                                   # Rank all
python main.py --rank --company_name "tcs"              # Rank one
python main.py --crawl                                  # Crawl all
python main.py --crawl --company_name "bharti airtel"   # Crawl one
python main.py --pdf                                    # Extract PDFs all
python main.py --pdf --company_name "infosys"           # Extract PDFs one
```

---

## Resume Feature

The pipeline saves progress after each company completes all three steps.

| `.env` Setting  | Behaviour                                                                 |
|-----------------|---------------------------------------------------------------------------|
| `RESUME=true`   | Reads `DATA/progress.json`, skips companies already marked completed, continues from where it left off. |
| `RESUME=false`  | Deletes `DATA/progress.json` and processes every company from scratch.     |

Progress is tracked by the **folder name** in `DATA/Raw/`. If a run is interrupted mid-company, that company will be re-processed on the next run (only fully completed companies are marked).

---

## Logging

Log lines include the company currently being processed:

```
2026-02-17 11:30:00 | INFO     | Ranker_Crawler [Reliance Industries] | Step 1/3: RANKING
2026-02-17 11:30:01 | INFO     | Ranker_Crawler [Reliance Industries] | Ranking: Reliance Industries
2026-02-17 11:30:01 | INFO     | Ranker_Crawler [Reliance Industries] | Step 2/3: CRAWLING
2026-02-17 11:30:02 | INFO     | Ranker_Crawler [Reliance Industries] | Crawling page: https://www.ril.com/investors
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Reliance Industries] | Step 3/3: PDF LINK EXTRACTION
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Reliance Industries] | Saved 58 unique downloadable links
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Reliance Industries] | [1/8] COMPLETED: Reliance Industries
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Hdfc Bank] | [2/8] STARTING COMPANY: Hdfc Bank
```

Log files are written to `logs/` with a timestamp in the filename (e.g., `ranker_crawler_20260217_113000.log`).

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Raw data path not found` | Ensure `DATA/Raw/` exists and contains company subfolders with JSON files. |
| `No search results in file` | The raw JSON must have a `search_results` array. Check the file format. |
| Company not found (fuzzy match) | The `--company_name` value must partially match a folder name. Try a shorter or different term. |
| Crawling is slow | Reduce `MAX_WORKERS`, increase `DELAY_MIN`/`DELAY_MAX` — aggressive settings may trigger rate-limiting. |
| Want to re-crawl a completed company | Set `RESUME=false` in `.env`, or manually remove the company entry from `DATA/progress.json`. |
| Missing downloadable links | Some sites load links via JavaScript. The crawler only parses static HTML `<a>` tags. |
# Ranker & Crawler Pipeline

An automated pipeline that discovers, ranks, crawls, and extracts downloadable documents (PDFs, Excel, etc.) from the **investor relations** pages of Indian listed companies.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Pipeline Flow](#pipeline-flow)
- [Configuration (.env)](#configuration-env)
- [Data Folder Layout](#data-folder-layout)
- [Modules](#modules)
  - [main.py](#mainpy)
  - [ranker.py](#rankerpy)
  - [scraper.py](#scraperpy)
  - [utils.py](#utilspy)
  - [logger.py](#loggerpy)
- [Usage](#usage)
- [Resume Feature](#resume-feature)
- [Logging](#logging)
- [Troubleshooting](#troubleshooting)

---

## Overview

Given raw search-engine results for a company (stored as JSON), this pipeline:

1. **Ranks** the URLs to find the most relevant investor-relations pages.
2. **Crawls** the top-ranked pages using a scored priority-queue BFS.
3. **Extracts** all unique downloadable links (PDF, XLS, DOCX, CSV, etc.).

Each company is processed **end-to-end** before moving to the next, so you always have complete data for finished companies even if the run is interrupted.

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
│ (scraper.py)  │  stay on the same domain, collect downloadables.
└───────┬───────┘
        │  Crawled JSON (site tree + all links)
        ▼
┌───────────────┐
│  PDF LINKS    │  De-duplicate downloadable links across all
│  EXTRACTION   │  crawled pages → final clean list.
└───────────────┘
```

---

## Project Structure

```
Ranker_Crawler/
├── .env                # All configurable settings
├── main.py             # Entry point — orchestrates the full pipeline
├── ranker.py           # URL ranking logic (scoring, filtering, sorting)
├── scraper.py          # Web crawler (priority BFS, link extraction)
├── utils.py            # Helpers (I/O, URL normalization, delays)
├── logger.py           # Logging setup (file + console, company tag)
├── README.md           # This file
├── QUICKSTART.md       # Quick start guide
├── logs/               # Auto-generated log files
└── DATA/
    ├── Raw/            # INPUT  — one subfolder per company with search-result JSON
    │   ├── reliance_industries_limited_investor_relations/
    │   │   └── *.json
    │   ├── hdfc_bank_investor_relations/
    │   │   └── *.json
    │   └── ...
    ├── Ranked/         # OUTPUT — ranked results per company
    │   ├── Reliance Industries_ranked.json
    │   └── ...
    ├── Crawled/        # OUTPUT — crawled site structure per company
    │   ├── Reliance Industries_crawled.json
    │   └── ...
    ├── Pdf_links/      # OUTPUT — unique downloadable links per company
    │   ├── Reliance Industries.json
    │   └── ...
    └── progress.json   # Auto-managed — tracks completed companies (for RESUME)
```

---

## Pipeline Flow

### Full Pipeline (default: `python main.py`)

For **each** company folder in `DATA/Raw/`:

```
Company 1: Rank → Crawl → PDF Links  ✓
Company 2: Rank → Crawl → PDF Links  ✓
Company 3: Rank → Crawl → PDF Links  ✓
...
```

This means Company 2 only starts after Company 1 is fully done — ranking, crawling, and PDF extraction are all completed as a unit.

### Individual Steps

You can also run each step independently:

| Flag      | What it does                                    | Reads from       | Writes to         |
|-----------|-------------------------------------------------|------------------|--------------------|
| `--rank`  | Score & rank URLs from raw search results       | `DATA/Raw/`      | `DATA/Ranked/`     |
| `--crawl` | Crawl top-ranked URLs, build site tree          | `DATA/Ranked/`   | `DATA/Crawled/` + `DATA/Pdf_links/` |
| `--pdf`   | Re-extract downloadable links from crawled data | `DATA/Crawled/`  | `DATA/Pdf_links/`  |

All flags accept an optional `--company_name "name"` for fuzzy single-company matching.

---

## Configuration (.env)

| Variable                | Default   | Description                                              |
|-------------------------|-----------|----------------------------------------------------------|
| **Search**              |           |                                                          |
| `SEARCH_ENGINE`         | duckduckgo| Search engine used to get raw results                    |
| `MAX_SEARCH_RESULTS`    | 20        | Max results per search query                             |
| `TOP_URLS_TO_VISIT`     | 3         | Number of top-ranked URLs to crawl per company           |
| **Delays**              |           |                                                          |
| `DELAY_MIN`             | 0.5       | Minimum delay (seconds) between requests                 |
| `DELAY_MAX`             | 1         | Maximum delay (seconds) between requests                 |
| `LONG_DELAY_MIN`        | 0.0       | Long pause min (seconds) after N requests                |
| `LONG_DELAY_MAX`        | 0.5       | Long pause max (seconds)                                 |
| `LONG_DELAY_AFTER_COUNT`| 300       | Trigger long delay every N requests                      |
| **Workers**             |           |                                                          |
| `MAX_WORKERS`           | 60        | Concurrent threads for the BFS crawler                   |
| **Logging**             |           |                                                          |
| `LOG_ENABLED`           | true      | Master on/off for logging                                |
| `LOG_LEVEL`             | INFO      | Logging level (DEBUG, INFO, WARNING, ERROR)              |
| `LOG_TO_FILE`           | true      | Write logs to `logs/` folder                             |
| `LOG_TO_CONSOLE`        | true      | Print logs to terminal                                   |
| `LOG_FILE_PATH`         | logs/     | Directory for log files                                  |
| **Data Paths**          |           |                                                          |
| `DATA_RAW_PATH`         | DATA/Raw  | Input folder with raw search-result JSON                 |
| `DATA_RANKED_PATH`      | DATA/Ranked | Output folder for ranked results                       |
| `DATA_CRAWLED_PATH`     | DATA/Crawled | Output folder for crawled site structures              |
| `DATA_PDF_LINKS_PATH`   | DATA/Pdf_links | Output folder for unique downloadable links          |
| **Resume**              |           |                                                          |
| `RESUME`                | true      | `true` = skip already completed companies; `false` = start fresh |
| **Request**             |           |                                                          |
| `REQUEST_TIMEOUT`       | 30        | HTTP request timeout in seconds                          |
| `USER_AGENT`            | Chrome UA | User-Agent header sent with every request                |
| **Save Switches**       |           |                                                          |
| `SAVE_TO_JSON`          | true      | Save output as JSON files                                |
| `SAVE_TO_MONGO`         | false     | Save output to MongoDB                                   |
| `SAVE_TO_CSV`           | false     | Save output as CSV                                       |

---

## Data Folder Layout

### Input: `DATA/Raw/`

Each company has its own subfolder containing one or more JSON files with search engine results:

```
DATA/Raw/
└── reliance_industries_limited_investor_relations/
    └── reliance_industries_limited_investor_relations_20260216_124726.json
```

The JSON contains a `query` field (the search query) and a `search_results` array with URLs, titles, and snippets.

### Output: `DATA/Ranked/`

One JSON file per company with scored and sorted URL entries:

```json
[
  {
    "rank": 1,
    "company": "Reliance Industries",
    "investor_url": "https://www.ril.com/investors",
    "official_score": 0.95,
    "quality_score": 0.80,
    "authority_score": 0.70,
    "final_score": 0.85
  }
]
```

### Output: `DATA/Crawled/`

One JSON file per company containing metadata and a hierarchical site tree:

```json
{
  "company": "Reliance Industries",
  "metadata": {
    "total_pages_crawled": 42,
    "total_links_found": 380,
    "total_downloadables_found": 65,
    "unique_downloadable_links": 58,
    "time_taken": "2.5 minutes"
  },
  "crawled_results": [ ... ]
}
```

### Output: `DATA/Pdf_links/`

One JSON file per company with de-duplicated downloadable links:

```json
{
  "company": "Reliance Industries",
  "metadata": { "unique_links_count": 58 },
  "downloadable_links": [
    "https://www.ril.com/ar2024/annual-report.pdf",
    "https://www.ril.com/results/Q3FY25.xlsx"
  ]
}
```

---

## Modules

### main.py

The orchestrator. Parses CLI arguments, loads `.env`, and runs the pipeline. In full-pipeline mode, processes each company sequentially through all three steps. Handles resume/progress tracking.

**Key functions:**
- `step_rank(folder, logger)` — reads raw JSON, calls ranker, saves ranked output.
- `step_crawl(ranked_file, logger)` — reads ranked JSON, crawls top URLs, saves crawled output + PDF links.
- `step_pdf(crawled_file, logger)` — re-extracts unique downloadable links from an existing crawled file.
- `find_matching_folders(path, query)` — fuzzy folder matching (e.g., "reliance" matches `reliance_industries_limited_investor_relations`).

### ranker.py

Scores and ranks URLs from raw search results to identify the best investor-relations landing pages.

**Three scoring dimensions (combined into a final score):**
1. **Official Score** — how likely the domain is the company's own website (domain-name similarity).
2. **Quality Score** — how investor-relevant the URL path and title are (path pattern matching, keyword presence).
3. **Authority Score** — based on backlink count and domain frequency across results.

URLs from authority domains (BSE, NSE, Moneycontrol, etc.) are whitelisted but scored lower on the "official" axis so the company's own site is preferred.

### scraper.py

A multi-threaded priority-queue BFS web crawler.

**How it works:**
1. Starts from the top-ranked URLs.
2. Fetches each page, extracts all `<a href>` links.
3. Scores every discovered link using keyword matching (investor/financial = high, careers/shop = blocked).
4. Pushes high-scoring links onto a min-heap (priority queue) for further crawling.
5. Stays within the same domain; blacklists social media.
6. Collects all downloadable file links (PDF, XLS, DOC, CSV, etc.) across every page visited.

**Key classes:**
- `PageCrawler` — the main crawler with `crawl_page()`, `crawl_hierarchy()`, and `get_unique_downloadables()`.
- `score_url()` — assigns a relevance score to any URL based on path keywords.

### utils.py

Shared utilities used across the project:
- `clean_company_name(query)` — extracts a clean company name from a search query.
- `normalize_url(url)` — deduplicates URLs by normalizing scheme, port, path, query params.
- `extract_root_domain(url)` — strips subdomains and paths.
- `save_json(data, folder, filename)` / `load_json(filepath)` — JSON file I/O.
- `DelayManager` — rate-limiting with configurable random delays and periodic long pauses.

### logger.py

Configurable logging to console and/or file.

**Features:**
- Company-aware: every log line includes the company currently being processed in brackets.
- Format: `2026-02-17 11:30:00 | INFO     | Ranker_Crawler [Reliance Industries] | Crawling page: ...`
- Auto-creates timestamped log files in `logs/`.
- Controlled via `.env` (`LOG_LEVEL`, `LOG_TO_FILE`, `LOG_TO_CONSOLE`, etc.).

---

## Usage

### Full pipeline — all companies
```bash
python main.py
```

### Full pipeline — single company (fuzzy match)
```bash
python main.py --company_name "reliance"
python main.py --company_name "hdfc bank"
```

### Individual steps
```bash
python main.py --rank                                   # Rank all
python main.py --rank --company_name "tcs"              # Rank one
python main.py --crawl                                  # Crawl all
python main.py --crawl --company_name "bharti airtel"   # Crawl one
python main.py --pdf                                    # Extract PDFs all
python main.py --pdf --company_name "infosys"           # Extract PDFs one
```

---

## Resume Feature

The pipeline saves progress after each company completes all three steps.

| `.env` Setting  | Behaviour                                                                 |
|-----------------|---------------------------------------------------------------------------|
| `RESUME=true`   | Reads `DATA/progress.json`, skips companies already marked completed, continues from where it left off. |
| `RESUME=false`  | Deletes `DATA/progress.json` and processes every company from scratch.     |

Progress is tracked by the **folder name** in `DATA/Raw/`. If a run is interrupted mid-company, that company will be re-processed on the next run (only fully completed companies are marked).

---

## Logging

Log lines include the company currently being processed:

```
2026-02-17 11:30:00 | INFO     | Ranker_Crawler [Reliance Industries] | Step 1/3: RANKING
2026-02-17 11:30:01 | INFO     | Ranker_Crawler [Reliance Industries] | Ranking: Reliance Industries
2026-02-17 11:30:01 | INFO     | Ranker_Crawler [Reliance Industries] | Step 2/3: CRAWLING
2026-02-17 11:30:02 | INFO     | Ranker_Crawler [Reliance Industries] | Crawling page: https://www.ril.com/investors
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Reliance Industries] | Step 3/3: PDF LINK EXTRACTION
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Reliance Industries] | Saved 58 unique downloadable links
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Reliance Industries] | [1/8] COMPLETED: Reliance Industries
2026-02-17 11:32:15 | INFO     | Ranker_Crawler [Hdfc Bank] | [2/8] STARTING COMPANY: Hdfc Bank
```

Log files are written to `logs/` with a timestamp in the filename (e.g., `ranker_crawler_20260217_113000.log`).

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Raw data path not found` | Ensure `DATA/Raw/` exists and contains company subfolders with JSON files. |
| `No search results in file` | The raw JSON must have a `search_results` array. Check the file format. |
| Company not found (fuzzy match) | The `--company_name` value must partially match a folder name. Try a shorter or different term. |
| Crawling is slow | Reduce `MAX_WORKERS`, increase `DELAY_MIN`/`DELAY_MAX` — aggressive settings may trigger rate-limiting. |
| Want to re-crawl a completed company | Set `RESUME=false` in `.env`, or manually remove the company entry from `DATA/progress.json`. |
| Missing downloadable links | Some sites load links via JavaScript. The crawler only parses static HTML `<a>` tags. |
