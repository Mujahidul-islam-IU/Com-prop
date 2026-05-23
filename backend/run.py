"""
Quick-launch script: reads config.py and calls the scraper.
Run: python run.py
"""
import sys
import io
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Windows console unicode errors
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Import config values
try:
    from config import (
        LOCATION, KEYWORD, MIN_SIZE, LISTING_TYPE,
        MAX_PAGES, FETCH_DETAILS, OUTPUT_DIR
    )
except ImportError:
    print("❌  config.py not found. Copy config.py.example to config.py and edit it.")
    sys.exit(1)

from scraper import run_scraper

if __name__ == "__main__":
    print(f"""
============================================================
  Commercial Real Estate Scraper — Quick Launch
============================================================
  Location  : {LOCATION:<45} 
  Keyword   : {KEYWORD:<45} 
  Min Size  : {f"{MIN_SIZE} m2":<45} 
  Type      : {LISTING_TYPE:<45} 
  Max Pages : {str(MAX_PAGES):<45} 
  Fetch Detail Pages: {str(FETCH_DETAILS):<38} 
  Output    : {OUTPUT_DIR:<45} 
============================================================
    """)
    results = run_scraper(
        location=LOCATION,
        keyword=KEYWORD,
        min_size=MIN_SIZE,
        listing_type=LISTING_TYPE,
        max_pages=MAX_PAGES,
        fetch_details=FETCH_DETAILS,
        output_dir=OUTPUT_DIR,
    )
    print(f"\n✅  Scraped {len(results)} properties. Check ./output/ for results.\n")
