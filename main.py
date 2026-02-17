"""
Ranker & Crawler Pipeline - main.py

Usage:
  python main.py                                          # Full pipeline (rank + crawl + pdf_links) for ALL companies
  python main.py --company_name "reliance industries"     # Full pipeline for matching company (fuzzy match)
  python main.py --rank                                   # Only rank, all companies
  python main.py --rank --company_name "bharti airtel"    # Only rank, one company
  python main.py --crawl                                  # Only crawl (from ranked data), all companies
  python main.py --crawl --company_name "hdfc bank"       # Only crawl, one company
  python main.py --pdf                                    # Only extract unique PDF/downloadable links, all companies
  python main.py --pdf --company_name "tcs"               # Only extract PDF links, one company
"""

import os
import sys
import argparse
import glob
import time
import re
from pathlib import Path
from dotenv import load_dotenv

from logger import setup_logger
from utils import clean_company_name, save_json, load_json
from ranker import rank_investor_pages
from scraper import PageCrawler

# Load env from project root (works on both Windows and Linux)
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


# ============================================================================
# FOLDER MATCHING (fuzzy, case-insensitive)
# ============================================================================

def _normalize_for_match(text: str) -> str:
    """Normalize a string for fuzzy folder matching.
    'Reliance Industries Limited' -> 'reliance industries limited'
    'reliance_industries_limited_investor_relations' -> 'reliance industries limited investor relations'
    """
    text = text.lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r'\s+', ' ', text)
    return text


def find_matching_folders(base_path: str, query: str) -> list:
    """
    Find folders in base_path that match the query (fuzzy, case-insensitive).
    The query can be a partial name — e.g. 'reliance' matches
    'reliance_industries_limited_investor_relations'.
    """
    if not os.path.isdir(base_path):
        return []

    query_norm = _normalize_for_match(query)
    matches = []

    for item in os.listdir(base_path):
        full_path = os.path.join(base_path, item)
        if not os.path.isdir(full_path):
            continue

        folder_norm = _normalize_for_match(item)

        # Match if the query words all appear in the folder name (order-independent)
        query_words = query_norm.split()
        if all(word in folder_norm for word in query_words):
            matches.append(full_path)

    return matches


def find_matching_files(base_path: str, query: str, extension: str = ".json") -> list:
    """
    Find files in base_path whose name matches the query (fuzzy, case-insensitive).
    Used for finding ranked / crawled files by company name.
    """
    if not os.path.isdir(base_path):
        return []

    query_norm = _normalize_for_match(query)
    matches = []

    for item in os.listdir(base_path):
        if not item.lower().endswith(extension):
            continue

        file_norm = _normalize_for_match(os.path.splitext(item)[0])

        query_words = query_norm.split()
        if all(word in file_norm for word in query_words):
            matches.append(os.path.join(base_path, item))

    return matches


def get_all_folders(base_path: str) -> list:
    """Return all subdirectories in base_path."""
    if not os.path.isdir(base_path):
        return []
    return [
        os.path.join(base_path, d)
        for d in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, d))
    ]


def get_all_files(base_path: str, extension: str = ".json") -> list:
    """Return all files with given extension in base_path."""
    if not os.path.isdir(base_path):
        return []
    return [
        os.path.join(base_path, f)
        for f in os.listdir(base_path)
        if f.lower().endswith(extension) and os.path.isfile(os.path.join(base_path, f))
    ]


# ============================================================================
# PIPELINE STEPS
# ============================================================================

def step_rank(company_folder_path: str, logger) -> str | None:
    """
    Step 1: Read raw search results and rank them.
    Returns the company_name if successful, None otherwise.
    """
    json_files = glob.glob(os.path.join(company_folder_path, "*.json"))
    if not json_files:
        logger.warning(f"No JSON files found in {company_folder_path}")
        return None

    raw_file = json_files[0]
    logger.info(f"Reading raw file: {raw_file}")
    data = load_json(raw_file)
    if not data:
        return None

    search_results = data.get('search_results', [])
    if not search_results:
        logger.warning(f"No search results in {raw_file}")
        return None

    # Determine Company Name
    query = data.get('query', '')
    company_name = clean_company_name(query)
    if not company_name:
        company_name = clean_company_name(os.path.basename(company_folder_path).replace('_', ' '))

    logger.info(f"Ranking: {company_name}")

    ranked_results = rank_investor_pages(company_name, search_results)

    ranked_path = os.getenv("DATA_RANKED_PATH", "DATA/Ranked")
    os.makedirs(ranked_path, exist_ok=True)

    ranked_filename = f"{company_name}_ranked.json"
    saved_file = save_json(ranked_results, ranked_path, ranked_filename)
    if saved_file:
        logger.info(f"Saved ranked results to: {saved_file}")

    return company_name


def step_crawl(ranked_filepath: str, logger) -> tuple:
    """
    Step 2: Crawl top ranked URLs.
    Returns (company_name, crawled_data_dict, crawler_instance) or (None, None, None).
    """
    data = load_json(ranked_filepath)
    if not data or not isinstance(data, list):
        logger.warning(f"Invalid or empty ranked file: {ranked_filepath}")
        return None, None, None

    # Determine company name from the data
    company_name = None
    for entry in data:
        if isinstance(entry, dict) and 'company' in entry:
            company_name = entry['company']
            break

    if not company_name:
        # Derive from filename
        basename = os.path.basename(ranked_filepath)
        company_name = os.path.splitext(basename)[0].replace("_ranked", "").strip()

    logger.info(f"Crawling: {company_name}")

    top_n = int(os.getenv("TOP_URLS_TO_VISIT", "3"))
    valid_entries = [d for d in data if isinstance(d, dict) and 'rank' in d and 'investor_url' in d]
    sorted_entries = sorted(valid_entries, key=lambda x: x['rank'])

    top_urls = []
    seen_urls = set()
    for entry in sorted_entries:
        url = entry['investor_url']
        if url not in seen_urls:
            top_urls.append(entry)
            seen_urls.add(url)
            if len(top_urls) >= top_n:
                break

    if not top_urls:
        logger.warning(f"No valid URLs to crawl for {company_name}")
        return company_name, None, None

    crawler = PageCrawler()
    crawled_results_list = []

    start_time = time.time()

    total_pages_crawled = 0
    total_links_found = 0
    total_downloadables_found = 0

    for entry in top_urls:
        url = entry['investor_url']
        rank = entry['rank']
        logger.info(f"Crawling Rank {rank}: {url}")

        try:
            crawl_output = crawler.crawl_hierarchy(url)
            meta = crawl_output["metadata"]

            total_pages_crawled += meta.get("total_pages_crawled", 0)
            total_links_found += meta.get("total_links_found", 0)
            total_downloadables_found += meta.get("total_downloadables_found", 0)

            result_entry = {
                "url": url,
                "rank": rank,
                "total_pages_crawled": meta.get("total_pages_crawled", 0),
                "total_links_found": meta.get("total_links_found", 0),
                "total_downloadables_found": meta.get("total_downloadables_found", 0),
                "site_structure": crawl_output["structure"]
            }
            crawled_results_list.append(result_entry)

        except Exception as crawl_err:
            logger.error(f"Failed to crawl {url}: {crawl_err}")

    end_time = time.time()
    elapsed_time_sec = round(end_time - start_time, 2)
    elapsed_time = round(elapsed_time_sec / 60, 2)

    unique_downloadables = crawler.get_unique_downloadables()

    crawled_data = {
        "company": company_name,
        "metadata": {
            "total_pages_crawled": total_pages_crawled,
            "total_links_found": total_links_found,
            "total_downloadables_found": total_downloadables_found,
            "unique_downloadable_links": len(unique_downloadables),
            "time_taken": f"{elapsed_time} minutes"
        },
        "crawled_results": crawled_results_list
    }

    crawled_path = os.getenv("DATA_CRAWLED_PATH", "DATA/Crawled")
    crawled_filename = f"{company_name}_crawled.json"
    save_json(crawled_data, crawled_path, crawled_filename)
    logger.info(f"Saved crawled results to: {crawled_path}/{crawled_filename}")

    # Also save pdf links immediately
    _save_pdf_links(company_name, unique_downloadables, logger)

    crawler.close()

    return company_name, crawled_data, None


def step_pdf(crawled_filepath: str, logger):
    """
    Step 3: Extract unique downloadable links from an existing crawled JSON.
    Useful for re-extracting without re-crawling.
    """
    data = load_json(crawled_filepath)
    if not data:
        logger.warning(f"Invalid crawled file: {crawled_filepath}")
        return

    company_name = data.get("company", "Unknown")
    logger.info(f"Extracting PDF links: {company_name}")

    # Collect all unique downloadable links from the crawled structure
    all_links = set()

    def _walk_tree(node):
        """Recursively walk the site_structure tree and collect downloadable links."""
        if isinstance(node, dict):
            if "downloadables" in node and isinstance(node["downloadables"], list):
                all_links.update(node["downloadables"])
            for key, value in node.items():
                if key.startswith("_") or key in ("downloadables", "links"):
                    continue
                _walk_tree(value)

    for result in data.get("crawled_results", []):
        structure = result.get("site_structure", {})
        _walk_tree(structure)

    unique_list = sorted(list(all_links))
    _save_pdf_links(company_name, unique_list, logger)


def _save_pdf_links(company_name: str, links: list, logger):
    """Save unique downloadable links to DATA/Pdf_links/."""
    pdf_links_path = os.getenv("DATA_PDF_LINKS_PATH", "DATA/Pdf_links")
    pdf_links_data = {
        "company": company_name,
        "metadata": {
            "unique_links_count": len(links)
        },
        "downloadable_links": links
    }
    pdf_links_filename = f"{company_name}.json"
    save_json(pdf_links_data, pdf_links_path, pdf_links_filename)
    logger.info(f"Saved {len(links)} unique downloadable links to: {pdf_links_path}/{pdf_links_filename}")


# ============================================================================
# ARGUMENT PARSING
# ============================================================================

def get_args():
    parser = argparse.ArgumentParser(
        description="Ranker & Crawler Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                        Full pipeline, all companies
  python main.py --company_name "reliance industries"   Full pipeline, fuzzy match
  python main.py --rank                                 Only rank, all companies
  python main.py --crawl --company_name "tcs"           Only crawl, one company
  python main.py --pdf                                  Only extract PDF links, all
        """
    )
    parser.add_argument(
        "--company_name", type=str, default=None,
        help="Company name (fuzzy match, case-insensitive). Omit for all companies."
    )
    parser.add_argument("--rank", action="store_true", help="Run only the ranking step")
    parser.add_argument("--crawl", action="store_true", help="Run only the crawling step (needs ranked data)")
    parser.add_argument("--pdf", action="store_true", help="Run only PDF/downloadable link extraction (needs crawled data)")
    return parser.parse_args()


# ============================================================================
# MAIN
# ============================================================================

def main():
    args = get_args()
    logger = setup_logger()

    raw_path = os.getenv("DATA_RAW_PATH", "DATA/Raw")
    ranked_path = os.getenv("DATA_RANKED_PATH", "DATA/Ranked")
    crawled_path = os.getenv("DATA_CRAWLED_PATH", "DATA/Crawled")

    # Determine which steps to run
    # If none of --rank, --crawl, --pdf are set, run full pipeline
    run_rank = args.rank
    run_crawl = args.crawl
    run_pdf = args.pdf
    full_pipeline = not (run_rank or run_crawl or run_pdf)

    company_query = args.company_name  # may be None (means all)

    # -----------------------------------------------------------------------
    # STEP: RANK
    # -----------------------------------------------------------------------
    if full_pipeline or run_rank:
        logger.info("=" * 60)
        logger.info("STEP: RANKING")
        logger.info("=" * 60)

        if not os.path.isdir(raw_path):
            logger.error(f"Raw data path not found: {raw_path}")
            if not full_pipeline:
                return
        else:
            if company_query:
                targets = find_matching_folders(raw_path, company_query)
                if not targets:
                    logger.warning(f"No folders matching '{company_query}' in {raw_path}")
                    if not full_pipeline:
                        return
            else:
                targets = get_all_folders(raw_path)

            logger.info(f"Found {len(targets)} folder(s) to rank.")
            for folder in targets:
                try:
                    step_rank(folder, logger)
                except Exception as e:
                    logger.error(f"Error ranking {folder}: {e}")

    # -----------------------------------------------------------------------
    # STEP: CRAWL
    # -----------------------------------------------------------------------
    if full_pipeline or run_crawl:
        logger.info("=" * 60)
        logger.info("STEP: CRAWLING")
        logger.info("=" * 60)

        if not os.path.isdir(ranked_path):
            logger.error(f"Ranked data path not found: {ranked_path}")
            if not full_pipeline:
                return
        else:
            if company_query:
                ranked_files = find_matching_files(ranked_path, company_query, ".json")
                if not ranked_files:
                    logger.warning(f"No ranked files matching '{company_query}' in {ranked_path}")
                    if not full_pipeline:
                        return
            else:
                ranked_files = get_all_files(ranked_path, ".json")

            logger.info(f"Found {len(ranked_files)} ranked file(s) to crawl.")
            for rfile in ranked_files:
                try:
                    step_crawl(rfile, logger)
                except Exception as e:
                    logger.error(f"Error crawling {rfile}: {e}")

    # -----------------------------------------------------------------------
    # STEP: PDF LINKS
    # -----------------------------------------------------------------------
    if run_pdf:
        # Only runs when explicitly requested (not in full pipeline, since
        # crawl already saves pdf links)
        logger.info("=" * 60)
        logger.info("STEP: PDF LINK EXTRACTION")
        logger.info("=" * 60)

        if not os.path.isdir(crawled_path):
            logger.error(f"Crawled data path not found: {crawled_path}")
            return

        if company_query:
            crawled_files = find_matching_files(crawled_path, company_query, ".json")
            if not crawled_files:
                logger.warning(f"No crawled files matching '{company_query}' in {crawled_path}")
                return
        else:
            crawled_files = get_all_files(crawled_path, ".json")

        logger.info(f"Found {len(crawled_files)} crawled file(s) to extract PDF links from.")
        for cfile in crawled_files:
            try:
                step_pdf(cfile, logger)
            except Exception as e:
                logger.error(f"Error extracting PDF links from {cfile}: {e}")

    logger.info("=" * 60)
    logger.info("Pipeline finished.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
