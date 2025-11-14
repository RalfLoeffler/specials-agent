"""Demo configuration using a test e-commerce website.

This configuration uses a website specifically designed for web scraping practice,
so you can test the specials-agent functionality without anti-bot issues.

To use this configuration:
1. Copy this file content
2. Replace the STORES configuration in src/main.py
3. Update WATCHLIST to match products on the test site
4. Run: python -m src.main --scrape-test
"""

# Example watchlist for the test site
WATCHLIST_TEST = [
    "phone",
    "laptop",
    "tablet",
    "watch",
    "camera"
]

# Working test configuration
STORES_TEST = [
    {
        "name": "Test E-commerce Site",
        "url": "https://webscraper.io/test-sites/e-commerce/allinone",
        "product_selector": ".thumbnail"  # This selector works on the test site
    }
]

# Another test option - quotes website
STORES_QUOTES_TEST = [
    {
        "name": "Quotes Test Site",
        "url": "http://quotes.toscrape.com/",
        "product_selector": ".quote"
    }
]

# Simple example.com test (just to verify Playwright works)
STORES_SIMPLE_TEST = [
    {
        "name": "Example Domain",
        "url": "https://example.com",
        "product_selector": "h1, p"
    }
]

print("""
To use these test configurations:

1. Simple test (verify Playwright works):
   - Use STORES_SIMPLE_TEST
   - Update WATCHLIST = ["Example", "domain", "illustrative"]

2. E-commerce test (realistic product scraping):
   - Use STORES_TEST
   - Update WATCHLIST = ["phone", "laptop", "tablet"]

3. Quotes test (text content scraping):
   - Use STORES_QUOTES_TEST
   - Update WATCHLIST = ["love", "life", "inspirational"]

Replace the STORES and WATCHLIST in src/main.py and run:
    python -m src.main --scrape-test
""")
