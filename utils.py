import os
import json
import re
import time
import random
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from logger import get_logger

# ---------------------------------------------------------------------------
# STRING & URL UTILITIES
# ---------------------------------------------------------------------------

def clean_company_name(query):
    """
    Extracts a likely company name from the search query.
    Removes common suffixes like 'investor relations', 'news', etc.
    """
    if not query:
        return ""

    stopwords = [
        "investor relations", "investor relation", "investors", "investor", 
        "shareholding", "shareholder", "news", "share price", "stock price",
        "limited", "ltd", "corporation", "corp", "inc"
    ]
    
    clean_query = query.lower()
    for word in stopwords:
        clean_query = clean_query.replace(word, "")
        
    # Clean up whitespace
    clean_query = re.sub(r'\s+', ' ', clean_query).strip()
    
    # Fallback
    if not clean_query:
        clean_query = query.split()[0]
        
    return clean_query.title()

def normalize_url(url: str) -> str:
    """
    Normalize URL to prevent duplicates and ensure consistency.
    - Lowercase scheme and netloc
    - Strip fragment (#)
    - Reorder query parameters
    - Remove trailing slash
    - Remove default ports
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url.strip())
        
        # 1. Lowercase scheme and netloc
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Remove default ports
        if scheme == 'http' and netloc.endswith(':80'):
            netloc = netloc[:-3]
        elif scheme == 'https' and netloc.endswith(':443'):
            netloc = netloc[:-4]

        # 2. Sort Query Params
        if parsed.query:
            qs = parse_qs(parsed.query)
            sorted_qs = urlencode(sorted(qs.items()), doseq=True)
        else:
            sorted_qs = ""
        
        # 3. Reconstruct without fragment
        path = parsed.path
        if path.endswith('/') and len(path) > 1:
            path = path.rstrip('/')
            
        return urlunparse((scheme, netloc, path, parsed.params, sorted_qs, ""))
    except Exception:
        return url

def extract_root_domain(url: str) -> str:
    """
    Extracts the root domain (e.g., 'example.com' from 'sub.example.com/path').
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Remove 'www.' if present
    if domain.startswith('www.'):
        domain = domain[4:]
        
    return domain

# ---------------------------------------------------------------------------
# FILE I/O UTILITIES
# ---------------------------------------------------------------------------

def save_json(data, folder_path, filename):
    """
    Save data to a JSON file in the specified folder.
    """
    try:
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            
        # Ensure filename ends with .json
        if not filename.lower().endswith('.json'):
            filename += '.json'
            
        filepath = os.path.join(folder_path, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            
        return filepath
    except Exception as e:
        logger = get_logger()
        logger.error(f"Failed to save JSON to {folder_path}/{filename}: {e}")
        return None

def load_json(filepath):
    """
    Load data from a JSON file.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger = get_logger()
        logger.error(f"Failed to load JSON from {filepath}: {e}")
        return None

# ---------------------------------------------------------------------------
# DELAY MANAGER
# ---------------------------------------------------------------------------

class DelayManager:
    """Manages request timing to avoid rate-limiting and blocks."""

    def __init__(self):
        # Load from env or defaults
        self.delay_min = float(os.getenv("DELAY_MIN", "1"))
        self.delay_max = float(os.getenv("DELAY_MAX", "3"))
        self.long_delay_min = float(os.getenv("LONG_DELAY_MIN", "10.0"))
        self.long_delay_max = float(os.getenv("LONG_DELAY_MAX", "15.0"))
        self.long_delay_after_count = int(os.getenv("LONG_DELAY_AFTER_COUNT", "30"))
        
        self.request_count = 0
        self.logger = get_logger()

    def wait(self):
        """
        Apply appropriate delay before the next request.
        """
        self.request_count += 1

        if (
            self.long_delay_after_count > 0
            and self.request_count % self.long_delay_after_count == 0
        ):
            delay = random.uniform(self.long_delay_min, self.long_delay_max)
            self.logger.info(
                f"Long delay triggered after {self.request_count} requests: "
                f"sleeping {delay:.1f}s"
            )
        else:
            delay = random.uniform(self.delay_min, self.delay_max)

        time.sleep(delay)

    def reset(self):
        """Reset the request counter."""
        self.request_count = 0
