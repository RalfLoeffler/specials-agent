"""Email newsletter parser for grocery store specials.

This module monitors your email inbox for store newsletters (Coles, Woolworths)
and extracts special offers from the HTML emails.

Setup:
1. Subscribe to store newsletters
2. Configure email credentials in environment variables
3. Run this script to check for new specials

Environment Variables:
    EMAIL_IMAP_SERVER: IMAP server (e.g., imap.gmail.com)
    EMAIL_IMAP_PORT: IMAP port (default: 993)
    EMAIL_USER: Your email address
    EMAIL_PASS: Your email password or app-specific password
"""

import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
import os
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import re


# Email configuration
IMAP_SERVER = os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("EMAIL_IMAP_PORT", "993"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")

# Store email addresses to monitor
STORE_EMAILS = {
    "Coles": ["coles@coles.com.au", "noreply@coles.com.au", "catalogue@coles.com.au"],
    "Woolworths": ["woolworths@woolworths.com.au", "noreply@woolworths.com.au"],
}


def connect_to_email() -> imaplib.IMAP4_SSL:
    """Connect to email server via IMAP.
    
    Returns:
        IMAP connection object
        
    Raises:
        Exception: If connection fails
    """
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail
    except Exception as e:
        raise Exception(f"Failed to connect to email: {e}")


def get_recent_emails(mail: imaplib.IMAP4_SSL, days: int = 7) -> List[Tuple[str, bytes]]:
    """Fetch recent emails from store newsletters.
    
    Args:
        mail: IMAP connection object
        days: Number of days to look back
        
    Returns:
        List of (email_id, email_data) tuples
    """
    mail.select('inbox')
    
    # Calculate date threshold
    date_threshold = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    
    # Build search query for all store emails
    all_emails = []
    for store, addresses in STORE_EMAILS.items():
        for address in addresses:
            try:
                status, messages = mail.search(None, f'(FROM "{address}" SINCE {date_threshold})')
                if status == "OK" and messages[0]:
                    email_ids = messages[0].split()
                    print(f"  Found {len(email_ids)} emails from {store} ({address})")
                    all_emails.extend(email_ids)
            except Exception as e:
                print(f"  Warning: Could not search emails from {address}: {e}")
    
    return all_emails


def decode_email_subject(subject: str) -> str:
    """Decode email subject handling various encodings.
    
    Args:
        subject: Raw subject string
        
    Returns:
        Decoded subject string
    """
    decoded_parts = decode_header(subject)
    subject_parts = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            subject_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
        else:
            subject_parts.append(part)
    return ''.join(subject_parts)


def extract_text_from_html(html_content: str) -> str:
    """Extract readable text from HTML email content.
    
    Args:
        html_content: HTML string
        
    Returns:
        Plain text content
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text
    text = soup.get_text()
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text


def parse_email_for_products(email_message: email.message.Message) -> Dict:
    """Parse email and extract product information.
    
    Args:
        email_message: Email message object
        
    Returns:
        Dictionary with email metadata and products
    """
    # Extract email metadata
    subject = decode_email_subject(email_message.get("Subject", ""))
    from_addr = email_message.get("From", "")
    date = email_message.get("Date", "")
    
    # Determine store from sender
    store = "Unknown"
    for store_name, addresses in STORE_EMAILS.items():
        if any(addr in from_addr.lower() for addr in addresses):
            store = store_name
            break
    
    products = []
    html_content = ""
    
    # Extract email body
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                try:
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    html_content = part.get_payload(decode=True).decode('latin-1', errors='ignore')
                break
    else:
        try:
            html_content = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
        except:
            html_content = email_message.get_payload(decode=True).decode('latin-1', errors='ignore')
    
    # Parse HTML for products
    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Common patterns for product information
        # These patterns may need adjustment based on actual email structure
        
        # Look for price patterns (e.g., $5.99, $10)
        price_pattern = re.compile(r'\$\d+(?:\.\d{2})?')
        
        # Try to find product containers
        product_containers = soup.find_all(['div', 'td', 'p'], class_=re.compile(r'product|item|special|offer', re.I))
        
        for container in product_containers[:50]:  # Limit to first 50
            text = container.get_text(strip=True)
            # Look for text with prices
            if price_pattern.search(text) and len(text) > 10:
                products.append(text)
        
        # Fallback: extract all text and look for price patterns
        if not products:
            full_text = extract_text_from_html(html_content)
            lines = full_text.split('\n')
            for line in lines:
                if price_pattern.search(line) and len(line.strip()) > 10:
                    products.append(line.strip())
    
    return {
        "store": store,
        "subject": subject,
        "from": from_addr,
        "date": date,
        "products": list(set(products[:100])),  # Remove duplicates, limit to 100
        "product_count": len(products)
    }


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


def check_newsletters(watchlist: List[str], days: int = 7, verbose: bool = True) -> Dict[str, List[str]]:
    """Main function to check email newsletters for watchlist items.
    
    Args:
        watchlist: List of product keywords to search for
        days: Number of days to look back
        verbose: Print detailed progress
        
    Returns:
        Dictionary mapping store names to matching products
    """
    if not EMAIL_USER or not EMAIL_PASS:
        print("❌ Email credentials not configured!")
        print("Set EMAIL_USER and EMAIL_PASS environment variables")
        return {}
    
    print(f"\n{'='*60}")
    print(f"Checking email newsletters from last {days} days...")
    print(f"{'='*60}\n")
    
    try:
        # Connect to email
        print("Connecting to email server...")
        mail = connect_to_email()
        print(f"✓ Connected to {IMAP_SERVER}\n")
        
        # Get recent emails
        print("Searching for store newsletters...")
        email_ids = get_recent_emails(mail, days)
        print(f"\nTotal emails found: {len(email_ids)}\n")
        
        if not email_ids:
            print("No store emails found in the specified period.")
            mail.logout()
            return {}
        
        # Process emails
        all_matches = {}
        
        for i, email_id in enumerate(email_ids[:20], 1):  # Process up to 20 most recent
            if verbose:
                print(f"Processing email {i}/{min(len(email_ids), 20)}...")
            
            # Fetch email
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            if status != "OK":
                continue
            
            # Parse email
            email_message = email.message_from_bytes(msg_data[0][1])
            parsed = parse_email_for_products(email_message)
            
            if verbose:
                print(f"  Store: {parsed['store']}")
                print(f"  Subject: {parsed['subject'][:60]}...")
                print(f"  Products found: {parsed['product_count']}")
            
            # Find matches
            matches = find_matches(parsed['products'], watchlist)
            
            if matches:
                store_name = f"{parsed['store']} - {parsed['subject'][:30]}"
                all_matches[store_name] = matches
                if verbose:
                    print(f"  ✓ Found {len(matches)} matching items!")
            
            if verbose:
                print()
        
        # Close connection
        mail.logout()
        
        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}\n")
        
        total_matches = sum(len(items) for items in all_matches.values())
        if total_matches > 0:
            print(f"✓ Found {total_matches} matching products across {len(all_matches)} emails\n")
            for store, items in all_matches.items():
                print(f"{store}:")
                for item in items[:5]:  # Show first 5
                    print(f"  - {item}")
                if len(items) > 5:
                    print(f"  ... and {len(items) - 5} more")
                print()
        else:
            print("No matches found in recent newsletters.")
        
        return all_matches
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}


def main() -> None:
    """Example usage of email newsletter checker."""
    # Example watchlist
    watchlist = [
        "Tim Tams",
        "Nescafe",
        "Coca-Cola",
        "Coffee",
        "Chocolate",
        "Chips"
    ]
    
    print("="*60)
    print("EMAIL NEWSLETTER CHECKER")
    print("="*60)
    print("\nThis tool checks your email for store newsletters")
    print("and finds products matching your watchlist.\n")
    
    print("Configuration:")
    print(f"  Email: {EMAIL_USER or '[NOT SET]'}")
    print(f"  Server: {IMAP_SERVER}")
    print(f"  Watchlist: {', '.join(watchlist)}\n")
    
    if not EMAIL_USER or not EMAIL_PASS:
        print("⚠️  Setup Required:")
        print("  1. Set environment variables:")
        print("     EMAIL_USER=your_email@gmail.com")
        print("     EMAIL_PASS=your_app_password")
        print("  2. Subscribe to store newsletters")
        print("  3. Run this script again\n")
        return
    
    # Check newsletters
    matches = check_newsletters(watchlist, days=7, verbose=True)
    
    print("="*60)
    print("DONE")
    print("="*60)


if __name__ == "__main__":
    main()
