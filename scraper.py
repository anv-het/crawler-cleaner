import os
import heapq
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import concurrent.futures
import threading
from dotenv import load_dotenv

from logger import get_logger
from utils import DelayManager, normalize_url

load_dotenv()


# ============================================================================
# SCORING CONFIGURATION
# ============================================================================

# HIGH VALUE: Things we definitely want to crawl (investor / financial content)
TARGET_KEYWORDS = [
    # Investor Relations
    "investor", "investors", "investor-relations", "investor-relation",
    "investorrelations", "investor_relations", "ir",

    # Financial Results & Reports
    "financial", "financials", "financial-results", "financial-information",
    "quarterly", "quarterly-results", "annual-report", "annual-reports",
    "financial-report", "financial-reports", "results", "reports",
    "earnings", "revenue", "profit", "balance-sheet", "income-statement",
    "cash-flow", "fiscal", "audited", "unaudited", "standalone", "consolidated",

    # Shareholding & Shareholders
    "shareholding", "shareholding-pattern", "shareholder", "shareholders",
    "shareholder-information", "equity", "stakeholder",

    # Governance & Corporate
    "corporate-governance", "governance", "board-of-directors", "board",
    "committees", "audit-committee", "compliance",

    # Stock & Market
    "stock", "share-price", "bse", "nse", "listing", "dividend",
    "bonus", "split", "buyback", "ipo",

    # Documents & Filings
    "disclosure", "filings", "notices", "agm", "egm", "postal-ballot",
    "annual-general-meeting", "prospectus", "offer-document",
    "code-of-conduct", "policies", "secretarial",

    # Downloadables
    "download", "pdf", "documents", "presentations", "factsheet",
    "press-release", "press-releases", "media-release","sheets","documents","docx","xlsx","xls","csv","txt","zip","rar","7z","tar","gz"
]

# MEDIUM VALUE: Generic navigation sections that often lead to investor pages
NAVIGATION_KEYWORDS = [
    "about", "about-us", "aboutus", "corporate", "company",
    "who-we-are", "group", "overview", "organization",
    "media", "press", "news", "updates", "announcements",
    "sustainability", "esg", "csr", "responsibility",
]

# NEGATIVE VALUE: Noise that should never be crawled
NOISE_KEYWORDS = [
    # Navigation & Locations
    "maps", "location", "locate-us", "directions", "store-locator", "find-us", "where-to-buy",
    "map", "dealers", "distributors", "network", "branches", "offices", "global-presence",

    # E-commerce & Shopping
    "cart", "checkout", "basket", "buy-now", "shop", "store", "products", "services",
    "pricing", "plans", "offers", "discount", "sale", "orders", "track-order", "wishlist",
    "compare", "shipping", "return", "payment", "invoice", "billing", "solutions",
    "catalog", "category", "collection", "brands", "marketplace", "specials", "clearance",

    # User Accounts & Auth
    "login", "signin", "signup", "register", "account", "profile", "dashboard",
    "my-account", "user", "member", "password", "reset-password", "forgot-password",
    "verify", "otp", "preferences", "settings", "logout", "sign-in", "sign-up",
    "login-register",

    # Support & Help
    "contact", "support", "help", "faq", "feedback", "customer-service", "support-center",
    "help-center", "community", "forum", "faqs", "manual", "documentation", "guide",
    "tutorial", "troubleshooting", "ticket", "inquiry", "complaint", "reach-us",

    # Careers & HR
    "careers", "jobs", "hiring", "join-us", "work-with-us", "internships", "vacancy",
    "opportunities", "resume", "apply", "culture", "life-at", "recruitment", "talent",
    "openings", "positions", "job-search", "people", "team",

    # Generic Media & content
    "blog", "article", "videos", "images", "photo", "photos", "audio", "gallery",
    "podcast", "webinar", "media-kit", "assets", "downloadqrcode", "qr-code",
    "feed", "rss", "subscribe", "newsletter",

    # Legal & Misc
    "privacy", "terms", "cookie", "disclaimer", "legal", "accessibility",
    "sitemap", "action", "api", "search", "filter", "sort",
    "calculator", "tools", "converter", "weather", "calendar", "survey", "poll",
    "loans", "mortgage", "credit", "loan", "case-study", "case-studies", "partners",
    "taxonomy", "tag", "archive", "page", "print", "share", "email", "mobile-app",
]

# Scoring Weights
TARGET_SCORE = 50
NAVIGATION_SCORE = 20
NOISE_SCORE = -100       # Hard negative — effectively blocks it via threshold
BASE_SCORE = 5
DEPTH_PENALTY = 5        # Points lost per URL depth level
SCORE_THRESHOLD = -10    # Links scoring below this are discarded, never queued


# ============================================================================
# SCORING FUNCTION
# ============================================================================

def score_url(url: str) -> int:
    """
    Calculate a relevance score for a URL.
    Higher score = more relevant to investor/financial content.
    """
    url_lower = url.lower()
    parsed = urlparse(url_lower)
    path = parsed.path

    score = BASE_SCORE

    # Target keywords (high value)
    for kw in TARGET_KEYWORDS:
        if kw in path:
            score += TARGET_SCORE
            break  # One match is enough for the bonus

    # Navigation keywords (medium value)
    for kw in NAVIGATION_KEYWORDS:
        if kw in path:
            score += NAVIGATION_SCORE
            break

    # Noise keywords (negative value)
    for kw in NOISE_KEYWORDS:
        if kw in url_lower:
            score += NOISE_SCORE
            break  # One noise match is enough to kill it

    # Depth penalty: deeper pages are less likely to be landing pages
    depth = path.strip("/").count("/") if path.strip("/") else 0
    score -= depth * DEPTH_PENALTY

    return score


# ============================================================================
# CRAWLER CLASS
# ============================================================================

class PageCrawler:
    """Visit URLs and extract all hyperlinks using a scored priority queue."""

    # Social media and noise domains to ignore entirely
    BLACKLIST_DOMAINS = {
        "facebook.com", "www.facebook.com",
        "twitter.com", "www.twitter.com", "x.com",
        "linkedin.com", "www.linkedin.com",
        "instagram.com", "www.instagram.com",
        "youtube.com", "www.youtube.com",
        "pinterest.com", "www.pinterest.com",
        "tiktok.com", "www.tiktok.com",
        "reddit.com", "www.reddit.com",
        "whatsapp.com", "api.whatsapp.com"
    }

    def __init__(self):
        self.timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))
        self.user_agent = os.getenv("USER_AGENT", "Mozilla/5.0")

        self.delay_manager = DelayManager()
        self.logger = get_logger()

        # Thread-safe session
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )
        self.session.max_redirects = 60

        # Global Visited Set & Lock
        self.visited = set()
        self.visited_lock = threading.Lock()

        # Collected downloadable links (unique, across all crawls in this session)
        self.all_downloadables = set()
        self.downloadables_lock = threading.Lock()

        # Define extensions to be grouped under "downloadables"
        self.downloadable_extensions = {
            ".pdf", ".doc", ".docx", ".rtf",
            ".xls", ".xlsx", ".csv",
            ".xml", ".txt",
            ".ppt", ".pptx",
            ".zip", ".rar", ".7z", ".tar", ".gz"
        }

    def crawl_page(self, url: str) -> dict:
        """Visit a URL and extract all links from the page."""
        self.logger.info(f"Crawling page: {url}")
        result = {
            "url": url,
            "page_title": "",
            "status": None,
            "metadata": {
                "total_links": 0,
                "total_downloadables": 0
            },
            "links": [],
            "downloadables": []
        }

        try:
            self.delay_manager.wait()
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except Exception as e:
                self.logger.warning(f"Request failed, retrying: {e}")
                self.delay_manager.wait()
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)

            result["status"] = response.status_code

            if response.status_code != 200:
                self.logger.warning(f"Non-200 status ({response.status_code}) for: {url}")
                return result

            soup = BeautifulSoup(response.text, "lxml")

            title_tag = soup.find("title")
            result["page_title"] = title_tag.get_text(strip=True) if title_tag else ""

            collected_links = {"links": set(), "downloadables": set()}

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                    continue

                absolute_url = urljoin(url, href)
                parsed = urlparse(absolute_url)
                if parsed.scheme not in ("http", "https"):
                    continue

                path_lower = parsed.path.lower()

                # Skip .aspx pages
                if path_lower.endswith(".aspx") :
                    continue

                # Categorize
                is_downloadable = False
                for ext in self.downloadable_extensions:
                    if path_lower.endswith(ext):
                        collected_links["downloadables"].add(absolute_url)
                        is_downloadable = True
                        break

                if not is_downloadable:
                    collected_links["links"].add(absolute_url)

            for key in collected_links:
                result[key] = sorted(list(collected_links[key]))

            result["metadata"]["total_links"] = len(result["links"])
            result["metadata"]["total_downloadables"] = len(result["downloadables"])

            # Track downloadables globally (unique across all crawls)
            with self.downloadables_lock:
                self.all_downloadables.update(collected_links["downloadables"])

            self.logger.info(
                f"Crawled {url}: {result['metadata']['total_links']} links, "
                f"{result['metadata']['total_downloadables']} downloadables."
            )

        except Exception as e:
            result["status"] = f"ERROR: {str(e)}"
            self.logger.error(f"Error crawling {url}: {e}")

        return result

    def normalize_url(self, url):
        return normalize_url(url)

    def _is_same_domain(self, url: str, base_domain: str) -> bool:
        """Check if URL belongs to the same domain (or subdomain)."""
        try:
            netloc = urlparse(url).netloc.lower()
            for bad_domain in self.BLACKLIST_DOMAINS:
                if bad_domain in netloc:
                    return False
            return netloc.endswith(base_domain)
        except:
            return False

    def crawl_hierarchy(self, start_url: str) -> dict:
        """
        Priority-Queue BFS Crawler.

        Uses a min-heap (negated scores for max-priority) to always crawl the
        most relevant URLs first. Links scoring below SCORE_THRESHOLD are
        discarded and never visited.
        """

        normalized_start = self.normalize_url(start_url)

        # Priority queue: list of (-score, counter, url)
        # counter is used as tiebreaker so heapq never compares strings
        pq = []
        counter = 0

        with self.visited_lock:
            if normalized_start not in self.visited:
                self.visited.add(normalized_start)
                start_score = score_url(start_url)
                heapq.heappush(pq, (-start_score, counter, start_url))
                counter += 1
            else:
                self.logger.info(f"Skipping start URL (already visited): {start_url}")

        # Determine Scope
        try:
            parsed_start = urlparse(start_url)
            base_domain = parsed_start.netloc.replace("www.", "")
        except:
            base_domain = ""

        url_tree = {}
        metadata = {
            "total_pages_crawled": 0,
            "total_links_found": 0,
            "total_downloadables_found": 0
        }

        self.logger.info(f"Starting Priority BFS Crawl on {start_url}")

        MAX_WORKERS = int(os.getenv("MAX_WORKERS", "30"))

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

            while pq:
                # Pop a batch of the highest-scoring URLs from the priority queue
                batch_size = min(len(pq), MAX_WORKERS)
                current_batch = []
                for _ in range(batch_size):
                    if pq:
                        neg_score, _cnt, url = heapq.heappop(pq)
                        current_batch.append(url)

                if not current_batch:
                    break

                future_to_url = {
                    executor.submit(self.crawl_page, url): url
                    for url in current_batch
                }

                self.logger.info(f"Processing batch of {len(current_batch)} URLs (queue remaining: {len(pq)})...")

                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        page_data = future.result()

                        metadata["total_pages_crawled"] += 1
                        metadata["total_links_found"] += page_data["metadata"]["total_links"]
                        metadata["total_downloadables_found"] += page_data["metadata"]["total_downloadables"]

                        self._insert_into_tree(url_tree, url, page_data)

                        # Score and enqueue child links
                        links_found = page_data.get("links", [])
                        for link in links_found:
                            normalized_link = self.normalize_url(link)

                            with self.visited_lock:
                                if normalized_link in self.visited:
                                    continue

                                # Domain check
                                if not self._is_same_domain(link, base_domain):
                                    continue

                                # Score the link
                                link_score = score_url(link)

                                # THRESHOLD: discard noise immediately
                                if link_score < SCORE_THRESHOLD:
                                    continue

                                self.visited.add(normalized_link)
                                heapq.heappush(pq, (-link_score, counter, link))
                                counter += 1

                    except Exception as e:
                        self.logger.error(f"Error processing {url}: {e}")

        self.logger.info(f"Priority Crawl Completed. Total pages: {metadata['total_pages_crawled']}")

        return {
            "metadata": metadata,
            "structure": url_tree
        }

    def get_unique_downloadables(self) -> list:
        """Return all unique downloadable links collected across all crawls."""
        with self.downloadables_lock:
            return sorted(list(self.all_downloadables))

    def _insert_into_tree(self, root_tree: dict, url: str, page_data: dict):
        """Insert a page's data into the tree structure based on its URL path segments."""
        parsed = urlparse(url)
        if parsed.path.strip("/"):
            path_segments = parsed.path.strip("/").split("/")
        else:
            path_segments = []

        domain_part = parsed.netloc.replace("www.", "").split(".")[0]
        keys = [domain_part] + [s for s in path_segments if s]

        current_level = root_tree

        for i, key in enumerate(keys):
            key = key.lower().replace(" ", "_")
            if not key:
                continue

            if key not in current_level:
                current_level[key] = {}

            current_level = current_level[key]

            if i == len(keys) - 1:
                current_level["_url"] = url
                current_level["_title"] = page_data.get("page_title")
                current_level["_metadata"] = page_data.get("metadata")
                current_level["downloadables"] = page_data.get("downloadables", [])
                current_level["links"] = page_data.get("links", [])

    def close(self):
        self.session.close()

