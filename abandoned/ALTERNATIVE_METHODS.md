# Alternative Scraping Methods Guide

This document explains how to use the email parser and Lasoo scraper as alternatives to direct website scraping.

## 📧 Method 1: Email Newsletter Parsing

### Overview
Monitor your email inbox for store newsletters and extract specials automatically.

### Advantages
- ✅ **Legal & Official** - Content is sent directly by stores
- ✅ **No bot detection** - Not web scraping
- ✅ **Reliable** - Weekly delivery
- ✅ **Rich content** - Usually includes best deals
- ✅ **No rate limiting** - Read your own emails

### Setup

#### Step 1: Subscribe to Newsletters

**Coles:**
1. Visit https://www.coles.com.au/
2. Scroll to footer
3. Click "Email Sign Up"
4. Enter your email and postcode

**Woolworths:**
1. Visit https://www.woolworths.com.au/
2. Find "Subscribe" in footer
3. Sign up for weekly emails

#### Step 2: Configure Email Access

Set environment variables:

```bash
# Windows PowerShell
$env:EMAIL_USER="your_email@gmail.com"
$env:EMAIL_PASS="your_app_password"

# Linux/Mac
export EMAIL_USER="your_email@gmail.com"
export EMAIL_PASS="your_app_password"
```

**For Gmail:**
1. Enable 2-Step Verification
2. Go to https://myaccount.google.com/apppasswords
3. Generate app password for "Mail"
4. Use this password (not your regular password)

#### Step 3: Run Email Parser

```bash
python -m src.email_parser
```

### Usage Examples

**Check last 7 days:**
```python
from src.email_parser import check_newsletters

watchlist = ["Tim Tams", "Coffee", "Chocolate"]
matches = check_newsletters(watchlist, days=7)
```

**Integration with main script:**
```python
# In src/main.py, add email checking:
from src.email_parser import check_newsletters

# After scraping websites, also check emails
email_matches = check_newsletters(WATCHLIST, days=7, verbose=False)
all_matches.update(email_matches)
```

### Customization

**Add more store emails:**
```python
# In src/email_parser.py:
STORE_EMAILS = {
    "Coles": ["coles@coles.com.au", "noreply@coles.com.au"],
    "Woolworths": ["woolworths@woolworths.com.au"],
    "Aldi": ["aldi@aldi.com.au"],  # Add more stores
}
```

---

## 🌐 Method 2: Lasoo Catalogue Scraper

### Overview
Scrape from Lasoo.com.au, a legitimate catalogue aggregator service.

### Advantages
- ✅ **Simpler structure** - Easier to scrape than store sites
- ✅ **Multi-store** - One site for all catalogues
- ✅ **Public service** - Designed for viewing catalogues
- ✅ **Fewer restrictions** - Less aggressive bot detection
- ⚠️ **Check robots.txt** - Always verify scraping is allowed

### Setup

No special setup needed! Just run:

```bash
python -m src.lasoo_scraper
```

### Usage Examples

**Basic usage:**
```python
from src.lasoo_scraper import scrape_lasoo_stores

stores = ["coles", "woolworths"]
watchlist = ["Tim Tams", "Coffee", "Milk"]
postcode = "2000"  # Your postcode

matches = scrape_lasoo_stores(stores, watchlist, postcode)
```

**Integration with main script:**
```python
# In src/main.py, add Lasoo as alternative source:
from src.lasoo_scraper import scrape_lasoo_stores

# Use Lasoo instead of direct scraping:
stores = ["coles", "woolworths"]
results = scrape_lasoo_stores(stores, WATCHLIST, postcode="2000")
send_email_alert(results)
```

### Customization

**Add more stores:**
Lasoo supports many Australian retailers. Check their website for store names.

**Adjust selectors:**
If Lasoo changes their HTML structure:
```python
# In src/lasoo_scraper.py, update selectors_to_try:
selectors_to_try = [
    "div.new-product-class",  # Add new selectors here
    "div[class*='product']",
    # ... existing selectors
]
```

---

---

## 📄 Method 3: PDF Catalogue Parser

### Overview
Extract product information directly from PDF catalogues published by stores.

### Advantages
- ✅ **Official documents** - Published by stores
- ✅ **Complete data** - Full catalogue content
- ✅ **No bot detection** - Just reading PDFs
- ✅ **Offline capable** - Process downloaded files
- ✅ **Consistent format** - PDFs less likely to change

### Setup

Install PDF parsing libraries:
```bash
pip install pdfplumber pypdf2
```

### Usage Examples

**Single PDF file:**
```bash
python -m src.pdf_parser catalogue.pdf
```

**Batch process directory:**
```bash
python -m src.pdf_parser ./catalogues/
```

**In Python code:**
```python
from src.pdf_parser import parse_catalogue_pdf

watchlist = ["Tim Tams", "Coffee", "Milk"]
results = parse_catalogue_pdf("coles_catalogue.pdf", watchlist)
```

### Finding PDF Catalogues

**Coles:**
- Visit https://www.coles.com.au/catalogues-and-specials
- Look for PDF download links
- Right-click catalogue → "Save as PDF" if viewing online

**Woolworths:**
- Visit https://www.woolworths.com.au/shop/catalogue
- Similar PDF download options
- Use browser print → "Save as PDF"

**Third-party sites:**
- Lasoo.com.au often has PDF versions
- Store mobile apps may offer PDF downloads

### Automation

**Download PDFs automatically:**
```python
from src.pdf_parser import download_pdf

url = "https://example.com/catalogue.pdf"
download_pdf(url, "catalogue.pdf")
```

**Schedule weekly parsing:**
```bash
# In cron (Raspberry Pi):
0 9 * * 3 /path/to/python /path/to/pdf_parser.py /path/to/catalogues/
```

---

## 📊 Comparison Matrix

| Feature | Direct Scraping | Email Parser | Lasoo Scraper | PDF Parser |
|---------|----------------|--------------|---------------|------------|
| **Setup Complexity** | High | Medium | Low | Low |
| **Reliability** | Low | High | Medium | High |
| **Bot Detection** | High risk | None | Low risk | None |
| **Legal Concerns** | Possible | None | Check ToS | None |
| **Data Freshness** | Real-time | Weekly | Real-time | Weekly |
| **Maintenance** | High | Low | Medium | Low |
| **Product Coverage** | Complete | Highlights | Complete | Complete |
| **Offline Capable** | No | No | No | Yes |

---

## 🎯 Recommended Approach

### For Home Use (Best):

**Hybrid Approach:**
1. **Primary**: PDF parsing (most complete and reliable)
2. **Secondary**: Email parsing (highlights and deals)
3. **Backup**: Lasoo scraping (if PDFs unavailable)
4. **Fallback**: Direct scraping (last resort)

```python
# Pseudo-code for hybrid approach:
def get_specials(watchlist):
    matches = {}
    
    # Try PDF catalogues first (best option if available)
    pdf_dir = "./catalogues/"
    if os.path.exists(pdf_dir):
        pdf_matches = batch_parse_catalogues(pdf_dir, watchlist)
        if pdf_matches:
            matches.update(pdf_matches)
            return matches
    
    # Try email newsletters (good for highlights)
    email_matches = check_newsletters(watchlist, days=7)
    if email_matches:
        matches.update(email_matches)
        return matches
    
    # Fall back to Lasoo
    lasoo_matches = scrape_lasoo_stores(["coles", "woolworths"], watchlist)
    if lasoo_matches:
        matches.update(lasoo_matches)
        return matches
    
    # Last resort: direct scraping
    direct_matches = scrape_direct_websites(watchlist)
    matches.update(direct_matches)
    
    return matches
```

### For Production (Recommended):

**PDF + Email Approach:**
- Most complete data (PDF catalogues)
- Highlights and deals (Email newsletters)
- No legal concerns
- Lowest maintenance
- Download PDFs weekly
- Parse both PDFs and emails on schedule

---

## 🔧 Troubleshooting

### Email Parser Issues

**"Failed to connect to email":**
- Check EMAIL_USER and EMAIL_PASS are set
- For Gmail, use app password, not regular password
- Enable IMAP in email settings

**"No store emails found":**
- Verify you're subscribed to newsletters
- Check spam folder
- Wait for weekly newsletter delivery
- Try searching for older emails (increase days parameter)

**Products not extracted correctly:**
- Email HTML structure varies by store
- Update parsing logic in `parse_email_for_products()`
- Look for different HTML patterns

### Lasoo Scraper Issues

**"No catalogues found":**
- Check store name spelling (use lowercase: "coles", "woolworths")
- Visit lasoo.com.au manually to verify store availability
- Check internet connection

**Wrong products extracted:**
- Lasoo HTML structure may have changed
- Update selectors in `scrape_lasoo_catalogue()`
- Use browser DevTools to find new class names

**Timeout errors:**
- Increase timeout values in code
- Check internet speed
- Try running during off-peak hours

### PDF Parser Issues

**"No PDF library installed":**
- Install libraries: `pip install pdfplumber pypdf2`
- pdfplumber is recommended for better extraction
- PyPDF2 is fallback option

**"File not found":**
- Check PDF file path is correct
- Use absolute paths: `C:\path\to\catalogue.pdf`
- Ensure PDF was downloaded successfully

**Few or no products extracted:**
- PDF may be image-based (scanned) - requires OCR
- Try different PDF source
- Some catalogues use complex layouts
- Check extracted text manually to verify quality

**Prices not detected:**
- Update price pattern regex in code
- Some stores use unusual price formatting
- Check if PDF uses images instead of text

**Install Tesseract OCR (for image-based PDFs):**
```bash
# Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
# Linux: sudo apt-get install tesseract-ocr
# Mac: brew install tesseract

# Then: pip install pytesseract
```

---

## 📝 Implementation Guide

### Adding to Main Script

Update `src/main.py` to use alternative methods:

```python
# Add imports at top:
from src.email_parser import check_newsletters
from src.lasoo_scraper import scrape_lasoo_stores
from src.pdf_parser import batch_parse_catalogues, parse_catalogue_pdf
import os

# In main() function, replace or add to scraping logic:
def main() -> None:
    scrape_test_mode = SCRAPE_TEST_MODE or "--scrape-test" in sys.argv
    use_email = "--email" in sys.argv
    use_lasoo = "--lasoo" in sys.argv
    use_pdf = "--pdf" in sys.argv
    
    results = {}
    
    if use_pdf:
        print("Using PDF catalogue method...")
        pdf_path = sys.argv[sys.argv.index("--pdf") + 1] if len(sys.argv) > sys.argv.index("--pdf") + 1 else "./catalogues"
        if os.path.isdir(pdf_path):
            results = batch_parse_catalogues(pdf_path, WATCHLIST)
        else:
            results = parse_catalogue_pdf(pdf_path, WATCHLIST)
    elif use_email:
        print("Using email newsletter method...")
        results = check_newsletters(WATCHLIST, days=7, verbose=True)
    elif use_lasoo:
        print("Using Lasoo catalogue method...")
        results = scrape_lasoo_stores(
            ["coles", "woolworths"], 
            WATCHLIST, 
            postcode="2000"
        )
    else:
        # Original direct scraping method
        for store in STORES:
            # ... existing code
    
    send_email_alert(results, scrape_test=scrape_test_mode)
    print("Done.")
```

### Command Line Usage

```bash
# Use PDF parser (single file):
python -m src.main --pdf catalogue.pdf

# Use PDF parser (directory):
python -m src.main --pdf ./catalogues

# Use email parser:
python -m src.main --email

# Use Lasoo scraper:
python -m src.main --lasoo

# Test mode with PDF:
python -m src.main --pdf catalogue.pdf --scrape-test

# Test mode with email:
python -m src.main --email --scrape-test

# Test mode with Lasoo:
python -m src.main --lasoo --scrape-test
```

---

## 🚀 Next Steps

1. **Download PDF catalogues** from store websites
2. **Subscribe to newsletters** (if using email method)
3. **Test each method** individually:
   - `python -m src.pdf_parser catalogue.pdf`
   - `python -m src.email_parser`
   - `python -m src.lasoo_scraper`
4. **Choose your preferred approach** (PDF recommended)
5. **Update main.py** to integrate chosen method
6. **Set up on Raspberry Pi** (see RASPBERRY_PI_SETUP.md)
7. **Schedule with cron** for automatic monitoring

---

## ⚖️ Legal & Ethical Considerations

### Email Parsing
- ✅ **Legal** - Reading your own emails
- ✅ **Ethical** - Using officially provided content
- ✅ **Sustainable** - No impact on store servers

### Lasoo Scraping
- ⚠️ **Check robots.txt**: https://www.lasoo.com.au/robots.txt
- ⚠️ **Read Terms of Service**: https://www.lasoo.com.au/terms
- ⚠️ **Use reasonable rate limits**
- ⚠️ **Respect their infrastructure**

### Direct Website Scraping
- ⚠️ **May violate Terms of Service**
- ⚠️ **Risk of IP blocking**
- ⚠️ **Higher maintenance burden**
- ⚠️ **Consider alternatives first**

**Always prioritize methods that:**
- Respect website ToS
- Don't overload servers
- Use officially provided data when available
- Maintain good internet citizenship

---

## 📚 Additional Resources

- **Email Parser Code**: `src/email_parser.py`
- **Lasoo Scraper Code**: `src/lasoo_scraper.py`
- **Cookie Management**: `COOKIE_GUIDE.md`
- **Raspberry Pi Setup**: `RASPBERRY_PI_SETUP.md`
- **General Scraping Guide**: `SCRAPING_GUIDE.md`

---

**Ready to try?**
```bash
# Test PDF parser (download a catalogue PDF first):
python -m src.pdf_parser catalogue.pdf

# Test email parser (requires email credentials):
python -m src.email_parser

# Test Lasoo scraper:
python -m src.lasoo_scraper
```
