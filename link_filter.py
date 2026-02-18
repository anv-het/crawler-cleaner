import json
import os
import re
import time
import logging
from urllib.parse import urlparse, unquote
from pathlib import Path
from multiprocessing import Pool, cpu_count
from functools import partial

# Configure logging
try:
    from logger import get_logger
    logger = get_logger("Ranker_Crawler.LinkFilter")
except ImportError:
    logger = logging.getLogger(__name__)

# Keywords and Regex Patterns Configuration
HIGH_PRIORITY_KEYWORDS = {
    "investor", "investor-relations", "financial", "results", "earnings",
    "annual", "quarterly", "shareholding", "shareholder","cash-flow",
    "concall", "investor-presentation", "balance-sheet", "profit-loss",
    "assets", "liabilities", "equity"
    
}

MEDIUM_PRIORITY_KEYWORDS = {
    "report", "statement", "accounts", "disclosure", "outcome", "intimation",
    "board-meeting", "press-release", "presentation", "transcript", "regulation"
}

IGNORE_KEYWORDS = {
    "brochure", "product", "catalog", "flyer", "career", "job", "tender",
    "vendor", "newsletter", "privacy-policy","policy", "terms-of-service", "contact","press-release",
    "sustainability","csr","corporate-social-responsibility","environmental","social","governance"
}

AUTO_KEEP_PATHS = [
    "/investor/", "/financial/", "/results/", "/disclosures/", "/stock-exchange/"
]

# Regex patterns
FINANCIAL_PATTERNS = [
    r"fy20\d{2}", r"fy\d{2}",         # fy2024, fy23
    r"\d{4}-\d{2}",                   # 2023-24
    r"q[1-4]",                        # q1, q2
    r"year-ended",
    r"ye-31\.03\.20\d{2}",            # ye-31.03.2023
]
YEAR_PATTERN = r"(20[0-2][0-9]|2030)" # 2000-2030

def extract_links_wrapper(data):
    """
    Recursively extracts all strings from lists with key 'downloadables' or 'downloadable_links'.
    Handles both the user-described format and the actual complex nested structure.
    """
    links = set()
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ["downloadables", "downloadable_links"] and isinstance(value, list):
                for link in value:
                    if isinstance(link, str):
                        links.add(link)
            else:
                links.update(extract_links_wrapper(value))
    elif isinstance(data, list):
        for item in data:
            links.update(extract_links_wrapper(item))
            
    return links

def score_url(url):
    """
    Scores a URL based on keywords and patterns.
    
    Returns:
        tuple: (score, result_category)
        result_category is 'useful', 'uncertain', or 'discard'
    """
    url_lower = url.lower()
    path = unquote(urlparse(url_lower).path)
    
    # 0. Check Ignore Keywords (Immediate Discard)
    for kw in IGNORE_KEYWORDS:
        if kw in url_lower:
            return -100, "discard"

    score = 0
    
    # 2. Keyword Scoring
    # Check High Priority
    for kw in HIGH_PRIORITY_KEYWORDS:
        if kw in url_lower:
            score += 5
            
    # Check Medium Priority
    for kw in MEDIUM_PRIORITY_KEYWORDS:
        if kw in url_lower:
            score += 3
            
    # 3. Regex Pattern Scoring
    for pattern in FINANCIAL_PATTERNS:
        if re.search(pattern, url_lower):
            score += 3
            
    # 4. Year Scoring
    if re.search(YEAR_PATTERN, url_lower):
        score += 1
        
    # Apply Auto-Keep logic as a safeguard or bonus
    for keep_path in AUTO_KEEP_PATHS:
        if keep_path in url_lower:
            if score < 3:
                score = 3
            break

    # 5. Decision Logic
    if score >= 3:
        return score, "useful"
    elif 1 <= score <= 2:
        return score, "uncertain"
    else:
        return score, "discard"

def process_company_file(file_path, output_dir="DATA/Pdf_links"):
    """
    Process a single company JSON file.
    Reads, filters links, and writes to output directory.
    """
    try:
        start_time = time.time()
        file_path = Path(file_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = file_path.name.replace("_crawled.json", ".json")
        output_path = output_dir / output_filename
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        company_name = data.get("company", "Unknown")
        
        # Extract all unique links
        raw_links = extract_links_wrapper(data)
        
        useful_links = []
        uncertain_links = []
        discarded_links = []
        
        for link in raw_links:
            score, category = score_url(link)
            if category == "useful":
                useful_links.append(link)
            elif category == "uncertain":
                uncertain_links.append(link)
            else:
                discarded_links.append(link)
                
        # Result Object
        result = {
            "company": company_name,
            "metadata": {
                "total_links_scanned": len(raw_links),
                "useful_links_count": len(useful_links),
                "uncertain_links_count": len(uncertain_links),
                "removed_links_count": len(discarded_links)
            },
            "all_links": sorted(list(raw_links)),
            "useful_links": sorted(useful_links),
            "uncertain_links": sorted(uncertain_links),
            "removed_links": sorted(discarded_links)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
            
        return f"Processed {company_name}: {len(useful_links)} useful, {len(uncertain_links)} uncertain, {len(discarded_links)} removed"
        
    except Exception as e:
        return f"Error processing {file_path}: {str(e)}"

def run_link_filter(input_dir="DATA/Crawled", output_dir="DATA/Pdf_links", processes=None):
    """
    Main runner function for the link filtering process.
    """
    input_path = Path(input_dir)
    json_files = list(input_path.glob("*_crawled.json"))
    
    if not json_files:
        # Fallback to just .json if pattern differs
        json_files = list(input_path.glob("*.json"))
        
    if not json_files:
        logger.warning(f"No JSON files found in {input_dir}")
        return

    logger.info(f"Found {len(json_files)} files to process.")
    
    # Determine number of processes
    if processes is None:
        processes = cpu_count()
        processes = min(processes, 8) 
        
    logger.info(f"Starting processing with {processes} processes...")
    
    start_total = time.time()
    
    with Pool(processes=processes) as pool:
        # Use partial to pass output_dir to process_company_file
        func = partial(process_company_file, output_dir=output_dir)
        results = pool.map(func, [str(p) for p in json_files])
        
    end_total = time.time()
    
    for res in results:
        if "Error" in res:
            logger.error(res)
        else:
             logger.debug(res)
             
    logger.info(f"Completed processing {len(json_files)} files in {end_total - start_total:.2f} seconds.")

