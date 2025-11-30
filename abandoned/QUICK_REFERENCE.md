# Quick Reference Guide - All Scraping Methods

## 🎯 Which Method Should I Use?

### Best → Good → Okay → Last Resort

1. **📄 PDF Parser** - Download and parse official PDF catalogues
2. **📧 Email Parser** - Monitor newsletters in your inbox
3. **🌐 Lasoo Scraper** - Scrape from catalogue aggregator
4. **🌍 Direct Scraping** - Scrape store websites directly (hardest)

---

## 📄 PDF Catalogue Parser

### When to Use
- Store publishes PDF catalogues
- Want complete product list
- Need offline processing
- Most reliable method

### Quick Start
```bash
# Install dependencies (if not already done)
pip install pdfplumber pypdf2

# Parse single PDF
python -m src.pdf_parser catalogue.pdf

# Parse all PDFs in folder
python -m src.pdf_parser ./catalogues/
```

### Finding PDFs
- **Coles**: https://www.coles.com.au/catalogues-and-specials
- **Woolworths**: https://www.woolworths.com.au/shop/catalogue
- Browser: Right-click catalogue → "Print" → "Save as PDF"

### Pros & Cons
✅ Complete product data  
✅ No bot detection  
✅ Works offline  
✅ Very reliable  
❌ Manual PDF download needed  
❌ Weekly updates only

---

## 📧 Email Newsletter Parser

### When to Use
- Already subscribed to newsletters
- Want highlights and best deals
- Most hands-off approach
- Gmail or similar email access

### Quick Start
```bash
# Set email credentials
$env:EMAIL_USER="your_email@gmail.com"
$env:EMAIL_PASS="your_gmail_app_password"

# Run parser
python -m src.email_parser
```

### Gmail App Password Setup
1. https://myaccount.google.com/apppasswords
2. Generate password for "Mail"
3. Use this password (not your regular password)

### Subscribe to Newsletters
- **Coles**: Footer on coles.com.au
- **Woolworths**: Footer on woolworths.com.au

### Pros & Cons
✅ Fully automatic  
✅ 100% legal  
✅ No maintenance  
✅ Highlights best deals  
❌ Requires email setup  
❌ Weekly updates only  
❌ May miss some products

---

## 🌐 Lasoo Catalogue Scraper

### When to Use
- Don't have PDFs or emails
- Want multiple stores in one place
- Easier than direct scraping
- Quick testing

### Quick Start
```bash
# Just run it!
python -m src.lasoo_scraper
```

### Customize
Edit `src/lasoo_scraper.py`:
```python
stores = ["coles", "woolworths", "aldi"]
watchlist = ["Tim Tams", "Coffee"]
postcode = "2000"  # Your postcode
```

### Pros & Cons
✅ Simple to use  
✅ Multi-store support  
✅ No setup needed  
⚠️ Check Lasoo's terms of service  
❌ May have bot detection  
❌ Structure can change

---

## 🌍 Direct Website Scraping

### When to Use
- Other methods not available
- Need real-time data
- Learning/testing purposes

### Quick Start
```bash
# Setup your location first
python setup_session.py

# Test scraping
python -m src.main --scrape-test
```

### Pros & Cons
✅ Real-time data  
✅ Complete control  
❌ Bot detection issues  
❌ High maintenance  
❌ May violate ToS  
❌ Complex setup

---

## 🔄 Hybrid Approach (Recommended)

Combine multiple methods for best results:

```python
# Try PDF first
if pdf_files_available:
    results = parse_pdfs()
# Fall back to email
elif emails_configured:
    results = check_newsletters()
# Use Lasoo as backup
else:
    results = scrape_lasoo()
```

---

## 📊 Feature Comparison

| Feature | PDF | Email | Lasoo | Direct |
|---------|-----|-------|-------|--------|
| Setup Time | 5 min | 10 min | 0 min | 30 min |
| Reliability | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Coverage | Complete | Highlights | Complete | Complete |
| Legal/ToS | ✅ | ✅ | ⚠️ | ❌ |
| Maintenance | Low | Low | Medium | High |
| Automation | Medium | High | High | Low |

---

## 🚀 Quick Commands Reference

```bash
# PDF Parser
python -m src.pdf_parser catalogue.pdf
python -m src.pdf_parser ./catalogues/

# Email Parser
python -m src.email_parser

# Lasoo Scraper
python -m src.lasoo_scraper

# Direct Scraping (with test mode)
python setup_session.py                # First time setup
python -m src.main --scrape-test       # Test run

# Integration with main script
python -m src.main --pdf catalogue.pdf
python -m src.main --email
python -m src.main --lasoo
```

---

## 🛠️ Installation

### All dependencies
```bash
pip install playwright beautifulsoup4 lxml pdfplumber pypdf2
playwright install chromium
```

### Individual methods
```bash
# PDF only
pip install pdfplumber pypdf2

# Email only
pip install beautifulsoup4 lxml

# Lasoo only
pip install playwright
playwright install chromium

# Direct scraping
pip install playwright
playwright install chromium
```

---

## 📝 Next Steps

1. **Choose your method** (PDF recommended)
2. **Install dependencies** for that method
3. **Test it**:
   - PDF: Download a catalogue PDF
   - Email: Set up Gmail app password
   - Lasoo: Just run it
4. **Integrate into main script** (see ALTERNATIVE_METHODS.md)
5. **Set up scheduling** (see RASPBERRY_PI_SETUP.md)

---

## 📚 Detailed Documentation

- **ALTERNATIVE_METHODS.md** - Complete guide to all methods
- **COOKIE_GUIDE.md** - Session/cookie management
- **SCRAPING_GUIDE.md** - Web scraping best practices
- **RASPBERRY_PI_SETUP.md** - Deployment guide

---

## ⚡ Pro Tips

1. **Start with PDF** - Easiest and most reliable
2. **Add email** - Get highlights automatically
3. **Use Lasoo as backup** - When PDFs unavailable
4. **Avoid direct scraping** - Unless necessary
5. **Combine methods** - Best of all worlds!

---

**Need help?** Check the detailed guides or try the test commands above!
