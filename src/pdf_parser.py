"""PDF catalogue parser for grocery store specials.

This module extracts product information from PDF catalogues published by stores.
Many stores publish weekly catalogues as PDFs which are easier to parse than
dynamic websites.

Features:
- Extract text from PDF catalogues
- Identify products and prices
- Match against watchlist
- Save extracted data for analysis

PDF Sources:
- Coles: Check their website for PDF catalogue downloads
- Woolworths: Similar PDF availability
- Direct download URLs if available

Setup:
    pip install pypdf2 pdfplumber

Usage:
    python -m src.pdf_parser /path/to/catalogue.pdf
"""

import os
import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import urllib.request
from datetime import datetime

# Try to import PDF libraries
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("Warning: pdfplumber not installed. Install with: pip install pdfplumber")

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("Warning: PyPDF2 not installed. Install with: pip install pypdf2")


class CataloguePDF:
    """Class to handle PDF catalogue parsing."""
    
    def __init__(self, pdf_path: str):
        """Initialize with path to PDF file.
        
        Args:
            pdf_path: Path to PDF file
        """
        self.pdf_path = pdf_path
        self.text_content = ""
        self.products = []
        
    def extract_text_pdfplumber(self) -> str:
        """Extract text using pdfplumber (preferred method).
        
        Returns:
            Extracted text from all pages
        """
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError("pdfplumber not installed")
        
        text = []
        print(f"Extracting text from PDF using pdfplumber...")
        
        with pdfplumber.open(self.pdf_path) as pdf:
            print(f"  Total pages: {len(pdf.pages)}")
            
            for i, page in enumerate(pdf.pages, 1):
                print(f"  Processing page {i}/{len(pdf.pages)}...", end="\r")
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
        
        print(f"\n  ✓ Extracted text from {len(pdf.pages)} pages")
        return "\n\n".join(text)
    
    def extract_text_pypdf2(self) -> str:
        """Extract text using PyPDF2 (fallback method).
        
        Returns:
            Extracted text from all pages
        """
        if not PYPDF2_AVAILABLE:
            raise ImportError("PyPDF2 not installed")
        
        text = []
        print(f"Extracting text from PDF using PyPDF2...")
        
        reader = PdfReader(self.pdf_path)
        print(f"  Total pages: {len(reader.pages)}")
        
        for i, page in enumerate(reader.pages, 1):
            print(f"  Processing page {i}/{len(reader.pages)}...", end="\r")
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        
        print(f"\n  ✓ Extracted text from {len(reader.pages)} pages")
        return "\n\n".join(text)
    
    def extract_text(self) -> str:
        """Extract text using best available method.
        
        Returns:
            Extracted text from PDF
        """
        # Try pdfplumber first (better extraction)
        if PDFPLUMBER_AVAILABLE:
            self.text_content = self.extract_text_pdfplumber()
        elif PYPDF2_AVAILABLE:
            self.text_content = self.extract_text_pypdf2()
        else:
            raise ImportError("No PDF library available. Install pdfplumber or pypdf2")
        
        return self.text_content
    
    def parse_products(self) -> List[Dict]:
        """Parse extracted text to identify products and prices.
        
        Returns:
            List of product dictionaries with name and price
        """
        if not self.text_content:
            self.extract_text()
        
        products = []
        
        # Price patterns to match
        price_pattern = re.compile(r'\$\s*(\d+)\.(\d{2})')
        save_pattern = re.compile(r'[Ss]ave\s+\$\s*(\d+\.?\d*)')
        percentage_pattern = re.compile(r'(\d+)%\s+[Oo]ff')
        
        # Split into lines and process
        lines = self.text_content.split('\n')
        
        current_product = {}
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Look for price in the line
            price_match = price_pattern.search(line)
            
            if price_match:
                # This line likely contains a product with price
                price = f"${price_match.group(1)}.{price_match.group(2)}"
                
                # Extract product name (text before price)
                product_name = price_pattern.sub('', line).strip()
                
                # Clean up common catalogue formatting
                product_name = re.sub(r'\s+', ' ', product_name)
                product_name = product_name.strip('•-*→')
                
                if product_name and len(product_name) > 3:
                    product_dict = {
                        'name': product_name,
                        'price': price,
                        'text': line
                    }
                    
                    # Look for save/discount info
                    save_match = save_pattern.search(line)
                    if save_match:
                        product_dict['save'] = f"${save_match.group(1)}"
                    
                    percent_match = percentage_pattern.search(line)
                    if percent_match:
                        product_dict['discount'] = f"{percent_match.group(1)}%"
                    
                    products.append(product_dict)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_products = []
        for p in products:
            key = (p['name'].lower(), p['price'])
            if key not in seen:
                seen.add(key)
                unique_products.append(p)
        
        self.products = unique_products
        print(f"  ✓ Found {len(self.products)} products with prices")
        
        return self.products
    
    def find_matches(self, watchlist: List[str]) -> List[Dict]:
        """Find products matching the watchlist.
        
        Args:
            watchlist: List of keywords to search for
            
        Returns:
            List of matching product dictionaries
        """
        if not self.products:
            self.parse_products()
        
        matches = []
        
        for product in self.products:
            product_text = f"{product['name']} {product.get('text', '')}".lower()
            
            for term in watchlist:
                if term.lower() in product_text:
                    matches.append(product)
                    break  # Don't add same product twice
        
        return matches


def download_pdf(url: str, save_path: str) -> bool:
    """Download a PDF catalogue from URL.
    
    Args:
        url: URL of the PDF file
        save_path: Path to save the downloaded PDF
        
    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"Downloading PDF from {url}...")
        urllib.request.urlretrieve(url, save_path)
        print(f"  ✓ Saved to {save_path}")
        return True
    except Exception as e:
        print(f"  ✗ Error downloading PDF: {e}")
        return False


def parse_catalogue_pdf(pdf_path: str, watchlist: List[str], verbose: bool = True) -> Dict[str, List[Dict]]:
    """Main function to parse PDF catalogue and find matches.
    
    Args:
        pdf_path: Path to PDF file
        watchlist: List of product keywords to search for
        verbose: Print detailed progress
        
    Returns:
        Dictionary with parsing results and matches
    """
    if verbose:
        print(f"\n{'='*60}")
        print("PDF CATALOGUE PARSER")
        print(f"{'='*60}\n")
        print(f"File: {pdf_path}")
        print(f"Watchlist: {', '.join(watchlist)}\n")
    
    # Check if file exists
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        return {}
    
    try:
        # Parse PDF
        catalogue = CataloguePDF(pdf_path)
        
        # Extract and parse
        catalogue.extract_text()
        catalogue.parse_products()
        
        # Find matches
        matches = catalogue.find_matches(watchlist)
        
        # Results
        if verbose:
            print(f"\n{'='*60}")
            print("RESULTS")
            print(f"{'='*60}\n")
            print(f"Total products found: {len(catalogue.products)}")
            print(f"Watchlist matches: {len(matches)}\n")
            
            if matches:
                for i, match in enumerate(matches, 1):
                    print(f"{i}. {match['name']}")
                    print(f"   Price: {match['price']}", end="")
                    if 'save' in match:
                        print(f" (Save {match['save']})", end="")
                    if 'discount' in match:
                        print(f" ({match['discount']} off)", end="")
                    print()
                print()
        
        filename = Path(pdf_path).stem
        return {
            filename: matches
        }
        
    except Exception as e:
        print(f"❌ Error parsing PDF: {e}")
        import traceback
        traceback.print_exc()
        return {}


def batch_parse_catalogues(pdf_directory: str, watchlist: List[str]) -> Dict[str, List[Dict]]:
    """Parse multiple PDF catalogues in a directory.
    
    Args:
        pdf_directory: Directory containing PDF catalogues
        watchlist: List of product keywords to search for
        
    Returns:
        Dictionary mapping filenames to matching products
    """
    print(f"\n{'='*60}")
    print("BATCH PDF CATALOGUE PARSER")
    print(f"{'='*60}\n")
    print(f"Directory: {pdf_directory}")
    print(f"Watchlist: {', '.join(watchlist)}\n")
    
    if not os.path.exists(pdf_directory):
        print(f"❌ Directory not found: {pdf_directory}")
        return {}
    
    # Find all PDF files
    pdf_files = list(Path(pdf_directory).glob("*.pdf"))
    
    if not pdf_files:
        print("No PDF files found in directory")
        return {}
    
    print(f"Found {len(pdf_files)} PDF files\n")
    
    all_matches = {}
    
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n{'─'*60}")
        print(f"Processing {i}/{len(pdf_files)}: {pdf_file.name}")
        print(f"{'─'*60}")
        
        results = parse_catalogue_pdf(str(pdf_file), watchlist, verbose=False)
        
        if results:
            all_matches.update(results)
            matches = list(results.values())[0]
            print(f"  ✓ Found {len(matches)} matching items")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")
    
    total_matches = sum(len(items) for items in all_matches.values())
    print(f"Processed {len(pdf_files)} catalogues")
    print(f"Total matches: {total_matches}\n")
    
    for filename, matches in all_matches.items():
        if matches:
            print(f"{filename}:")
            for match in matches[:5]:  # Show first 5
                print(f"  - {match['name']} @ {match['price']}")
            if len(matches) > 5:
                print(f"  ... and {len(matches) - 5} more")
            print()
    
    return all_matches


def save_results_to_log(results: Dict[str, List[Dict]], log_file: str = "pdf_results.log") -> None:
    """Save parsing results to a log file.
    
    Args:
        results: Dictionary of parsing results
        log_file: Path to log file
    """
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n{'='*60}\n")
            f.write(f"PDF Parsing Results - {timestamp}\n")
            f.write(f"{'='*60}\n\n")
            
            for catalogue, matches in results.items():
                f.write(f"{catalogue}:\n")
                for match in matches:
                    f.write(f"  - {match['name']} @ {match['price']}\n")
                f.write("\n")
        
        print(f"✓ Results saved to {log_file}")
    except Exception as e:
        print(f"Warning: Could not save results to log: {e}")


def main() -> None:
    """Example usage of PDF parser."""
    import sys
    
    print("="*60)
    print("PDF CATALOGUE PARSER")
    print("="*60)
    print("\nThis tool extracts products from PDF catalogues.")
    print("Works with Coles, Woolworths, and other store PDFs.\n")
    
    # Check if PDF libraries are available
    if not PDFPLUMBER_AVAILABLE and not PYPDF2_AVAILABLE:
        print("❌ No PDF library installed!")
        print("\nInstall one of these:")
        print("  pip install pdfplumber  (recommended)")
        print("  pip install pypdf2       (alternative)")
        return
    
    # Example watchlist
    watchlist = [
        "Tim Tams",
        "Nescafe",
        "Coca-Cola",
        "Coffee",
        "Chocolate",
        "Milk",
        "Bread"
    ]
    
    # Check command line arguments
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        
        if os.path.isdir(pdf_path):
            # Batch process directory
            results = batch_parse_catalogues(pdf_path, watchlist)
        else:
            # Process single file
            results = parse_catalogue_pdf(pdf_path, watchlist)
        
        if results:
            save_results_to_log(results)
    else:
        print("Usage:")
        print("  Single file:  python -m src.pdf_parser catalogue.pdf")
        print("  Directory:    python -m src.pdf_parser ./catalogues/")
        print("\nExample:")
        print("  1. Download a catalogue PDF from store website")
        print("  2. Save to project folder (e.g., coles_catalogue.pdf)")
        print("  3. Run: python -m src.pdf_parser coles_catalogue.pdf")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
