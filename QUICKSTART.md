# Quick Start Guide

Get the Ranker & Crawler pipeline running in under 2 minutes.

---

## 1. Install Dependencies

```bash
pip install requests beautifulsoup4 lxml python-dotenv
```

## 2. Check Your Data

Make sure `DATA/Raw/` has at least one company folder with a JSON file inside:

```
DATA/Raw/
└── reliance_industries_limited_investor_relations/
    └── *.json
```

Each JSON file should contain:
```json
{
  "query": "reliance industries investor relations",
  "search_results": [
    { "url": "https://...", "title": "...", "text": "..." }
  ]
}
```

## 3. Configure (Optional)

Edit `.env` to tweak settings. The defaults work fine out of the box.

Key settings you might want to change:

```dotenv
TOP_URLS_TO_VISIT=3        # How many top-ranked URLs to crawl per company
MAX_WORKERS=60             # Concurrent crawl threads
RESUME=true                # true = resume from last stop, false = start fresh
```

## 4. Run

### Process all companies (Rank → Crawl → PDF for each)
```bash
python main.py
```

### Process one company
```bash
python main.py --company_name "reliance"
```

### Run individual steps
```bash
python main.py --rank                                  # Only rank
python main.py --crawl                                 # Only crawl
python main.py --pdf                                   # Only extract PDF links
python main.py --crawl --company_name "hdfc bank"      # Crawl one company
```

## 5. Check Results

After the pipeline finishes, find the outputs in:

| Folder             | Contents                                |
|--------------------|-----------------------------------------|
| `DATA/Ranked/`     | Scored & sorted URLs per company        |
| `DATA/Crawled/`    | Full crawled site structure per company  |
| `DATA/Pdf_links/`  | Clean list of downloadable links (PDF, XLS, etc.) |
| `logs/`            | Timestamped log files                   |

## 6. Resume After Interruption

If the run was interrupted (Ctrl+C, crash, etc.):

- With `RESUME=true` (default): just run `python main.py` again — it picks up where it left off.
- With `RESUME=false`: it starts over from company 1.

To force a fresh start, set `RESUME=false` in `.env` or delete `DATA/progress.json`.

---

For full documentation, see [README.md](README.md).
