"""Main module for specials-agent.

This module scrapes Australian grocery store websites (Coles and Woolworths)
for current specials and alerts the user via email when items on their watchlist
go on sale.
"""

from playwright.sync_api import sync_playwright
import os
import sys
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

# -----------------------------
# CONFIGURATION
# -----------------------------

# Scrape test mode: Set to True to test scraping without sending emails
# Can also be enabled via command line: python -m src.main --scrape-test
# Outputs all scraped data to console and optionally to a log file
SCRAPE_TEST_MODE = os.getenv("SALE_ALERT_SCRAPE_TEST", "").lower() in ("true", "1", "yes")

# Log file path for scrape test output (None = console only)
SCRAPE_TEST_LOG = os.getenv("SALE_ALERT_SCRAPE_TEST_LOG", "scrape_test.log")

# List of product names to monitor for sales/specials
# Case-insensitive matching is used, so "Tim Tams" will match "TIM TAMS" or "tim tams"
WATCHLIST = [
    "Tim Tams",
    "Nescafe",
    "Coca-Cola",
    "Laundry detergent"
]

# Email configuration - loaded from environment variables for security
# Set these in your .env file or system environment:
#   SALE_ALERT_SMTP_SERVER: SMTP server address (default: smtp.gmail.com)
#   SALE_ALERT_SMTP_PORT: SMTP port (default: 587 for TLS)
#   SALE_ALERT_EMAIL_USER: Your email address (sender)
#   SALE_ALERT_EMAIL_PASS: Your email password or app-specific password
#   SALE_ALERT_EMAIL_TO: Recipient email address (can be same as sender)
SMTP_SERVER = os.getenv("SALE_ALERT_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SALE_ALERT_SMTP_PORT", "587"))
EMAIL_USER = os.getenv("SALE_ALERT_EMAIL_USER", "")
EMAIL_PASS = os.getenv("SALE_ALERT_EMAIL_PASS", "")
EMAIL_TO = os.getenv("SALE_ALERT_EMAIL_TO", "")

# Store configuration - each store has a name, URL, and CSS selector
# NOTE: Selectors may need updating if the websites change their structure
STORES = [
    {
        "name": "Coles",
        "url": "https://www.coles.com.au/catalogues-and-specials",
        "product_selector": "div.product-tile, article[class*=product]"
    },
    {
        "name": "Woolworths",
        "url": "https://www.woolworths.com.au/shop/catalogue",
        "product_selector": "div.product-tile, article[class*=product]"
    }
]

# -----------------------------
# FUNCTIONS
# -----------------------------

def _append_to_log(log_file: str, message: str) -> None:
    """Append a message to the log file with timestamp.
    
    Args:
        log_file: Path to the log file
        message: Message to append
    """
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n[{timestamp}]\n{message}\n")
    except Exception as e:
        print(f"Warning: Could not write to log file {log_file}: {e}")


def fetch_items(url: str, product_selector: str) -> list[str]:
    """Scrape product listings from a store's website.
    
    Args:
        url: The URL of the store's catalogue/specials page
        product_selector: CSS selector to find product elements on the page
        
    Returns:
        A list of product text strings found on the page
        
    Note:
        Uses Playwright in headless mode to handle JavaScript-rendered content.
        Includes fallback scrolling mechanism for lazy-loaded content.
    """
    with sync_playwright() as p:
        # Launch browser in headless mode (no visible window)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Navigate to the store's specials page with 60 second timeout
        page.goto(url, timeout=60000)
        
        # Wait until network is idle (all resources loaded)
        page.wait_for_load_state("networkidle")
        
        try:
            # Wait for product elements to appear (15 second timeout)
            page.wait_for_selector(product_selector, timeout=15000)
        except Exception:
            # Fallback: If selector doesn't appear immediately, try scrolling
            # This helps load lazy-loaded content that appears on scroll
            for _ in range(5):
                # Scroll to the bottom of the page
                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                # Wait 1 second for content to load
                page.wait_for_timeout(1000)
        
        # Find all product elements matching the selector
        elements = page.query_selector_all(product_selector)
        items = []
        
        # Extract text from each product element
        for el in elements:
            txt = (el.inner_text() or "").strip()
            if txt:  # Only add non-empty text
                items.append(txt)
        
        # Clean up: close the browser
        browser.close()
        return items

def find_matches(items: list[str], watchlist: list[str]) -> list[str]:
    """Filter items to find those matching the watchlist.
    
    Args:
        items: List of product text strings scraped from a store
        watchlist: List of keywords to search for (case-insensitive)
        
    Returns:
        List of items that contain at least one watchlist keyword
        
    Note:
        Uses case-insensitive substring matching. Each item is added only once
        even if it matches multiple watchlist terms.
    """
    matches = []
    for item in items:
        # Convert to lowercase for case-insensitive matching
        lower_item = item.lower()
        
        # Check if any watchlist term appears in this item
        for term in watchlist:
            if term.lower() in lower_item:
                matches.append(item)
                break  # Don't add the same item twice
    return matches

def send_email_alert(store_matches: dict[str, list[str]], scrape_test: bool = False, log_file: str = None) -> None:
    """Send an email alert with all found matches.
    
    Args:
        store_matches: Dictionary mapping store names to lists of matching items
        scrape_test: If True, only prints email content without sending
        log_file: Optional path to log file for scrape test output
        
    Note:
        Only sends email if at least one match is found across all stores.
        Uses SMTP with TLS encryption for secure email transmission.
        Requires EMAIL_USER and EMAIL_PASS to be configured in environment.
        In scrape test mode, the email body is printed to console and/or log file.
    """
    # Count total matches across all stores
    total = sum(len(v) for v in store_matches.values())
    
    # Skip sending email if nothing was found
    if total == 0:
        msg = "No matches found; no email sent."
        print(msg)
        if scrape_test and log_file:
            _append_to_log(log_file, msg)
        return

    # Build email body with formatted results
    lines = []
    for store, items in store_matches.items():
        if items:
            lines.append(f"{store}:")
            for i in items:
                lines.append(f"  - {i}")
    body = "\n".join(lines)

    # Scrape test mode: print email content instead of sending
    if scrape_test:
        output = [
            "\n" + "="*60,
            "SCRAPE TEST MODE - Email Preview:",
            "="*60,
            f"Subject: Coles/Woolworths Sale Alert",
            f"From: {EMAIL_USER}",
            f"To: {EMAIL_TO}",
            "",
            body,
            "="*60,
            f"[SCRAPE TEST] Would have sent email with {total} match(es).",
            ""
        ]
        output_text = "\n".join(output)
        print(output_text)
        
        if log_file:
            _append_to_log(log_file, output_text)
        return

    # Create email message
    msg = MIMEText(body)
    msg["Subject"] = "Coles/Woolworths Sale Alert"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    # Send email via SMTP with TLS encryption
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()  # Upgrade connection to secure TLS
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())

    print(f"Sent email with {total} match(es).")

def main() -> None:
    """Main entry point - orchestrates the scraping and alerting process.
    
    Process:
        1. Check for scrape test mode flag
        2. Iterate through all configured stores
        3. Scrape each store's specials page for products
        4. Filter products against the watchlist
        5. Send a consolidated email alert with all matches (or output to console/log in test mode)
        
    Usage:
        Normal mode:     python -m src.main
        Scrape test:     python -m src.main --scrape-test
        With env var:    SALE_ALERT_SCRAPE_TEST=true python -m src.main
        Custom log file: SALE_ALERT_SCRAPE_TEST_LOG=my_test.log python -m src.main --scrape-test
        Or import and call: from src.main import main; main()
    """
    # Check for scrape test mode from command line args or environment variable
    scrape_test_mode = SCRAPE_TEST_MODE or "--scrape-test" in sys.argv
    log_file = SCRAPE_TEST_LOG if scrape_test_mode else None
    
    if scrape_test_mode:
        print("\n" + "!"*60)
        print("SCRAPE TEST MODE ENABLED - No emails will be sent")
        if log_file:
            print(f"Output will be logged to: {log_file}")
        print("!"*60 + "\n")
        _append_to_log(log_file, "=== SCRAPE TEST SESSION STARTED ===")
    
    results = {}
    
    # Scrape each store and check for watchlist matches
    for store in STORES:
        store_name = store['name']
        print(f"Fetching: {store_name} ...")
        
        if scrape_test_mode and log_file:
            _append_to_log(log_file, f"--- Fetching: {store_name} ---")
        
        # Get all product items from the store's page
        items = fetch_items(store["url"], store["product_selector"])
        
        # In scrape test mode, log all scraped items (not just matches)
        if scrape_test_mode:
            scrape_info = f"\nTotal items scraped from {store_name}: {len(items)}"
            print(scrape_info)
            if log_file:
                _append_to_log(log_file, scrape_info)
                if items:
                    _append_to_log(log_file, "All scraped items:")
                    for idx, item in enumerate(items[:50], 1):  # Log first 50 items
                        _append_to_log(log_file, f"  {idx}. {item}")
                    if len(items) > 50:
                        _append_to_log(log_file, f"  ... and {len(items) - 50} more items")
        
        # Filter to only items on the watchlist
        matches = find_matches(items, WATCHLIST)
        
        # Store results for this store
        results[store_name] = matches
        match_info = f"Found {len(matches)} matches for {store_name}."
        print(match_info)
        
        if scrape_test_mode and log_file:
            _append_to_log(log_file, match_info)
            if matches:
                _append_to_log(log_file, "Matched items:")
                for match in matches:
                    _append_to_log(log_file, f"  - {match}")

    # Send email alert with all results (or output to console/log in scrape test mode)
    send_email_alert(results, scrape_test=scrape_test_mode, log_file=log_file)
    
    if scrape_test_mode and log_file:
        _append_to_log(log_file, "=== SCRAPE TEST SESSION COMPLETED ===")
    
    print("Done.")

# Entry point when run as a script
if __name__ == "__main__":
    main()
