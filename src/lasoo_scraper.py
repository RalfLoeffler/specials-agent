"""Lasoo catalogue scraper for Australian grocery stores.

Lasoo (lasoo.com.au) is a catalogue aggregator that includes Coles and Woolworths.
It's more scraping-friendly than the store websites directly.

This module provides an alternative data source for grocery specials that:
- Doesn't require postcode/cookie management
- Has simpler HTML structure
- Is designed for public catalogue viewing
- May have fewer anti-bot protections

Note: Always respect Lasoo's terms of service and robots.txt
"""

from playwright.sync_api import sync_playwright
from typing import List, Dict
import time


def fetch_lasoo_catalogues(store_name: str, postcode: str = "2000") -> List[Dict]:
    """Fetch available catalogues for a store from Lasoo.
    
    Args:
        store_name: Store name (e.g., "coles", "woolworths")
        postcode: Australian postcode for location-specific catalogues
        
    Returns:
        List of catalogue dictionaries with titles and URLs
    """
    catalogues = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Lasoo search URL
        url = f"https://www.lasoo.com.au/{store_name}-catalogues"
        
        try:
            print(f"Loading Lasoo page for {store_name}...")
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # Look for catalogue cards/links
            # Note: Selectors may need adjustment based on actual Lasoo structure
            catalogue_links = page.query_selector_all("a[href*='catalogue']")
            
            for link in catalogue_links[:10]:  # Limit to 10 most recent
                try:
                    title = link.inner_text().strip()
                    href = link.get_attribute("href")
                    
                    if title and href and len(title) > 5:
                        full_url = href if href.startswith("http") else f"https://www.lasoo.com.au{href}"
                        catalogues.append({
                            "title": title,
                            "url": full_url,
                            "store": store_name
                        })
                except:
                    continue
            
            print(f"  Found {len(catalogues)} catalogues")
            
        except Exception as e:
            print(f"  Error loading Lasoo: {e}")
        finally:
            browser.close()
    
    return catalogues


def scrape_lasoo_catalogue(catalogue_url: str, store_name: str) -> List[str]:
    """Scrape product items from a Lasoo catalogue page.
    
    Args:
        catalogue_url: URL of the catalogue on Lasoo
        store_name: Store name for context
        
    Returns:
        List of product text strings
    """
    products = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print(f"  Loading catalogue: {catalogue_url[:60]}...")
            page.goto(catalogue_url, timeout=45000)
            
            # Wait for content to load
            page.wait_for_load_state("networkidle", timeout=20000)
            
            # Give extra time for dynamic content
            time.sleep(3)
            
            # Try multiple selector strategies for Lasoo
            selectors_to_try = [
                "div[class*='product']",
                "div[class*='item']",
                "div[class*='offer']",
                "div[class*='special']",
                "article",
                "div[class*='tile']",
                ".product-card",
                ".catalogue-item",
            ]
            
            for selector in selectors_to_try:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 5:
                    print(f"    Using selector: {selector} ({len(elements)} items)")
                    for el in elements:
                        try:
                            text = el.inner_text().strip()
                            if text and len(text) > 5:
                                products.append(text)
                        except:
                            continue
                    break
            
            # Remove duplicates while preserving order
            seen = set()
            unique_products = []
            for p in products:
                if p not in seen:
                    seen.add(p)
                    unique_products.append(p)
            
            print(f"    Scraped {len(unique_products)} products")
            return unique_products[:200]  # Limit to 200 items
            
        except Exception as e:
            print(f"    Error scraping catalogue: {e}")
            return []
        finally:
            browser.close()


def find_matches(products: List[str], watchlist: List[str]) -> List[str]:
    """Find products matching the watchlist.
    
    Args:
        products: List of product strings
        watchlist: List of keywords to match
        
    Returns:
        List of matching products
    """
    matches = []
    for product in products:
        lower_product = product.lower()
        for term in watchlist:
            if term.lower() in lower_product:
                matches.append(product)
                break
    return matches


def scrape_lasoo_stores(stores: List[str], watchlist: List[str], postcode: str = "2000") -> Dict[str, List[str]]:
    """Main function to scrape multiple stores from Lasoo.
    
    Args:
        stores: List of store names (e.g., ["coles", "woolworths"])
        watchlist: List of product keywords to search for
        postcode: Australian postcode
        
    Returns:
        Dictionary mapping store names to matching products
    """
    print(f"\n{'='*60}")
    print("LASOO CATALOGUE SCRAPER")
    print(f"{'='*60}\n")
    print(f"Stores: {', '.join(stores)}")
    print(f"Postcode: {postcode}")
    print(f"Watchlist: {', '.join(watchlist)}\n")
    
    all_matches = {}
    
    for store in stores:
        print(f"\n{'─'*60}")
        print(f"Processing: {store.upper()}")
        print(f"{'─'*60}")
        
        # Get available catalogues
        catalogues = fetch_lasoo_catalogues(store, postcode)
        
        if not catalogues:
            print(f"  No catalogues found for {store}")
            continue
        
        # Process each catalogue (usually just need the latest)
        for i, catalogue in enumerate(catalogues[:2], 1):  # Process top 2 catalogues
            print(f"\n  Catalogue {i}: {catalogue['title']}")
            
            # Scrape products from this catalogue
            products = scrape_lasoo_catalogue(catalogue['url'], store)
            
            if not products:
                print(f"    No products found")
                continue
            
            # Find matches
            matches = find_matches(products, watchlist)
            
            if matches:
                store_key = f"{store.title()} - {catalogue['title']}"
                all_matches[store_key] = matches
                print(f"    ✓ Found {len(matches)} matching items!")
            else:
                print(f"    No matches in watchlist")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")
    
    total_matches = sum(len(items) for items in all_matches.values())
    if total_matches > 0:
        print(f"✓ Found {total_matches} matching products across {len(all_matches)} catalogues\n")
        for store, items in all_matches.items():
            print(f"{store}:")
            for item in items[:10]:  # Show first 10
                print(f"  - {item}")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")
            print()
    else:
        print("No matches found in catalogues.")
    
    return all_matches


def main() -> None:
    """Example usage of Lasoo scraper."""
    # Configuration
    stores = ["coles", "woolworths"]
    watchlist = [
        "Tim Tams",
        "Nescafe",
        "Coca-Cola",
        "Coffee",
        "Chocolate",
        "Chips",
        "Milk",
        "Bread"
    ]
    postcode = "2000"  # Sydney CBD
    
    # Run scraper
    matches = scrape_lasoo_stores(stores, watchlist, postcode)
    
    print("="*60)
    print("DONE")
    print("="*60)
    print("\nNote: Lasoo structure may change. Update selectors as needed.")
    print("Check their robots.txt and terms of service before production use.")


if __name__ == "__main__":
    main()
