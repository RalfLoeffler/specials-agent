# Working with Real Grocery Websites - Important Notes

## ⚠️ Important Disclaimer

Major Australian grocery websites (Coles, Woolworths) implement sophisticated anti-scraping measures to protect their infrastructure and comply with terms of service. This guide explains the challenges and alternatives.

## 🚫 Common Challenges

### 1. Bot Detection
- User-agent checking
- CAPTCHA challenges
- Rate limiting
- IP blocking
- Browser fingerprinting
- JavaScript challenges

### 2. Dynamic Content
- Single Page Applications (SPAs)
- Lazy loading
- Infinite scroll
- API-based content loading

### 3. Legal and Ethical Considerations
- Terms of Service violations
- Potential legal issues
- Server load impact
- Data usage rights

## ✅ Recommended Alternatives

### Option 1: Official APIs or Data Feeds
Check if stores provide:
- Official mobile apps with APIs
- RSS feeds for specials
- Email newsletters
- Official catalogue PDFs

### Option 2: Third-Party Services
- **Lasoo.com.au** - Aggregates catalogues
- **CatalogueAU** - Catalogue aggregator
- Store-specific apps may have easier-to-access data

### Option 3: Manual Catalogue Monitoring
- Subscribe to email newsletters
- Use store mobile apps
- Check PDF catalogues published weekly

## 🔧 If You Must Scrape

If you have permission or the website allows scraping, here's how to improve success:

### 1. Add Realistic Browser Headers
```python
def fetch_items(url: str, product_selector: str) -> list[str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Some sites block headless browsers
            slow_mo=1000     # Slow down actions to appear more human
        )
        
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-AU',
            timezone_id='Australia/Sydney'
        )
        
        page = context.new_page()
        # ... rest of code
```

### 2. Add Random Delays
```python
import random
import time

# Between page loads
time.sleep(random.uniform(2, 5))

# Between actions
await page.wait_for_timeout(random.randint(1000, 3000))
```

### 3. Handle Cookies and Sessions
```python
# Save cookies after first successful visit
context.storage_state(path="auth.json")

# Reuse cookies in future visits
context = browser.new_context(storage_state="auth.json")
```

### 4. Rotate User Agents
```python
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...',
    'Mozilla/5.0 (X11; Linux x86_64)...',
]

user_agent = random.choice(USER_AGENTS)
```

### 5. Use Stealth Plugin
```bash
pip install playwright-stealth
```

```python
from playwright_stealth import stealth_sync

page = browser.new_page()
stealth_sync(page)
```

## 📋 Finding the Right Selectors

### Step 1: Use the Inspector Tool
```bash
python inspect_selectors.py
```

### Step 2: Manual Browser Inspection
1. Open the catalogue page in your browser
2. Press F12 to open DevTools
3. Click the element picker (top-left icon)
4. Click on product items
5. Look for unique classes or IDs that repeat for each product

### Step 3: Test Selectors
Look for patterns like:
- `div.product-card`
- `article[data-product-id]`
- `li.catalogue-item`
- `.tile.special-item`

### Step 4: Verify with Query Selector
In browser console, test:
```javascript
document.querySelectorAll('YOUR_SELECTOR_HERE').length
```

Should return a reasonable number (20-100 typically for a catalogue page).

## 🎯 Practical Example: Using a Test Website

For testing your scraper logic without dealing with anti-bot measures:

```python
STORES = [
    {
        "name": "Test E-commerce",
        "url": "https://webscraper.io/test-sites/e-commerce/allinone",
        "product_selector": ".product-card"
    }
]
```

This test site is specifically designed for web scraping practice.

## 📝 Best Practices

### 1. Respect robots.txt
Check: `https://www.coles.com.au/robots.txt`

### 2. Implement Rate Limiting
```python
import time

# Wait between requests
time.sleep(5)  # 5 seconds between stores
```

### 3. Handle Errors Gracefully
```python
try:
    items = fetch_items(store["url"], store["product_selector"])
except Exception as e:
    logging.error(f"Failed to scrape {store['name']}: {e}")
    continue  # Skip to next store
```

### 4. Monitor and Adapt
- Log all scraping attempts
- Monitor for changes in website structure
- Update selectors when they break
- Consider fallback strategies

## 🚀 Realistic Implementation Strategy

### For Home Use (Recommended):
1. **Subscribe to store newsletters** - Get specials via email
2. **Use store mobile apps** - Often easier to monitor
3. **Check PDF catalogues** - Published weekly, easier to parse
4. **Set up RSS feed monitoring** - If available

### For Development/Learning:
1. **Use test websites** designed for scraping practice
2. **Work with APIs** when available
3. **Focus on websites that allow scraping** (check ToS)
4. **Implement proper error handling and respect rate limits**

## 📖 Additional Resources

- **Playwright Documentation**: https://playwright.dev/python/
- **Web Scraping Best Practices**: https://www.scrapehero.com/web-scraping-best-practices/
- **robots.txt Specification**: https://www.robotstxt.org/
- **Australia's Privacy Act**: Consider legal implications

## ⚖️ Legal Disclaimer

Web scraping may violate terms of service. This code is provided for educational purposes. Users are responsible for:
- Reviewing and complying with website Terms of Service
- Respecting robots.txt directives
- Complying with applicable laws (Computer Fraud and Abuse Act, GDPR, etc.)
- Obtaining permission when required

**Always check a website's Terms of Service and robots.txt before scraping.**

---

## 🎓 Educational Value

This project demonstrates:
- ✅ Python project structure
- ✅ Environment management (Mamba/venv)
- ✅ Web automation with Playwright
- ✅ Email notifications
- ✅ Configuration management
- ✅ Logging and debugging
- ✅ Testing strategies
- ✅ Error handling
- ✅ Deployment to Raspberry Pi

Even if you can't scrape the exact stores you want, the framework and patterns are valuable for many automation tasks!
