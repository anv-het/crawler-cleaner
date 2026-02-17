# Ranker & Crawler Pipeline

Project for ranking investor relations search results and crawling the top-ranked pages.

## Project Structure

*   `main.py`: Entry point for the pipeline.
*   `ranker.py`: Logic for scoring and ranking URLs.
*   `scraper.py`: Logic for crawling websites (BFS hierarchy).
*   `logger.py`: Logging configuration.
*   `utils.py`: Helper functions (I/O, URL normalization, Delays).
*   `.env`: Configuration settings.
*   `DATA/`: Data storage.
    *   `Raw/`: Input JSON files (organized in folders per company).
    *   `Ranked/`: Output of `ranker.py`.
    *   `Crawled/`: Output of `scraper.py`.

## Setup

1.  Create a virtual environment (optional but recommended).
2.  Install dependencies:
    ```bash
    pip install requests beautifulsoup4 python-dotenv
    ```
3.  Configure `.env` file if needed (already set up).

## Usage

Calculate rankings and crawl top URLs for companies.

### Single Company

Run for a specific company folder located in `DATA/Raw`:

```bash
python main.py --company_name "Reliance_Industries"
```

*Note: The name must match a folder in `DATA/Raw`.*

### All Companies

Process all company folders in `DATA/Raw`:

```bash
python main.py --all
```

## Data Workflow

1.  **Input**: Place search result JSON files in `DATA/Raw/<Company_Name>/`.
2.  **Ranking**: The system reads the JSON, scores URLs based on domain authority, path patterns, and content relevance.
3.  **Crawling**: Key pages are visited, and a hierarchical map of the site is built.
4.  **Output**:
    *   Ranked results are saved to `DATA/Ranked`.
    *   Crawled structure is saved to `DATA/Crawled`.
