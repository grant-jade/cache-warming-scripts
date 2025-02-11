import requests
import time
from typing import List, Dict, Tuple, Set
import sys
from datetime import datetime
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

# BunnyCDN edge nodes locations
# Source: https://bunny.net/network/
BUNNY_NODES = {
    'Oceania': [
        'Sydney, Australia', 'Auckland, New Zealand',
        'Melbourne, Australia'
    ],
    'Europe': [
        'London, UK', 'Frankfurt, Germany', 'Paris, France', 
        'Amsterdam, Netherlands', 'Stockholm, Sweden', 'Warsaw, Poland',
        'Madrid, Spain', 'Prague, Czech Republic', 'Vienna, Austria',
        'Bucharest, Romania'
    ],
    'North America': [
        'New York, USA', 'Los Angeles, USA', 'Miami, USA', 
        'Chicago, USA', 'Dallas, USA', 'Seattle, USA',
        'Toronto, Canada', 'Vancouver, Canada'
    ],
    'Asia': [
        'Tokyo, Japan', 'Singapore', 'Seoul, South Korea',
        'Mumbai, India', 'Hong Kong', 'Bangkok, Thailand',
        'Jakarta, Indonesia', 'Bangalore, India'
    ],
    'South America': [
        'São Paulo, Brazil', 'Santiago, Chile',
        'Buenos Aires, Argentina'
    ],
    'Africa': [
        'Johannesburg, South Africa', 'Lagos, Nigeria',
        'Cape Town, South Africa'
    ]
}

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries
COMMON_SITEMAP_PATHS = [
    '/sitemap.xml',
    '/sitemap_index.xml',
    '/sitemap/',
    '/sitemaps/',
    '/sitemap/sitemap.xml',
    '/wp-sitemap.xml'  # WordPress default
]

def fetch_with_retry(url: str, timeout: int = 10) -> Tuple[bool, str, str]:
    """Fetch a URL with retry logic and return success status, content, and error message."""
    headers = {'User-Agent': 'Cache-Warmer/1.0'}
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return True, response.text, ""
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return False, "", str(e)
    
    return False, "", "Max retries reached"

def find_sitemap_url(base_url: str) -> str:
    """Try to locate the sitemap URL by checking common paths."""
    print("\nSearching for sitemap...")
    
    for path in COMMON_SITEMAP_PATHS:
        sitemap_url = urljoin(base_url, path)
        print(f"Checking {sitemap_url}...", end=" ", flush=True)
        
        success, _, error = fetch_with_retry(sitemap_url, timeout=5)
        if success:
            print("✓ Found!")
            return sitemap_url
        print("✗")
    
    return None

def parse_sitemap(url: str, discovered_urls: Set[str]) -> None:
    """
    Parse a sitemap file (both regular sitemaps and sitemap indexes)
    and add discovered URLs to the set.
    """
    success, content, error = fetch_with_retry(url)
    if not success:
        print(f"\nError fetching sitemap {url}: {error}")
        return
    
    try:
        root = ET.fromstring(content)
        # Remove namespace for easier parsing
        namespace = root.tag.split('}')[0] + '}'
        
        # Check if this is a sitemap index
        if root.tag == f"{namespace}sitemapindex":
            for sitemap in root.findall(f".//{namespace}sitemap/{namespace}loc"):
                sub_sitemap_url = sitemap.text.strip()
                print(f"\nProcessing sub-sitemap: {sub_sitemap_url}")
                parse_sitemap(sub_sitemap_url, discovered_urls)
        else:
            # Regular sitemap
            for url_element in root.findall(f".//{namespace}url/{namespace}loc"):
                url = url_element.text.strip()
                discovered_urls.add(url)
                
    except ET.ParseError as e:
        print(f"\nError parsing sitemap {url}: {e}")

def confirm_operation(urls: List[str]) -> bool:
    """Ask for user confirmation before proceeding."""
    print(f"\nPreparing to warm BunnyCDN cache for {len(urls)} URLs:")
    print(f"First few URLs:")
    for url in urls[:5]:
        print(f"- {url}")
    if len(urls) > 5:
        print(f"... and {len(urls) - 5} more")
    
    print(f"\nThis will send {len(urls)} requests to each of the {sum(len(nodes) for nodes in BUNNY_NODES.values())} BunnyCDN edge nodes worldwide.")
    print(f"Total requests to be made: {len(urls) * sum(len(nodes) for nodes in BUNNY_NODES.values())}")
    
    response = input("\nDo you want to continue? (y/n): ").lower().strip()
    return response == 'y'

def calculate_progress(current: int, total: int) -> int:
    """Calculate progress percentage."""
    return int((current / total) * 100)

def make_request(url: str, location: str) -> Tuple[bool, str]:
    """Make a request with retry logic."""
    headers = {
        'User-Agent': 'Cache-Warmer/1.0',
        'Cache-Control': 'no-cache'
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return True, "✓"
            else:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return False, f"✗ (HTTP {response.status_code})"
                
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return False, f"✗ ({type(e).__name__})"
    
    return False, "✗ (Max retries reached)"

def print_status(progress: int, location: str, status: str, url: str = "", attempt: int = None) -> None:
    """Print the current status with retry information if applicable."""
    retry_info = f" (Attempt {attempt}/{MAX_RETRIES})" if attempt is not None else ""
    url_info = f" - {url}" if url else ""
    sys.stdout.write(f"\r[{progress:3d}%] {location:<25} {status}{retry_info}{url_info}")
    sys.stdout.flush()

def warm_cache(urls: List[str]) -> None:
    """Warm the cache for the specified URLs across all BunnyCDN nodes."""
    total_operations = len(urls) * sum(len(nodes) for nodes in BUNNY_NODES.values())
    processed_operations = 0
    failed_operations = []
    
    print("\nStarting cache warming process...\n")
    start_time = datetime.now()
    
    for url in urls:
        print(f"\nWarming cache for: {url}")
        
        for region, locations in BUNNY_NODES.items():
            print(f"\n{region}:")
            for location in locations:
                processed_operations += 1
                progress = calculate_progress(processed_operations, total_operations)
                
                # Try the request with retries
                for attempt in range(MAX_RETRIES):
                    print_status(progress, location, "⋯", url, attempt + 1)
                    
                    success, status = make_request(url, location)
                    if success:
                        break
                    elif attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                
                # Final status update
                print_status(progress, location, status, url)
                print()  # New line after each location
                
                if not success:
                    failed_operations.append((url, location, status))
                
                # Add small delay before next node
                time.sleep(0.5)
    
    # Print summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\nCache warming process completed!")
    print(f"Duration: {duration:.1f} seconds")
    print(f"Successful operations: {total_operations - len(failed_operations)}/{total_operations}")
    
    if failed_operations:
        print("\nFailed operations:")
        for url, node, status in failed_operations:
            print(f"- {url} at {node}: {status}")

def main():
    base_url = "http://22355-dark-shape.site.hardypress.com/"
    discovered_urls = set()
    
    # First, try to find the sitemap
    sitemap_url = find_sitemap_url(base_url)
    if not sitemap_url:
        print("\nNo sitemap found. Would you like to:")
        print("1. Proceed with just the homepage")
        print("2. Enter a sitemap URL manually")
        print("3. Cancel operation")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == "1":
            discovered_urls.add(base_url)
        elif choice == "2":
            manual_sitemap = input("\nEnter the sitemap URL: ").strip()
            parse_sitemap(manual_sitemap, discovered_urls)
        else:
            print("Operation cancelled.")
            return
    else:
        # Parse the found sitemap
        parse_sitemap(sitemap_url, discovered_urls)
        
        # Always include the homepage
        discovered_urls.add(base_url)
    
    # Convert to sorted list for consistent ordering
    urls_to_warm = sorted(discovered_urls)
    
    if not urls_to_warm:
        print("No URLs found to process. Exiting.")
        return
    
    if not confirm_operation(urls_to_warm):
        print("Operation cancelled by user.")
        return
    
    warm_cache(urls_to_warm)

if __name__ == "__main__":
    main()
