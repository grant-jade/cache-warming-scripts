import requests
import concurrent.futures
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import time
import xml.etree.ElementTree as ET
from datetime import datetime
import threading
import gzip
from io import BytesIO
import sys
import logging
from requests.exceptions import RequestException

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def get_user_confirmation():
    """Get user confirmation to proceed with cache warming."""
    logger.info("This script will scan sitemap files for the provided domain and warm Cloudflare cache for Australian edge servers.")
    while True:
        response = input("\nDo you wish to proceed? (y/n): ").strip().lower()
        if response == 'y':
            return True
        elif response == 'n':
            return False
        else:
            logger.warning("Please enter 'y' for yes or 'n' for no.")

class CloudflareCacheWarmer:
    def __init__(self, base_url, sitemap_url=None, rate_limit=1.0):
        self.base_url = base_url
        self.sitemap_url = sitemap_url or urljoin(base_url, '/sitemap.xml')
        self.rate_limit = rate_limit
        self.last_request_time = {}
        self.request_condition = threading.Condition()
        
        # Australian Cloudflare edge locations
        self.cf_locations = {
            'Adelaide': 'ADL',
            'Brisbane': 'BNE',
            'Melbourne': 'MEL',
            'Perth': 'PER',
            'Sydney': 'SYD'
        }

    def fetch_sitemap(self, sitemap_url):
        """Fetch and parse a sitemap, handling both regular and gzipped sitemaps."""
        try:
            response = requests.get(sitemap_url, timeout=10)
            response.raise_for_status()
            
            # Handle gzipped content
            if response.headers.get('Content-Type', '').startswith('application/x-gzip') or sitemap_url.endswith('.gz'):
                content = gzip.GzipFile(fileobj=BytesIO(response.content)).read()
            else:
                content = response.content

            return ET.fromstring(content)
        except RequestException as e:
            logger.error(f"Error fetching sitemap {sitemap_url}: {e}")
            return None

    def process_sitemap(self, sitemap_url, processed_sitemaps=None):
        """Process a sitemap and return all URLs, handling nested sitemaps."""
        if processed_sitemaps is None:
            processed_sitemaps = set()
        
        if sitemap_url in processed_sitemaps:
            return []
        
        processed_sitemaps.add(sitemap_url)
        urls = []

        logger.info(f"Processing sitemap: {sitemap_url}")
        root = self.fetch_sitemap(sitemap_url)
        if root is None:
            return urls

        # Handle sitemap index
        for sitemap in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
            sitemap_text = sitemap.text.strip()
            if sitemap_text.endswith(('.xml', '.xml.gz')):
                urls.extend(self.process_sitemap(sitemap_text, processed_sitemaps))

        # Handle regular sitemap
        for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
            url_text = url.text.strip()
            if not url_text.endswith(('.xml', '.xml.gz')):
                if '/wp-admin/' not in url_text:
                    urls.append(url_text)

        return urls

    def get_urls_from_sitemap(self):
        """Extract URLs from all sitemaps."""
        logger.info("Fetching URLs from sitemaps...")
        urls = self.process_sitemap(self.sitemap_url)
        logger.info(f"Found {len(urls)} valid URLs in all sitemaps")
        return urls

    def crawl_website(self):
        """Crawl website to extract URLs (fallback method)."""
        visited = set()
        to_visit = {self.base_url}
        urls = []

        logger.info("Falling back to crawling website...")
        while to_visit and len(urls) < 100:
            url = to_visit.pop()
            if url in visited:
                continue

            try:
                response = requests.get(url, timeout=10)
                visited.add(url)
                urls.append(url)

                soup = BeautifulSoup(response.content, 'html.parser')
                for link in soup.find_all('a', href=True):
                    full_url = urljoin(self.base_url, link['href'])
                    if full_url.startswith(self.base_url) and full_url not in visited:
                        to_visit.add(full_url)

                logger.info(f"Crawled {len(urls)} URLs so far...")
            except RequestException as e:
                logger.error(f"Error crawling {url}: {e}")

        logger.info(f"Found {len(urls)} valid URLs through crawling")
        return urls

    def apply_rate_limit(self, location):
        """Enforce rate limiting for requests."""
        with self.request_condition:
            current_time = time.time()
            if location in self.last_request_time:
                time_since_last = current_time - self.last_request_time[location]
                if time_since_last < self.rate_limit:
                    sleep_time = self.rate_limit - time_since_last
                    logger.debug(f"Rate limit active. Sleeping for {sleep_time:.2f} seconds")
                    self.request_condition.wait(sleep_time)
            self.last_request_time[location] = time.time()

    def warm_cache(self, url, location_name, location_code):
        """Warm cache for a specific URL from a specific location."""
        self.apply_rate_limit(location_code)

        headers = {
            'User-Agent': 'CloudflareWarmer/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Cache-Control': 'no-cache',
            'CF-IPCountry': 'AU',
            'CF-RAY': location_code
        }

        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=10)
            end_time = time.time()
            response_time = round(end_time - start_time, 2)
            
            logger.info(f"{location_name:<10} | {url:<50.50} | Status: {response.status_code:<3} | Time: {response_time:<5.2f}s")
            return True
        except RequestException as e:
            logger.error(f"Error warming {url} from {location_name}: {e}")
            return False

    def warm_all_locations(self):
        """Warm cache from all Australian edge locations."""
        if not get_user_confirmation():
            logger.info("Operation cancelled by user.")
            return

        logger.info("Starting cache warming process...")

        urls = self.get_urls_from_sitemap() or self.crawl_website()
        if not urls:
            logger.warning("No URLs found to process!")
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.cf_locations)) as executor:
            tasks = [
                executor.submit(self.warm_cache, url, loc_name, loc_code)
                for url in urls for loc_name, loc_code in self.cf_locations.items()
            ]

            for completed, _ in enumerate(concurrent.futures.as_completed(tasks), 1):
                if completed % len(self.cf_locations) == 0:
                    logger.info(f"Progress: {completed // len(self.cf_locations)}/{len(urls)} URLs completed")

        logger.info("Cache warming process completed.")

if __name__ == "__main__":
    try:
        base_url = input("Please enter the target website URL (including https://): ").strip()
        if not base_url:
            logger.error("No URL provided. Exiting...")
            sys.exit(1)

        warmer = CloudflareCacheWarmer(base_url, rate_limit=0.0)
        warmer.warm_all_locations()

    except KeyboardInterrupt:
        logger.warning("Script interrupted by user. Exiting...")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
