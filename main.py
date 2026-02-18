"""
Ranker & Crawler Pipeline - main.py

Full pipeline processes each company end-to-end (Rank → Crawl → PDF) before
moving to the next company.  Set RESUME=true in .env to resume from where
it last stopped, or RESUME=false to start from the beginning.

Usage:
  python main.py                                          # Full pipeline (rank → crawl → pdf) per company
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
import signal
from pathlib import Path
from dotenv import load_dotenv

from logger import setup_logger, set_current_company

# Global flag for graceful shutdown
_shutdown_requested = False

def _signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    global _shutdown_requested
    if _shutdown_requested:
        print("\n[FORCE EXIT] Second interrupt received. Exiting immediately.")
        sys.exit(1)
    _shutdown_requested = True
    print("\n[INTERRUPT] Shutdown requested. Finishing current company... (Press Ctrl+C again to force exit)")

# Register signal handlers
signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, _signal_handler)
from utils import clean_company_name, save_json, load_json
from ranker import rank_investor_pages
from scraper import PageCrawler
from link_filter import process_company_file, run_link_filter  # Import the new filter logic


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
    """Return all subdirectories in base_path, sorted alphabetically."""
    if not os.path.isdir(base_path):
        return []
    return sorted([
        os.path.join(base_path, d)
        for d in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, d))
    ], key=lambda x: os.path.basename(x).lower())


def get_all_files(base_path: str, extension: str = ".json") -> list:
    """Return all files with given extension in base_path, sorted alphabetically."""
    if not os.path.isdir(base_path):
        return []
    return sorted([
        os.path.join(base_path, f)
        for f in os.listdir(base_path)
        if f.lower().endswith(extension) and os.path.isfile(os.path.join(base_path, f))
    ], key=lambda x: os.path.basename(x).lower())


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
    full_crawled_path = os.path.join(crawled_path, crawled_filename)
    save_json(crawled_data, crawled_path, crawled_filename)
    logger.info(f"Saved crawled results to: {full_crawled_path}")

    # Also extract and filter PDF links immediately
    try:
        pdf_links_path = os.getenv("DATA_PDF_LINKS_PATH", "DATA/Pdf_links")
        result = process_company_file(full_crawled_path, output_dir=pdf_links_path)
        if "Error" in result:
            logger.error(result)
        else:
            logger.info(result)
    except Exception as e:
        logger.error(f"Error extracting PDF links for {company_name}: {e}")

    crawler.close()

    return company_name, crawled_data, None


def step_pdf(crawled_filepath: str, logger):
    """
    Step 3: Extract & Filter unique downloadable links from an existing crawled JSON.
    Useful for re-extracting without re-crawling.
    Uses link_filter.py logic.
    """
    try:
        # Get output path from env or default
        pdf_links_path = os.getenv("DATA_PDF_LINKS_PATH", "DATA/Pdf_links")
        
        # Simply delegate to the new processor which handles loading, filtering, and saving
        result = process_company_file(crawled_filepath, output_dir=pdf_links_path)
        
        if "Error" in result:
            logger.error(result)
        else:
            logger.info(result)
    except Exception as e:
        logger.error(f"Error extracting PDF links from {crawled_filepath}: {e}")

# (Old _save_pdf_links removed as it is now handled by link_filter.py)



# ============================================================================
# PROGRESS TRACKING (for RESUME feature)
# ============================================================================

PROGRESS_FILENAME = "progress.json"


def _get_progress_path() -> str:
    """Return path to the progress tracking file (DATA/progress.json)."""
    path = os.getenv("PROGRESS_FILE_PATH", "DATA/progress.json")
    # Ensure directory exists
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    return path


def _load_completed(logger) -> set:
    """Load the set of completed company folder names from progress file."""
    progress_path = _get_progress_path()
    if not os.path.exists(progress_path):
        return set()
    data = load_json(progress_path)
    if data and isinstance(data, dict):
        completed = set(data.get("completed", []))
        logger.info(f"Loaded progress: {len(completed)} companies already completed.")
        return completed
    return set()


def _save_completed(completed: set, logger):
    """Persist the set of completed company folder names."""
    progress_path = _get_progress_path()
    folder = os.path.dirname(progress_path) or "."
    fname = os.path.basename(progress_path)
    save_json({"completed": sorted(list(completed))}, folder, fname)


def _clear_progress(logger):
    """Delete the progress file to start fresh."""
    progress_path = _get_progress_path()
    if os.path.exists(progress_path):
        os.remove(progress_path)
        logger.info("Cleared previous progress (RESUME=false).")


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
    parser.add_argument("--force", action="store_true", help="Force re-processing even if already completed (ignores progress)")
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

    # Resume switch from .env (--force overrides it)
    resume_enabled = os.getenv("RESUME", "true").lower() == "true" and not args.force
    if args.force:
        logger.info("--force flag set: ignoring progress, will re-process all matched companies.")

    # Determine which steps to run
    run_rank = args.rank
    run_crawl = args.crawl
    run_pdf = args.pdf
    full_pipeline = not (run_rank or run_crawl or run_pdf)

    company_query = args.company_name  # may be None (means all)

    # ------------------------------------------------------------------
    # FULL PIPELINE: per-company (rank → crawl → pdf → next company)
    # ------------------------------------------------------------------
    if full_pipeline:
        logger.info("=" * 60)
        logger.info("FULL PIPELINE (per-company: Rank → Crawl → PDF)")
        logger.info("=" * 60)

        if not os.path.isdir(raw_path):
            logger.error(f"Raw data path not found: {raw_path}")
            return

        # Get target folders
        if company_query:
            targets = find_matching_folders(raw_path, company_query)
            if not targets:
                logger.warning(f"No folders matching '{company_query}' in {raw_path}")
                return
        else:
            targets = get_all_folders(raw_path)

        # Filter by START_RANGE and END_RANGE if provided
        start_range_env = os.getenv("START_RANGE")
        end_range_env = os.getenv("END_RANGE")

        if start_range_env or end_range_env:
            try:
                # Default start is 1 (index 0) if not provided
                start_val = int(start_range_env) if start_range_env else 1
                start_idx = start_val - 1  # 1-based input -> 0-based index
                
                end_idx = int(end_range_env) if end_range_env else None
                
                if start_idx < 0:
                    start_idx = 0

                original_count = len(targets)
                if end_idx:
                    targets = targets[start_idx:end_idx]
                else:
                    targets = targets[start_idx:]

                logger.info(f"Applied range filter: START={start_val}, END={end_range_env}. Reduced targets from {original_count} to {len(targets)}.")
            except ValueError:
                logger.error("Invalid START_RANGE or END_RANGE. Please provide integers.")

        total = len(targets)
        logger.info(f"Found {total} company folder(s) to process.")

        # Resume logic
        completed = set()
        if resume_enabled:
            completed = _load_completed(logger)
        else:
            _clear_progress(logger)

        for i, folder in enumerate(targets, 1):
            # Check for shutdown request
            if _shutdown_requested:
                logger.info("Shutdown requested. Stopping after current company.")
                break

            folder_name = os.path.basename(folder)

            # Skip already completed (resume mode)
            if resume_enabled and folder_name in completed:
                logger.info(f"[{i}/{total}] SKIPPING (already completed): {folder_name}")
                continue

            # Derive a display-friendly company name from folder
            display_name = clean_company_name(folder_name.replace("_", " "))
            set_current_company(display_name)

            logger.info("=" * 60)
            logger.info(f"[{i}/{total}] STARTING COMPANY: {display_name}")
            logger.info("=" * 60)

            try:
                # --- Step 1: RANK ---
                logger.info("-" * 40)
                logger.info("Step 1/3: RANKING")
                logger.info("-" * 40)
                company_name = step_rank(folder, logger)
                if not company_name:
                    logger.warning(f"Ranking failed for {folder_name}, skipping.")
                    continue

                # Update logger with the actual resolved company name
                set_current_company(company_name)

                # --- Step 2: CRAWL ---
                logger.info("-" * 40)
                logger.info("Step 2/3: CRAWLING")
                logger.info("-" * 40)
                ranked_file = os.path.join(ranked_path, f"{company_name}_ranked.json")
                if not os.path.exists(ranked_file):
                    logger.warning(f"Ranked file not found: {ranked_file}, skipping crawl.")
                    continue

                company_name, crawled_data, _ = step_crawl(ranked_file, logger)

                # --- Step 3: PDF LINKS ---
                # (step_crawl already saves PDF links, but log the step)
                logger.info("-" * 40)
                logger.info("Step 3/3: PDF LINK EXTRACTION (saved during crawl)")
                logger.info("-" * 40)

                # If crawl produced data, verify pdf links were saved
                pdf_links_path = os.getenv("DATA_PDF_LINKS_PATH", "DATA/Pdf_links")
                pdf_file = os.path.join(pdf_links_path, f"{company_name}.json")
                if os.path.exists(pdf_file):
                    pdf_data = load_json(pdf_file)
                    # For new format, count is at useful_links_count
                    if "metadata" in pdf_data and "useful_links_count" in pdf_data["metadata"]:
                         count = pdf_data["metadata"]["useful_links_count"]
                         uncertain = pdf_data["metadata"].get("uncertain_links_count", 0)
                         logger.info(f"PDF links file exists: {count} useful, {uncertain} uncertain.")
                    else:
                        # Fallback for old format or unexpected structure
                        count = pdf_data.get("metadata", {}).get("unique_links_count", 0)
                        logger.info(f"PDF links file exists: {count} unique links.")
                else:
                    logger.warning(f"PDF links file not found for {company_name}.")

                # Mark completed and persist progress
                completed.add(folder_name)
                _save_completed(completed, logger)

                logger.info(f"[{i}/{total}] COMPLETED: {company_name}")

            except Exception as e:
                logger.error(f"Error processing {folder_name}: {e}", exc_info=True)

        set_current_company(None)
        logger.info("=" * 60)
        logger.info(f"Pipeline finished. {len(completed)} / {total} companies completed.")
        logger.info("=" * 60)
        return

    # ------------------------------------------------------------------
    # INDIVIDUAL STEPS (--rank / --crawl / --pdf)
    # ------------------------------------------------------------------

    # STEP: RANK
    if run_rank:
        logger.info("=" * 60)
        logger.info("STEP: RANKING")
        logger.info("=" * 60)

        if not os.path.isdir(raw_path):
            logger.error(f"Raw data path not found: {raw_path}")
            return

        if company_query:
            targets = find_matching_folders(raw_path, company_query)
            if not targets:
                logger.warning(f"No folders matching '{company_query}' in {raw_path}")
                return
        else:
            targets = get_all_folders(raw_path)

        logger.info(f"Found {len(targets)} folder(s) to rank.")
        for folder in targets:
            if _shutdown_requested:
                logger.info("Shutdown requested. Stopping.")
                break
            try:
                display_name = clean_company_name(os.path.basename(folder).replace("_", " "))
                set_current_company(display_name)
                company_name = step_rank(folder, logger)
                if company_name:
                    set_current_company(company_name)
            except Exception as e:
                logger.error(f"Error ranking {folder}: {e}")
        set_current_company(None)

    # STEP: CRAWL
    if run_crawl:
        logger.info("=" * 60)
        logger.info("STEP: CRAWLING")
        logger.info("=" * 60)

        if not os.path.isdir(ranked_path):
            logger.error(f"Ranked data path not found: {ranked_path}")
            return

        if company_query:
            ranked_files = find_matching_files(ranked_path, company_query, ".json")
            if not ranked_files:
                logger.warning(f"No ranked files matching '{company_query}' in {ranked_path}")
                return
        else:
            ranked_files = get_all_files(ranked_path, ".json")

        logger.info(f"Found {len(ranked_files)} ranked file(s) to crawl.")
        for rfile in ranked_files:
            if _shutdown_requested:
                logger.info("Shutdown requested. Stopping.")
                break
            try:
                display_name = os.path.splitext(os.path.basename(rfile))[0].replace("_ranked", "").strip()
                set_current_company(display_name)
                step_crawl(rfile, logger)
            except Exception as e:
                logger.error(f"Error crawling {rfile}: {e}")
        set_current_company(None)

    # STEP: PDF LINKS
    if run_pdf:
        logger.info("=" * 60)
        logger.info("STEP: PDF LINK EXTRACTION & FILTERING")
        logger.info("=" * 60)

        if not os.path.isdir(crawled_path):
            logger.error(f"Crawled data path not found: {crawled_path}")
            return

        # Define output path (defaulting to DATA/Pdf_links if not set)
        pdf_links_path = os.getenv("DATA_PDF_LINKS_PATH", "DATA/Pdf_links")

        if company_query:
            # If specific company requested, use the existing loop logic
            crawled_files = find_matching_files(crawled_path, company_query, ".json")
            if not crawled_files:
                logger.warning(f"No crawled files matching '{company_query}' in {crawled_path}")
                return
            
            logger.info(f"Found {len(crawled_files)} crawled file(s) to process.")
            for cfile in crawled_files:
                if _shutdown_requested:
                    logger.info("Shutdown requested. Stopping.")
                    break
                try:
                    display_name = os.path.splitext(os.path.basename(cfile))[0].replace("_crawled", "").strip()
                    set_current_company(display_name)
                    step_pdf(cfile, logger)
                except Exception as e:
                    logger.error(f"Error extracting PDF links from {cfile}: {e}")
            set_current_company(None)
        else:
            # If processing ALL companies, use the multiprocessing function from link_filter
            logger.info("Running parallel link filtering on all crawled files...")
            run_link_filter(input_dir=crawled_path, output_dir=pdf_links_path)

    logger.info("=" * 60)

    logger.info("Pipeline finished.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
