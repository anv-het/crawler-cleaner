from collections import defaultdict
import re
import difflib
from urllib.parse import urlparse
from typing import List, Dict, Any
from utils import normalize_url, extract_root_domain

# ---------------------------------------------------------------------------
# CONFIGURATION CONSTANTS
# ---------------------------------------------------------------------------

INVESTOR_PATH_PATTERNS = [
    '/investor-relations', '/investor-relation',
    '/investors', '/investor', '/ir',

    '/about-us/investor-relations', '/about-us/investor-relation',
    '/about-us/investors', '/about/investor-relations',
    '/about/investor-relation', '/about/investor',
    '/aboutus/investor-relations', '/aboutus/investor-relation',

    '/corporate/investor-relations', '/corporate/investor-relation',
    '/corporate/investors', '/corporate-governance',

    '/shareholders', '/shareholder', '/shareholder-information',
    '/financials', '/financial-information', '/financial-results',
    '/annual-report', '/annual-reports', '/financial-report', 
    '/quarterly-results', '/results', '/reports',

    '/company/investor-relations', '/company/investor-relation',

    '/investor-center', '/investor_center', '/investor-centre',
    '/for-investors', '/investorrelations', '/investor_relations'
]

INVESTOR_KEYWORDS = ["investor", "financial", "finance","finances", "shareholder", "investor-relations", "annual report", "quarterly results", "financials", "reports", "corporate governance"]

# Extensions to strictly exclude
EXCLUDED_EXTENSIONS = ['.aspx',]

# Penalize non-HTML files 
NON_HTML_EXTENSIONS = ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.txt']

# Domains to skip entirely (not crawled, not ranked)
SKIP_DOMAINS = [
    "bseindia.com","nseindia.com","moneycontrol.com",
    "screener.in","trendlyne.com","economictimes.indiatimes.com",
    "ratestar.in","ticker.finology.in","investing.com",
    "alphaspread.com","groww.in","chittorgarh.com",
    "zaubacorp.com","tofler.in","finance.yahoo.com","linkdin.com"
]

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def is_likely_official_domain(company_name: str, domain: str) -> bool:
    """
    Check if the domain likely belongs to the official company website.
    """
    if not company_name or not domain:
        return False
    
    # Clean company name: remove common suffixes and special chars
    company_clean = re.sub(r'[^a-zA-Z0-9]', '', company_name.lower())
    # Also try without common suffixes
    for suffix in ['limited', 'ltd', 'pvtltd', 'private', 'inc', 'corp', 'corporation', 'industries', 'group']:
        company_clean = company_clean.replace(suffix, '')
    
    # Extract domain core (without TLD)
    # Handle multi-part TLDs (co.in, com.au) and subdomains (ir.360.one)
    domain_low = domain.lower()
    
    # 1. Strip TLDs (naively remove last one or two parts if they are short)
    parts = domain_low.split('.')
    has_numbers = any(char.isdigit() for char in domain_low)
    potential_cores = []
    
    if len(parts) >= 2:
        # Standard: domain.com
        potential_cores.append(parts[-2]) 
        
        # Combined: domain + tld
        potential_cores.append(parts[-2] + parts[-1]) 
        
        # Subdomain + Domain
        if len(parts) >= 3:
             potential_cores.append(parts[-3] + parts[-2]) 

    # Add the full domain string stripped of dots as a fallback
    potential_cores.append(re.sub(r'[^a-z0-9]', '', domain_low))
    
    # Clean company name
    company_clean = re.sub(r'[^a-zA-Z0-9]', '', company_name.lower())
    
    # Also create a version without common entity suffixes
    company_no_suffix = company_clean
    for suffix in ['limited', 'ltd', 'pvtltd', 'private', 'inc', 'corp', 'corporation', 'industries', 'group', 'services', 'management']:
        company_no_suffix = company_no_suffix.replace(suffix, '')
        
    # CHECK MATCHING
    for core in potential_cores:
        core_clean = re.sub(r'[^a-z0-9]', '', core)
        if not core_clean: continue
        
        # 1. Exact containment (high confidence)
        if core_clean in company_no_suffix or company_no_suffix in core_clean:
            return True
            
        # 2. Sequence matcher (fuzzy)
        threshold = 0.7 if len(core_clean) < 5 or len(company_no_suffix) < 5 else 0.6
        if difflib.SequenceMatcher(None, company_no_suffix, core_clean).ratio() >= threshold:
            return True
            
    return False

def is_investor_url(url: str) -> bool:
    """
    Checks if the URL path contains any of the predefined investor patterns.
    """
    if not url:
        return False
        
    parsed = urlparse(url.lower())
    path = parsed.path
    
    # Allow root domains (empty path or just /)
    if path in ['', '/']:
        return True
    
    # Skip excluded domains entirely
    domain = extract_root_domain(url)
    if domain in SKIP_DOMAINS:
        return False

    # Check exact path matches or if the pattern is a segment in the path
    for pattern in INVESTOR_PATH_PATTERNS:
        if pattern in path:
            return True
            
    return False

def is_document_file(url: str) -> bool:
    """Checks if the URL ends with a document extension."""
    parsed = urlparse(url.lower())
    path = parsed.path
    return any(path.endswith(ext) for ext in NON_HTML_EXTENSIONS)

def is_excluded(url: str) -> bool:
    """Checks if validity of URL against excluded rules."""
    parsed = urlparse(url.lower())
    path = parsed.path
    return any(path.endswith(ext) for ext in EXCLUDED_EXTENSIONS)

# ---------------------------------------------------------------------------
# SCORING FUNCTIONS
# ---------------------------------------------------------------------------

def calculate_official_score(company_name: str, domain: str) -> float:
    """
    Calculates score based on likelihood of domain being the official company site.
    """
    if not company_name or not domain:
        return 0.0

    # Skip domains get zero score (they should already be filtered out)
    if domain in SKIP_DOMAINS:
        return 0.0

    company_clean = re.sub(r'[^a-zA-Z0-9]', '', company_name.lower())
    
    # Strip TLD and dots for simple checking
    domain_parts = domain.split('.')
    if len(domain_parts) > 1:
        domain_core = max(domain_parts, key=len)
    else:
        domain_core = domain
        
    score = 0.0
    
    if domain_core in company_clean or company_clean in domain_core:
        score += 0.8
    
    seq_match = difflib.SequenceMatcher(None, company_clean, domain_core).ratio()
    score += seq_match * 0.4
    
    if len(domain) < 20: 
        score += 0.2
    
    return min(score, 1.0)

def calculate_quality_score(url: str, title: str, text: str = "") -> float:
    """
    Calculates quality score of the specific page.
    """
    score = 0.0
    parsed = urlparse(url.lower())
    path = parsed.path
    
    if path in INVESTOR_PATH_PATTERNS:
        score += 0.4
    else:
        for pattern in INVESTOR_PATH_PATTERNS:
            if pattern in path:
                score += 0.2
                break
                
    depth = path.count('/')
    if depth <= 2:
        score += 0.2
    elif depth <= 4:
        score += 0.1
        
    content_combined = (title + " " + path + " " + (text or "")).lower()
    keyword_matches = sum(1 for kw in INVESTOR_KEYWORDS if kw in content_combined)
    
    if keyword_matches >= 1:
        score += 0.2
    if keyword_matches >= 2:
        score += 0.1 # bonus
        
    if path.endswith('/') or path.split('/')[-1] in ['index.html', 'default.aspx', 'investors']:
        score += 0.1
        
    return min(score, 1.0)

def calculate_authority_score(backlinks: int, domain_freq: int, max_backlinks: int, max_freq: int) -> float:
    """
    Calculates authority score based on backlinks and frequency.
    """
    norm_backlinks = backlinks / max_backlinks if max_backlinks > 0 else 0
    norm_freq = domain_freq / max_freq if max_freq > 0 else 0
    
    # Weighted authority
    score = (0.7 * norm_backlinks) + (0.3 * norm_freq)
    return min(score, 1.0)

# ---------------------------------------------------------------------------
# MAIN RANKING FUNCTION
# ---------------------------------------------------------------------------

def rank_investor_pages(company_name: str, crawled_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Main function to rank investor relations pages.
    """
    
    # 1. Pre-processing & Filtering
    valid_items = []
    domain_counts = defaultdict(int)
    max_backlinks = 0
    
    for item in crawled_results:
        raw_url = item.get('url', '') # Use 'link' or 'url' depending on input format?
        if not raw_url:
            # Check keys
            raw_url = item.get('link', '')
        
        if not raw_url:
            continue
            
        # Normalize
        norm_url = normalize_url(raw_url)
        
        # Filter: Exclude .aspx
        if ".aspx" in norm_url.lower():
            continue

        domain = extract_root_domain(norm_url)
        
        # Filter: STRICTLY Only Allow Official Company Domains
        is_official = is_likely_official_domain(company_name, domain)
        
        if not is_official:
            continue
            
        # Filter: Excluded extensions (e.g. .aspx)
        if is_excluded(norm_url):
            continue

        is_doc = is_document_file(norm_url)
        
        domain_counts[domain] += 1
        
        backlinks = item.get('backlinks_count', 0) or 0 # handle None
        if backlinks > max_backlinks:
            max_backlinks = backlinks
            
        valid_items.append({
            'original_item': item,
            'url': norm_url,
            'domain': domain,
            'is_doc': is_doc,
            'backlinks': backlinks
        })

    # 2. Domain Grouping
    grouped_by_domain = defaultdict(list)
    for v_item in valid_items:
        grouped_by_domain[v_item['domain']].append(v_item)

    # Global Max Frequency for normalization
    max_freq = max(domain_counts.values()) if domain_counts else 1
    if max_backlinks == 0: max_backlinks = 1 # avoid div by zero

    final_results = []

    # 3. Processing each domain
    for domain, items in grouped_by_domain.items():
        
        active_items = items
        if not active_items:
            continue
            
        candidates = []
        
        # Official Score is domain-level
        official_val = calculate_official_score(company_name, domain)
        
        for item in active_items:
            orig = item['original_item']
            
            # Quality Score
            quality_val = calculate_quality_score(
                item['url'], 
                orig.get('title', ''), 
                orig.get('page_text', '') or orig.get('snippet', '')
            )
            
            # Authority Score
            auth_val = calculate_authority_score(
                item['backlinks'],
                domain_counts[domain],
                max_backlinks,
                max_freq
            )
            
            # Final Score Formula
            final_val = (0.6 * official_val) + (0.3 * quality_val) + (0.1 * auth_val)
            
            candidates.append({
                'url': item['url'],
                'domain': domain,
                'scores': {
                    'official': round(official_val, 2),
                    'quality': round(quality_val, 2),
                    'authority': round(auth_val, 2),
                    'final': round(final_val, 4)
                }
            })
            
        # 4. Collection
        for candidate in candidates:
            final_results.append({
                "company": company_name,
                "domain": candidate['domain'],
                "investor_url": candidate['url'],
                "scores": candidate['scores']
            })

    # 5. Global Ranking and Sorting
    final_results.sort(key=lambda x: x['scores']['final'], reverse=True)
    
    # Assign rank number
    for idx, res in enumerate(final_results, 1):
        res['rank'] = idx
        
    return final_results
