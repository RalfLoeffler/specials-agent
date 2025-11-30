# Cookie and Session Management Guide

## Overview

Many grocery store websites require you to:
- Accept cookie notices
- Enter your postcode/suburb
- Select a preferred store
- Set location preferences

This guide explains how to save these preferences so your scraper can automatically use them.

## 🍪 How Playwright Handles Cookies

Playwright can save and restore complete browser sessions, including:
- **Cookies** - HTTP cookies set by websites
- **LocalStorage** - Browser local storage data
- **SessionStorage** - Session-specific data
- **Location preferences** - Postcode, suburb, store selection
- **Authentication tokens** - If you're logged in

## 🚀 Quick Start

### Step 1: Run the Session Setup Script

```bash
python setup_session.py
```

This will:
1. Open a visible browser window
2. Let you manually enter your postcode
3. Accept cookie notices
4. Save everything for future use

### Step 2: Use Your Saved Session

Your scraper automatically uses the saved session:

```bash
python -m src.main --scrape-test
```

That's it! The scraper will now use your postcode and preferences.

## 📋 Detailed Setup Instructions

### First Time Setup

1. **Run the setup script:**
   ```bash
   python setup_session.py
   ```

2. **Choose which store to setup:**
   - Enter `1` for Coles
   - Enter `2` for Woolworths
   - Enter `3` for both
   - Enter `4` for a custom URL

3. **In the browser that opens:**
   - Wait for the page to fully load
   - Look for postcode/location prompts
   - Enter your postcode (e.g., "2000" for Sydney CBD)
   - Click "Set Location" or similar button
   - Accept any cookie notices
   - Browse a catalogue page to verify it works
   - **Close the browser window** when done

4. **Session is saved:**
   - File created: `browser_session.json`
   - Contains all your preferences
   - Used automatically by the scraper

### Updating Your Location

Just run the setup script again:
```bash
python setup_session.py
```

It will overwrite the old session with your new preferences.

## 🔧 Technical Details

### Session File Structure

The `browser_session.json` file contains:

```json
{
  "cookies": [
    {
      "name": "postcode",
      "value": "2000",
      "domain": ".coles.com.au",
      ...
    }
  ],
  "origins": [
    {
      "origin": "https://www.coles.com.au",
      "localStorage": [
        {
          "name": "selectedStore",
          "value": "..."
        }
      ]
    }
  ]
}
```

### How the Scraper Uses Sessions

In `src/main.py`, the `fetch_items()` function:

```python
# Check if session file exists
if use_saved_session and os.path.exists(session_file):
    # Load saved session
    context = browser.new_context(storage_state=session_file)
    page = context.new_page()
else:
    # Create new session
    page = browser.new_page()
```

### Disabling Session Loading

If you want to test without saved sessions:

```python
# In src/main.py, modify the fetch_items call:
items = fetch_items(store["url"], store["product_selector"], use_saved_session=False)
```

## 🔐 Security Considerations

### Important Notes

1. **Personal Data**: The session file contains your location and browsing data
2. **Git Ignore**: Already added to `.gitignore` - won't be committed
3. **File Permissions**: Consider restricting access on Raspberry Pi:
   ```bash
   chmod 600 browser_session.json
   ```

4. **Expiration**: Cookies may expire - rerun setup if scraper stops working

### What's Stored

✅ **Safe to Store:**
- Postcode/location preferences
- Cookie acceptance flags
- Store selection
- UI preferences

❌ **Never Store:**
- Login credentials (use environment variables)
- Payment information
- Personal account details

## 🌍 Location-Specific Features

### Geolocation

The setup script sets realistic geolocation:

```python
context = browser.new_context(
    geolocation={'latitude': -33.8688, 'longitude': 151.2093},  # Sydney
    permissions=['geolocation']
)
```

### Timezone and Locale

Also configured for Australian stores:

```python
context = browser.new_context(
    locale='en-AU',
    timezone_id='Australia/Sydney'
)
```

## 🛠️ Troubleshooting

### Session Not Working

**Problem**: Scraper still asks for postcode

**Solutions:**
1. Rerun `python setup_session.py`
2. Make sure you click "Set Location" in the browser
3. Browse to a catalogue page before closing browser
4. Check that `browser_session.json` exists in project folder

### Session Expired

**Problem**: Worked before, now asking for postcode again

**Solution:**
- Cookies have expiration dates
- Rerun setup script to refresh session
- Some stores expire sessions after 30-90 days

### Multiple Stores

**Problem**: Need different postcodes for different stores

**Solution:**
You can create store-specific session files:

```python
# In src/main.py, modify STORES:
STORES = [
    {
        "name": "Coles",
        "url": "https://www.coles.com.au/catalogues-and-specials",
        "product_selector": "...",
        "session_file": "coles_session.json"  # Add this
    },
    {
        "name": "Woolworths",
        "url": "https://www.woolworths.com.au/shop/catalogue",
        "product_selector": "...",
        "session_file": "woolworths_session.json"  # Add this
    }
]

# Update fetch_items to use store-specific session:
session_file = store.get("session_file", "browser_session.json")
```

### Inspecting Session Contents

To see what's in your session file:

```bash
# Windows PowerShell
Get-Content browser_session.json | ConvertFrom-Json | ConvertTo-Json -Depth 10

# Linux/Mac
cat browser_session.json | python -m json.tool
```

## 📱 Mobile User Agent

Some stores show different content on mobile. To use mobile mode:

```python
# In setup_session.py or fetch_items(), use:
context = browser.new_context(
    user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
    viewport={'width': 375, 'height': 667},
    device_scale_factor=2,
    is_mobile=True,
    has_touch=True
)
```

## 🔄 Session Lifecycle

```
┌─────────────────────────────────────────┐
│  1. Run: python setup_session.py        │
│     - Opens browser                      │
│     - You set postcode manually          │
│     - Session saved                      │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  2. Run: python -m src.main             │
│     - Loads saved session                │
│     - Scrapes with your location         │
│     - Updates session if needed          │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  3. Session expires after 30-90 days    │
│     - Scraper asks for postcode again    │
│     - Rerun setup_session.py             │
└─────────────────────────────────────────┘
```

## 🎯 Best Practices

1. **Run setup once** - Only need to do this when:
   - First time setup
   - Moving to new location
   - Session expires

2. **Keep session file secure** - Contains browsing data:
   - Never commit to Git (already in `.gitignore`)
   - Restrict file permissions on servers
   - Don't share publicly

3. **Verify it works** - After setup:
   - Run `python -m src.main --scrape-test`
   - Check log for "→ Loaded saved session"
   - Verify products are from your area

4. **Update regularly** - If store layouts change:
   - Rerun setup to capture new cookie requirements
   - Update selectors if needed

## 📚 Additional Resources

- [Playwright Authentication Guide](https://playwright.dev/python/docs/auth)
- [Browser Context Documentation](https://playwright.dev/python/docs/browser-contexts)
- [Storage State API](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-storage-state)

## ✅ Verification Checklist

After running setup, verify:

- [ ] `browser_session.json` file exists
- [ ] File size > 100 bytes (contains data)
- [ ] Running scraper shows "→ Loaded saved session"
- [ ] Products match your location
- [ ] No postcode prompts when scraping

---

**Next Steps:**
1. Run `python setup_session.py`
2. Enter your postcode in the browser
3. Close browser when done
4. Run `python -m src.main --scrape-test`
5. Verify location-specific results!
