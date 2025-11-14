"""Helper script to inspect website structure and find correct selectors.

This script opens the store websites in a visible browser and takes screenshots
to help identify the correct CSS selectors for scraping.
"""

from playwright.sync_api import sync_playwright
import time


def inspect_website(name: str, url: str) -> None:
    """Open a website and help identify selectors.
    
    Args:
        name: Store name
        url: URL to inspect
    """
    print(f"\n{'='*60}")
    print(f"Inspecting: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}\n")
    
    with sync_playwright() as p:
        # Launch browser in headed mode (visible)
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("Loading page...")
        try:
            page.goto(url, timeout=60000)
            print("✓ Page loaded successfully")
            
            # Wait for page to settle
            page.wait_for_load_state("networkidle", timeout=30000)
            print("✓ Network idle")
            
            # Take a screenshot
            screenshot_name = f"{name.lower().replace(' ', '_')}_screenshot.png"
            page.screenshot(path=screenshot_name, full_page=True)
            print(f"✓ Screenshot saved: {screenshot_name}")
            
            # Try to find common product selectors
            print("\nSearching for common selectors...")
            common_selectors = [
                "div.product",
                "div[class*='product']",
                "article.product",
                "article[class*='product']",
                "div.item",
                "div[class*='item']",
                "div[class*='tile']",
                "div[class*='card']",
                "li[class*='product']",
                "a[class*='product']",
            ]
            
            for selector in common_selectors:
                elements = page.query_selector_all(selector)
                if elements and len(elements) > 5:
                    print(f"  ✓ Found {len(elements)} elements with: {selector}")
                    # Get sample text from first element
                    try:
                        sample_text = elements[0].inner_text()[:100]
                        print(f"    Sample: {sample_text}...")
                    except:
                        pass
            
            # Get page title
            title = page.title()
            print(f"\nPage title: {title}")
            
            # Check for common class names
            print("\nLooking for product-related classes...")
            all_classes = page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('*');
                    const classes = new Set();
                    elements.forEach(el => {
                        el.classList.forEach(cls => {
                            if (cls.toLowerCase().includes('product') || 
                                cls.toLowerCase().includes('item') ||
                                cls.toLowerCase().includes('tile') ||
                                cls.toLowerCase().includes('card') ||
                                cls.toLowerCase().includes('special')) {
                                classes.add(cls);
                            }
                        });
                    });
                    return Array.from(classes).slice(0, 20);
                }
            """)
            
            if all_classes:
                print("  Relevant classes found:")
                for cls in all_classes[:10]:
                    print(f"    - {cls}")
            
            print(f"\n{'='*60}")
            print("Browser will stay open for 30 seconds for manual inspection.")
            print("You can use browser DevTools (F12) to inspect elements.")
            print(f"{'='*60}\n")
            
            # Keep browser open for inspection
            time.sleep(30)
            
        except Exception as e:
            print(f"✗ Error: {e}")
        finally:
            browser.close()


def main() -> None:
    """Inspect both store websites."""
    stores = [
        ("Coles Catalogues", "https://www.coles.com.au/catalogues-and-specials"),
        ("Woolworths Catalogue", "https://www.woolworths.com.au/shop/catalogue"),
    ]
    
    print("="*60)
    print("WEBSITE INSPECTOR - Finding Correct Selectors")
    print("="*60)
    print("\nThis tool will:")
    print("1. Open each website in a visible browser")
    print("2. Take full-page screenshots")
    print("3. Search for common product selectors")
    print("4. Keep browser open for 30 seconds for manual inspection")
    print("\nPress Ctrl+C to skip to the next website.")
    print("="*60)
    
    input("\nPress Enter to start inspection...")
    
    for name, url in stores:
        try:
            inspect_website(name, url)
        except KeyboardInterrupt:
            print("\n\nSkipping to next website...")
            continue
    
    print("\n" + "="*60)
    print("INSPECTION COMPLETE")
    print("="*60)
    print("\nNext steps:")
    print("1. Review the screenshots saved in this directory")
    print("2. Use the suggested selectors found above")
    print("3. Update the STORES configuration in src/main.py")
    print("4. Run: python -m src.main --scrape-test")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
