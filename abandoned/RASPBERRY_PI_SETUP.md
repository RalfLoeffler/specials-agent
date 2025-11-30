# Raspberry Pi Setup Guide for specials-agent

This guide walks you through setting up the specials-agent grocery sale scraper on a Raspberry Pi (tested on openHABian), with automatic weekly execution via cron.

## Prerequisites

- Raspberry Pi running Raspberry Pi OS or openHABian
- Internet connection
- SSH access or direct terminal access
- Gmail account with App Password (or other SMTP email provider)

---

## 1. Update System and Install Python

First, ensure your system is up to date and has Python 3 installed:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git
```

**Verify Python installation:**
```bash
python3 --version  # Should show Python 3.9 or higher
```

---

## 2. Clone or Create Project Directory

### Option A: Clone from GitHub (once published)
```bash
cd ~
git clone https://github.com/YOUR_USERNAME/specials-agent.git
cd specials-agent
```

### Option B: Create manually
```bash
mkdir -p ~/specials-agent/src
cd ~/specials-agent
```

Then copy the files from your development machine:
- `src/main.py`
- `src/__init__.py`
- `pyproject.toml`
- `environment.yml` (optional, for reference)

---

## 3. Create and Activate Virtual Environment

```bash
cd ~/specials-agent
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)` indicating the virtual environment is active.

---

## 4. Install Python Dependencies

### Install required packages:
```bash
pip install --upgrade pip
pip install playwright black flake8 mypy pytest pytest-playwright
```

### Install Playwright browsers:
```bash
playwright install chromium
```

**Note:** Installing only Chromium saves disk space. Full installation:
```bash
playwright install  # Installs Chromium, Firefox, and WebKit
```

### Install system dependencies for Playwright:
```bash
playwright install-deps
```

---

## 5. Configure Environment Variables

Create a `.env` file or add to `~/.bashrc` for persistent configuration.

### Option A: Using .env file (recommended)
```bash
cd ~/specials-agent
nano .env
```

Add the following content:
```bash
# Email Configuration
SALE_ALERT_SMTP_SERVER="smtp.gmail.com"
SALE_ALERT_SMTP_PORT="587"
SALE_ALERT_EMAIL_USER="your_email@gmail.com"
SALE_ALERT_EMAIL_PASS="your_gmail_app_password"
SALE_ALERT_EMAIL_TO="your_email@gmail.com"
```

**Save:** `Ctrl+O`, `Enter`, `Ctrl+X`

### Option B: Using ~/.bashrc (system-wide)
```bash
nano ~/.bashrc
```

Add at the end:
```bash
# Sale Alert Configuration
export SALE_ALERT_SMTP_SERVER="smtp.gmail.com"
export SALE_ALERT_SMTP_PORT="587"
export SALE_ALERT_EMAIL_USER="your_email@gmail.com"
export SALE_ALERT_EMAIL_PASS="your_gmail_app_password"
export SALE_ALERT_EMAIL_TO="your_email@gmail.com"
```

Apply changes:
```bash
source ~/.bashrc
```

### Gmail App Password Setup
1. Go to https://myaccount.google.com/apppasswords
2. Sign in to your Google account
3. Create a new app password named "Raspberry Pi Sale Alerts"
4. Copy the 16-character password
5. Use this password (no spaces) as `SALE_ALERT_EMAIL_PASS`

---

## 6. Test the Script

### Manual test run:
```bash
cd ~/specials-agent
source .venv/bin/activate
python -m src.main
```

**Expected output:**
```
Fetching: Coles ...
Found X matches for Coles.
Fetching: Woolworths ...
Found Y matches for Woolworths.
Sent email with Z match(es).
Done.
```

### Troubleshooting:
- **No matches found:** Normal if no items on your watchlist are on sale
- **Browser error:** Run `playwright install-deps` to install system dependencies
- **Email error:** Check your SMTP credentials and app password

---

## 7. Schedule Weekly Execution with Cron

### Edit crontab:
```bash
crontab -e
```

**If prompted to choose an editor, select nano (usually option 1)**

### Add cron job (runs every Wednesday at 9:00 AM):
```bash
# Sale Alerts - Run every Wednesday at 9:00 AM
0 9 * * 3 /home/openhabian/specials-agent/.venv/bin/python /home/openhabian/specials-agent/src/main.py >> /home/openhabian/specials-agent/alerts.log 2>&1
```

**Note:** Adjust the path if your username is not `openhabian`:
- Replace `/home/openhabian/` with `/home/YOUR_USERNAME/`

### Cron schedule format explained:
```
0 9 * * 3
│ │ │ │ │
│ │ │ │ └── Day of week (3 = Wednesday, 0 = Sunday)
│ │ │ └──── Month (1-12)
│ │ └────── Day of month (1-31)
│ └──────── Hour (0-23)
└────────── Minute (0-59)
```

### Alternative schedules:
```bash
# Every Monday at 8:00 AM
0 8 * * 1 /home/openhabian/specials-agent/.venv/bin/python /home/openhabian/specials-agent/src/main.py >> /home/openhabian/specials-agent/alerts.log 2>&1

# Every day at 7:00 AM
0 7 * * * /home/openhabian/specials-agent/.venv/bin/python /home/openhabian/specials-agent/src/main.py >> /home/openhabian/specials-agent/alerts.log 2>&1

# Twice weekly: Wednesday and Saturday at 9:00 AM
0 9 * * 3,6 /home/openhabian/specials-agent/.venv/bin/python /home/openhabian/specials-agent/src/main.py >> /home/openhabian/specials-agent/alerts.log 2>&1
```

**Save:** `Ctrl+O`, `Enter`, `Ctrl+X`

### Verify cron job:
```bash
crontab -l
```

---

## 8. Create Environment Loading Script (if using .env file)

If you used a `.env` file instead of `~/.bashrc`, create a wrapper script:

```bash
nano ~/specials-agent/run_alert.sh
```

Add content:
```bash
#!/bin/bash
# Load environment variables and run the sale alert script

# Navigate to project directory
cd /home/openhabian/specials-agent

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

# Run the Python script
/home/openhabian/specials-agent/.venv/bin/python /home/openhabian/specials-agent/src/main.py
```

Make executable:
```bash
chmod +x ~/specials-agent/run_alert.sh
```

Update cron to use the wrapper:
```bash
crontab -e
```

Change to:
```bash
0 9 * * 3 /home/openhabian/specials-agent/run_alert.sh >> /home/openhabian/specials-agent/alerts.log 2>&1
```

---

## 9. Monitor and Verify

### View recent log output:
```bash
tail -50 ~/specials-agent/alerts.log
```

### View full log:
```bash
cat ~/specials-agent/alerts.log
```

### Clear log file:
```bash
> ~/specials-agent/alerts.log
```

### Test cron job manually (simulates scheduled run):
```bash
/home/openhabian/specials-agent/.venv/bin/python /home/openhabian/specials-agent/src/main.py >> /home/openhabian/specials-agent/alerts.log 2>&1
```

---

## 10. Maintenance and Updates

### Update watchlist:
```bash
nano ~/specials-agent/src/main.py
```

Modify the `WATCHLIST` array and save.

### Update selectors (if websites change):
Edit the `STORES` configuration in `src/main.py` to update CSS selectors.

### Update Python packages:
```bash
cd ~/specials-agent
source .venv/bin/activate
pip install --upgrade playwright black flake8 mypy pytest
playwright install chromium
```

### Update from Git (if using version control):
```bash
cd ~/specials-agent
git pull origin main
source .venv/bin/activate
pip install --upgrade -r requirements.txt  # if you create one
```

---

## Troubleshooting

### Script runs but no email received:
- Check spam folder
- Verify email credentials in environment variables
- Test email manually: `echo $SALE_ALERT_EMAIL_USER` should show your email
- Check alerts.log for errors

### Playwright browser crashes:
- Increase swap space on Raspberry Pi
- Install only Chromium to save resources: `playwright install chromium`
- Add `--disable-dev-shm-usage` to browser launch args in the script

### Cron job not running:
- Verify cron service: `sudo systemctl status cron`
- Check system time: `date`
- View cron logs: `grep CRON /var/log/syslog`

### Permission errors:
```bash
chmod +x ~/specials-agent/src/main.py
chmod 644 ~/specials-agent/.env
```

---

## Security Best Practices

1. **Never commit credentials to Git:**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Use Gmail App Passwords** instead of your main password

3. **Restrict .env file permissions:**
   ```bash
   chmod 600 ~/specials-agent/.env
   ```

4. **Regularly update system:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

---

## System Resources

### Check Raspberry Pi resources:
```bash
# CPU and memory usage
htop

# Disk space
df -h

# Check if script is running
ps aux | grep python
```

### Estimated requirements:
- **Disk space:** ~500MB for Chromium browser, ~50MB for Python packages
- **RAM:** ~200-300MB while script is running
- **Runtime:** 1-3 minutes per execution (depends on network speed)

---

## Notes

- **Website changes:** Grocery store websites may update their HTML structure. If the script stops finding products, update the `product_selector` in `STORES` configuration.
- **Dynamic content:** Playwright is required because catalogue pages load content dynamically with JavaScript.
- **Rate limiting:** The script includes delays and waits for content to load. Don't run too frequently to avoid being blocked.
- **Headless mode:** Browser runs without a display (headless=True), suitable for Raspberry Pi without monitor.

---

## Support

For issues or questions:
1. Check `alerts.log` for error messages
2. Test the script manually before troubleshooting cron
3. Verify all environment variables are set correctly
4. Ensure Playwright browsers are installed: `playwright install --help`

---

## License

This project is open source. See LICENSE file for details.
