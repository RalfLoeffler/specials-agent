"""Setup script to save browser session with postcode/location preferences.

This script opens a visible browser where you can:
1. Navigate to store websites
2. Enter your postcode/location
3. Accept cookies
4. Close the browser
5. Session is automatically saved for future scraper runs

The saved session includes:
- Cookies
- LocalStorage data
- SessionStorage data
- Postcode/location preferences
"""

from playwright.sync_api import sync_playwright
import time


def setup_session_for_store(name: str, url: str, session_file: str = "browser_session.json") -> None:
    """Open a browser for manual session setup.
    
    Args:
        name: Store name for display
        url: URL to open
        session_file: Path to save session data
    """
    print(f"\n{'='*60}")
    print(f"Setting up session for: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}\n")
    
    print("Instructions:")
    print("1. A browser window will open")
    print("2. Enter your postcode/location when prompted")
    print("3. Accept any cookie notices")
    print("4. Browse to make sure location is set correctly")
    print("5. Close the browser window when done")
    print("6. Session will be saved automatically\n")
    
    input("Press Enter to open browser...")
    
    with sync_playwright() as p:
        # Launch browser in visible mode
        browser = p.chromium.launch(
            headless=False,
            slow_mo=500  # Slow down for easier manual interaction
        )
        
        # Create browser context with realistic settings
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-AU',
            timezone_id='Australia/Sydney',
            geolocation={'latitude': -33.8688, 'longitude': 151.2093},  # Sydney coordinates
            permissions=['geolocation']
        )
        
        page = context.new_page()
        
        # Navigate to the store
        print(f"\nOpening {url}...")
        page.goto(url, timeout=60000)
        
        print("\n" + "="*60)
        print("BROWSER IS OPEN")
        print("="*60)
        print("Take your time to:")
        print("  • Enter your postcode/suburb")
        print("  • Accept cookies")
        print("  • Verify your location is set correctly")
        print("  • Browse a few pages if needed")
        print("\nWhen you're done, just CLOSE the browser window.")
        print("="*60 + "\n")
        
        # Wait for user to close the browser
        try:
            page.wait_for_timeout(300000)  # Wait up to 5 minutes
        except:
            pass  # Browser was closed by user
        
        # Save the session state
        print("\nSaving session...")
        try:
            context.storage_state(path=session_file)
            print(f"✓ Session saved to: {session_file}")
            print("  This includes cookies, postcode, and location preferences")
            print("  Your scraper will now use this session automatically!")
        except Exception as e:
            print(f"✗ Error saving session: {e}")
        finally:
            browser.close()


def main() -> None:
    """Setup sessions for all configured stores."""
    print("="*60)
    print("BROWSER SESSION SETUP")
    print("="*60)
    print("\nThis tool helps you save your location/postcode preferences")
    print("so the scraper can access location-specific catalogues.\n")
    
    stores = [
        ("Coles", "https://www.coles.com.au/catalogues-and-specials"),
        ("Woolworths", "https://www.woolworths.com.au/shop/catalogue"),
    ]
    
    print("Which store would you like to setup?")
    for i, (name, _) in enumerate(stores, 1):
        print(f"  {i}. {name}")
    print("  3. Both stores")
    print("  4. Custom URL")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    session_file = "browser_session.json"
    
    if choice == "1":
        setup_session_for_store(stores[0][0], stores[0][1], session_file)
    elif choice == "2":
        setup_session_for_store(stores[1][0], stores[1][1], session_file)
    elif choice == "3":
        for name, url in stores:
            setup_session_for_store(name, url, session_file)
            if name != stores[-1][0]:  # Not the last one
                cont = input("\nContinue to next store? (y/n): ")
                if cont.lower() != 'y':
                    break
    elif choice == "4":
        url = input("Enter URL: ").strip()
        name = input("Enter store name: ").strip()
        setup_session_for_store(name, url, session_file)
    else:
        print("Invalid choice")
        return
    
    print("\n" + "="*60)
    print("SETUP COMPLETE!")
    print("="*60)
    print(f"\nSession file: {session_file}")
    print("\nYour scraper will now automatically:")
    print("  ✓ Use your saved postcode/location")
    print("  ✓ Skip cookie acceptance prompts")
    print("  ✓ Access location-specific catalogues")
    print("\nYou can run your scraper now:")
    print("  python -m src.main --scrape-test")
    print("\nTo update your location, run this script again.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
