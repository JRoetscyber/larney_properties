"""
Property24 page scraper using Playwright (real browser).
Usage:
    python scraper.py <url>
    python scraper.py https://www.property24.com/for-sale/nigel-ext-2/nigel/gauteng/33470/117059303

Saves the rendered HTML to scraped_listing.html for analysis.
Requires:
    pip install playwright
    playwright install chromium
"""

import sys
import time
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://www.property24.com/for-sale/nigel-ext-2/nigel/gauteng/33470/117059303"
)

OUTPUT = "scraped_listing.html"

print(f"Fetching: {URL}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()

    page.goto(URL, wait_until="networkidle", timeout=30000)

    # Wait a moment for any lazy-loaded content
    time.sleep(3)

    html = page.content()
    browser.close()

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Done. Saved {len(html):,} characters to {OUTPUT}")
