import requests
import time
from typing import List, Dict, Tuple
import sys
from datetime import datetime

# BunnyCDN edge nodes locations
BUNNY_NODES = {
    'Oceania': [
        'Sydney, Australia', 'Auckland, New Zealand',
        'Melbourne, Australia'
    ],
    'North America': [
        'New York, United States', 'Miami, United States', 'Dallas, United States',
        'Los Angeles, United States', 'Toronto, Canada', 'Vancouver, Canada',
        'Mexico City, Mexico'
    ],
    'Europe': [
        'London, United Kingdom', 'Amsterdam, Netherlands', 'Frankfurt, Germany',
        'Paris, France', 'Stockholm, Sweden', 'Warsaw, Poland', 'Madrid, Spain',
        'Milan, Italy', 'Prague, Czech Republic', 'Bucharest, Romania',
        'Sofia, Bulgaria', 'Vienna, Austria', 'Zurich, Switzerland'
    ],
    'Asia': [
        'Tokyo, Japan', 'Singapore', 'Seoul, South Korea', 'Hong Kong',
        'Bangalore, India', 'Delhi, India', 'Dubai, UAE', 'Tel Aviv, Israel',
        'Jakarta, Indonesia', 'Taipei, Taiwan', 'Bangkok, Thailand'
    ],
    'South America': [
        'Sao Paulo, Brazil', 'Buenos Aires, Argentina', 'Santiago, Chile',
        'Bogota, Colombia', 'Lima, Peru'
    ],
    'Africa': [
        'Johannesburg, South Africa', 'Cape Town, South Africa', 'Lagos, Nigeria',
        'Nairobi, Kenya', 'Cairo, Egypt'
    ]
}

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries
NUM_RUNS = 5

def read_domains() -> List[str]:
    """Read domains from user input."""
    print("\nEnter domains (one per line). Press Ctrl+D (Unix) or Ctrl+Z (Windows) when done:")
    domains = []
    try:
        while True:
            domain = input().strip()
            if domain:  # Skip empty lines
                # Ensure domain has proper scheme
                if not domain.startswith(('http://', 'https://')):
                    domain = 'https://' + domain
                domains.append(domain)
    except (EOFError, KeyboardInterrupt):
        if domains:
            return domains
        print("\nNo domains entered. Exiting...")
        sys.exit(0)

def verify_domains(domains: List[str]) -> List[str]:
    """Verify all domains are accessible."""
    verified_domains = []
    print("\nVerifying domains...")
    
    for domain in domains:
        try:
            response = requests.head(domain, timeout=5)
            print(f"✓ {domain}: {response.status_code} OK")
            verified_domains.append(domain)
        except requests.exceptions.RequestException as e:
            print(f"✗ {domain}: Error - {str(e)}")
    
    return verified_domains

def get_user_confirmation(domains: List[str]) -> bool:
    """Get user confirmation to proceed with cache warming."""
    print(f"\nThis script will warm the cache for {len(domains)} domains across all BunnyCDN nodes.")
    print(f"Each domain will receive {NUM_RUNS} requests to Oceania nodes and single requests to worldwide nodes.")
    print("\nDomains to process:")
    for domain in domains:
        print(f"- {domain}")
    
    while True:
        try:
            print("\nDo you wish to proceed? (y/n): ", end='', flush=True)
            response = input().strip().lower()
            if response == 'y':
                return True
            elif response == 'n':
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no.")
        except (EOFError, KeyboardInterrupt):
            return False

def calculate_total_operations() -> int:
    """Calculate total operations across all phases."""
    oceania_ops = NUM_RUNS * len(BUNNY_NODES['Oceania'])
    worldwide_ops = sum(len(nodes) for region, nodes in BUNNY_NODES.items() if region != 'Oceania')
    return oceania_ops + worldwide_ops

def calculate_progress(current_run: int, current_region_idx: int, current_location_idx: int, 
                      total_locations: int, phase: str) -> int:
    """Calculate progress percentage based on the total operations across all phases."""
    total_ops = calculate_total_operations()
    
    if phase == 'oceania':
        completed_ops = ((current_run - 1) * len(BUNNY_NODES['Oceania'])) + current_location_idx
    else:
        completed_ops = NUM_RUNS * len(BUNNY_NODES['Oceania'])
        other_regions = [region for region in BUNNY_NODES.keys() if region != 'Oceania']
        for i in range(current_region_idx):
            if i < len(other_regions):
                completed_ops += len(BUNNY_NODES[other_regions[i]])
        completed_ops += current_location_idx
    
    return int((completed_ops / total_ops) * 100)

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

def print_status(progress: int, location: str, status: str, attempt: int = None, current_run: int = None, region: str = None) -> None:
    """Print the current status with retry information if applicable."""
    region_info = f"[{region}] " if region else ""
    status_line = f"\r[{progress:3d}%] {region_info}{location:<35} {status}"
    
    if attempt is not None and attempt > 0:
        status_line += f" (Attempt {attempt}/{MAX_RETRIES})"
    
    if current_run is not None:
        status_line += f" [Run {current_run}/{NUM_RUNS}]"
    
    print(status_line.ljust(100), end='', flush=True)

def warm_cache(url: str) -> List[Tuple[str, str, int, str]]:
    """Warm the cache for the specified URL across all BunnyCDN nodes."""
    failed_nodes = []
    
    # Phase 1: Process Oceania nodes with 5 runs
    print("\nPhase 1: Warming Oceania nodes (5 runs)")
    
    for run in range(1, NUM_RUNS + 1):
        print(f"\n--- Run {run} of {NUM_RUNS} - Oceania Nodes ---\n")
        
        for idx, location in enumerate(BUNNY_NODES['Oceania'], 1):
            progress = calculate_progress(run, 0, idx, len(BUNNY_NODES['Oceania']), 'oceania')
            
            for attempt in range(MAX_RETRIES):
                print_status(progress, location, "⋯", attempt + 1, run, "Oceania")
                
                success, status = make_request(url, location)
                if success:
                    break
                elif attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
            
            print_status(progress, location, status, current_run=run, region="Oceania")
            print()
            
            if not success:
                failed_nodes.append((location, status, run, "Oceania"))
            
            time.sleep(0.5)
    
    # Phase 2: Process all other regions (single run)
    print("\nPhase 2: Warming worldwide nodes (single run)")
    
    other_regions = [region for region in BUNNY_NODES.keys() if region != 'Oceania']
    for region_idx, region in enumerate(other_regions, 1):
        print(f"\n--- Processing {region} Region ---\n")
        
        for loc_idx, location in enumerate(BUNNY_NODES[region], 1):
            progress = calculate_progress(1, region_idx, loc_idx, 
                                       sum(len(BUNNY_NODES[r]) for r in other_regions),
                                       'worldwide')
            
            for attempt in range(MAX_RETRIES):
                print_status(progress, location, "⋯", attempt + 1, region=region)
                
                success, status = make_request(url, location)
                if success:
                    break
                elif attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
            
            print_status(progress, location, status, region=region)
            print()
            
            if not success:
                failed_nodes.append((location, status, 1, region))
            
            time.sleep(0.5)
    
    return failed_nodes

def process_domains(domains: List[str]) -> None:
    """Process multiple domains sequentially."""
    total_start_time = datetime.now()
    domain_results = []
    
    for i, domain in enumerate(domains, 1):
        print(f"\n{'='*80}\nProcessing domain {i}/{len(domains)}: {domain}\n{'='*80}")
        
        domain_start_time = datetime.now()
        failed_nodes = warm_cache(domain)
        domain_end_time = datetime.now()
        
        domain_duration = (domain_end_time - domain_start_time).total_seconds()
        total_ops = calculate_total_operations()
        successful_ops = total_ops - len(failed_nodes)
        
        domain_results.append({
            'domain': domain,
            'duration': domain_duration,
            'success_rate': successful_ops / total_ops,
            'failed_nodes': failed_nodes
        })
        
        if i < len(domains):
            print(f"\nWaiting 60 seconds before processing next domain...")
            time.sleep(60)
    
    # Print final summary
    total_end_time = datetime.now()
    total_duration = (total_end_time - total_start_time).total_seconds()
    
    print("\nFinal Summary")
    print("=" * 80)
    print(f"Total domains processed: {len(domains)}")
    print(f"Total duration: {total_duration:.1f} seconds")
    
    for result in domain_results:
        print(f"\nDomain: {result['domain']}")
        print(f"Duration: {result['duration']:.1f} seconds")
        print(f"Success rate: {result['success_rate']*100:.1f}%")
        
        if result['failed_nodes']:
            print("Failed nodes:")
            for node, status, run, region in result['failed_nodes']:
                run_info = f"Run {run}" if region == "Oceania" else "Single Run"
                print(f"- {node} ({region}): {status} ({run_info})")
    
    print("=" * 80)

def main():
    try:
        # Read and verify domains
        domains = read_domains()
        verified_domains = verify_domains(domains)
        
        if not verified_domains:
            print("\nNo valid domains to process. Exiting...")
            sys.exit(1)
        
        # Get user confirmation
        if get_user_confirmation(verified_domains):
            process_domains(verified_domains)
        else:
            print("\nOperation cancelled by user.")
            
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nAn error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
