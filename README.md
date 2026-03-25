# Grocery Specials Checker (Coles & Woolworths)

This project can run on your PC for testing and then on a Raspberry Pi
(for example OpenHABian) in production. It:

- Checks Coles and Woolworths product data via RapidAPI
- Matches against your watchlist
- Builds a simple text/Markdown report
- Emails it to you weekly using Gmail or another SMTP server

---

## 1. RapidAPI setup

Create a RapidAPI account and subscribe to these two APIs:

- **Coles Product Price API**
  https://rapidapi.com/data-holdings-group-data-holdings-group-default/api/coles-product-price-api
- **Woolworths Products API**
  https://rapidapi.com/data-holdings-group-data-holdings-group-default/api/woolworths-products-api

From either API's code snippets panel, copy your `X-RapidAPI-Key`.

---

## 2. Files in this repo

- `src/specials_checker.py`
  Main script with API calls, watchlist handling, report generation, email
  sending, and test helpers.
- `src/watchlist_excel_export.py`
  Exports `watchlist.yaml` to Excel for easier editing.
- `src/watchlist_excel_import.py`
  Imports Excel watchlist edits back into `watchlist.yaml`.
- `watchlist.yaml`
  Watchlist data plus optional `api_limits`, email routing, and numeric filters.
- `config/email_config.yaml.example`
  Template for SMTP credentials and one or more target addresses.
- `config/limits.yaml.example`
  Template for monthly API warning and hard limits.
- `config/secrets.example.yaml`
  Template for the RapidAPI key file.
- `scripts/build_excel_tools.ps1`
  Builds standalone Windows executables for the Excel helper tools.

---

## 3. Local setup

You can test locally on Windows, macOS, Linux, or a Raspberry Pi with a
virtual environment.

### 3.1 Create a virtual environment and install dependencies

**Windows (PowerShell):**

```powershell
cd C:\path\to\specials-agent

py -3 -m venv venv
.\venv\Scripts\Activate.ps1

pip install requests pyyaml openpyxl
```

**macOS/Linux/Raspberry Pi:**

```bash
cd ~/specials-agent

python3 -m venv .venv
source .venv/bin/activate

pip install requests pyyaml openpyxl
```

Runtime dependencies are listed in `requirements.txt`:

```powershell
python -m pip install -r requirements.txt
```

Development/build dependencies are listed in `requirements_dev.txt`:

```powershell
python -m pip install -r requirements_dev.txt
```

### 3.2 Configure your RapidAPI key

You can either set an environment variable or create `config/secrets.yaml`.

**Environment variable:**

```bash
export RAPIDAPI_KEY="your_real_key_here"
```

**Config file:**

```bash
cp config/secrets.example.yaml config/secrets.yaml
nano config/secrets.yaml
```

```yaml
rapidapi_key: "your_real_key_here"
```

---

## 4. Configure email (optional while testing)

Copy the template and edit it:

```bash
cp config/email_config.yaml.example email_config.yaml
nano email_config.yaml
```

Preferred location:

```bash
cp config/email_config.yaml.example config/email_config.yaml
nano config/email_config.yaml
```

Legacy fallback:

```bash
cp config/email_config.yaml.example email_config.yaml
nano email_config.yaml
```

Fill in:

```yaml
gmail_user: "youraddress@gmail.com"
auth_mode: "app_password"   # or "password"
gmail_app_password: "your_16_char_app_password"
# gmail_password: "your_regular_password_here"
smtp_host: "smtp.gmail.com"
smtp_port: 587
smtp_use_tls: true
email_subject: "Weekly grocery specials report"
email_test_subject: "Email test - grocery specials checker"
report_verbose: false
report_calls: false
to_email: "where_to_send_report@gmail.com"
# Optional indexed recipient list used by watchlist email_index/email_indices.
# report_verbose can also be a list aligned with to_emails, for example:
# report_verbose: [true, false]
# report_calls can also be a list aligned with to_emails, for example:
# report_calls: [true, false]
# to_emails:
#   - "where_to_send_report@gmail.com"   # index 0
#   - "someone_else@gmail.com"           # index 1
```

Notes:

- `auth_mode: "app_password"` uses `gmail_app_password`
- `auth_mode: "password"` uses `gmail_password`
- `smtp_host`, `smtp_port`, and `smtp_use_tls` are optional and default to the
  Gmail SMTP settings shown above
- `email_subject` controls the normal report subject line
- `email_test_subject` controls the `--test-email` subject line
- emails include an HTML table view with a plain-text fallback
- `report_verbose: true` adds extra columns such as previous price and barcode
- `report_calls: true` appends the accumulated monthly API call counts to the
  bottom of the email
- `to_email` keeps the original single-recipient behaviour
- `to_emails` is an optional ordered recipient list; when present, watchlist
  entries can route matches by zero-based index
- when `to_emails` is used, `report_verbose` can be a matching list of booleans
  so each recipient can opt in or out independently
- when `to_emails` is used, `report_calls` can be a matching list of booleans
  so each recipient can opt in or out independently
- Gmail often rejects regular password SMTP logins unless the account/provider
  explicitly allows them, so `app_password` is usually the safer option

Optional hardening:

```bash
chmod 600 config/email_config.yaml
chmod 600 config/secrets.yaml
```

---

## 5. Configure your watchlist

Edit `watchlist.yaml`:

```bash
nano watchlist.yaml
```

Example:

```yaml
items:
  - name: "Tim Tam"
    match_keywords: ["tim tam"]
    include_keywords: ["tim tam", "tim tams"]
    exclude_keywords: []
    stores: ["Coles", "Woolworths"]
    email_indices: [0]
    price_range: "<5.00"
    size_range: "150-200"
    include_unknown_half_price: true
    only_half_price: true
  - name: "Smith's Chips"
    match_keywords: ["smith chips", "smith's chips"]
    include_keywords: ["smith chips", "smith's chips", "crinkle cut"]
    exclude_keywords: ["lunchbox"]
    stores: ["Coles", "Woolworths"]
    email_index: 1
    size_range: "150-200"
    include_unknown_half_price: true
    only_half_price: false
  - name: "Glow Lab"
    match_keywords: ["glow lab"]
    # No email_index/email_indices means send this item to every configured
    # recipient.
```

- `name` - friendly label for the item.
- `match_keywords` - search terms used against both stores.
- `include_keywords` - optional final inclusion filter used after API results are
  fetched. If omitted, it falls back to `match_keywords`.
- `exclude_keywords` - terms that should remove products from the comparison.
- `stores` - optional store filter. Use `["Coles"]`, `["Woolworths"]`, or both.
  If omitted or blank, the checker searches both stores.
  Use `["none"]` to pause that watchlist item without deleting it.
- `include_unknown_half_price` - when `only_half_price` is enabled, still show
  products whose current price is known but previous price is not.
- `only_half_price` - if `true`, only keep results that appear to be about 50%
  off.
- `price_range` - optional numeric price filter such as `1.50`, `1-1.50`,
  `<1.50`, `<=1.50`, `>2`, or `>=2`.
- `size_range` - optional numeric size filter such as `900`, `800-1000`,
  `<1000`, `<=1000`, `>800`, or `>=800`.
- `email_index` - optional zero-based recipient index for a single target
  address from `to_emails`.
- `email_indices` - optional list of zero-based recipient indices when the item
  should go to multiple configured addresses.

Matching notes:

- matching checks the combined product title, brand, and size fields
- `match_keywords` drives the API search step
- `include_keywords` is applied after the API response is fetched, just before
  final inclusion in the report/email
- exact phrase matches are preferred first
- if the full phrase is not found, matching falls back to token coverage
- punctuation and apostrophes are normalised, so `smith's` and `smiths` match
  sensibly
- simple singular/plural variants are treated as equivalent in token matching
- `exclude_keywords` uses the same logic and is applied before final inclusion
- `price_range` and `size_range` accept numeric-only input plus range/comparison
  operators; do not include `$`, `ml`, `g`, or other units in the watchlist
- price comparison strips a leading `$` from product data before comparing
- size comparison strips trailing units such as `ml`, `g`, or `kg` from product
  data before comparing
- size filters compare only the extracted numeric value; there is no unit
  conversion between values such as `900g` and `0.9kg`
- if `email_index` / `email_indices` is omitted, that watchlist item is
  included in every recipient's email
- if `to_emails` is not configured, the checker falls back to `to_email`
- `stores: ["none"]` pauses pulling for that item, so it stays in the watchlist
  but no store queries are run for it

Routing example:

```yaml
# config/email_config.yaml
to_emails:
  - "household@example.com"  # index 0
  - "snacks@example.com"     # index 1
  - "beauty@example.com"     # index 2
report_verbose:
  - false  # household gets the compact report
  - true   # snacks gets barcode/was-price detail
  - false  # beauty gets the compact report
report_calls:
  - true   # household sees monthly API counts
  - false  # snacks email hides them
  - true   # beauty sees them

# watchlist.yaml
items:
  - name: "Tim Tam"
    match_keywords: ["tim tam"]
    email_index: 1
  - name: "Glow Lab"
    match_keywords: ["glow lab"]
    email_indices: [0, 2]
  - name: "Milk"
    match_keywords: ["milk"]
    # no index => sent to all three recipients
```

Examples:

- `match_keywords: ["tim tam"]` matches `Arnott's Tim Tam Choc Mint Biscuits`
- `match_keywords: ["tim tam"]` with `include_keywords: ["tim tam", "tim tams"]`
  keeps the API query simple while allowing a broader final inclusion rule
- `match_keywords: ["smith chips"]` can still match `Smith's Crinkle Cut Potato Chips`
- `match_keywords: ["165g"]` can match a product through its size field
- `match_keywords: ["tim tam 165g"]` can match using both title and size
- `exclude_keywords: ["lunchbox"]` removes lunchbox variants before reporting
- `exclude_keywords: ["lunchbox", "mega size"]` removes products matching
  either exclusion term
- `exclude_keywords: ["6 pack"]` removes multipacks if that text appears in the
  title, brand, or size
- `price_range: "<1.50"` matches offers priced below `$1.50`
- `price_range: "2-4"` matches offers priced from `$2.00` to `$4.00`
- `size_range: "800-1000"` matches sizes like `900ml`
- `size_range: "900"` matches sizes like `900ml`

You can also add API usage limits at the top level of `watchlist.yaml`, though
`config/limits.yaml` is cleaner:

```yaml
api_limits:
  default:
    warn: 450
    hard: 480
  coles:
    warn: 430
    hard: 450
  woolworths:
    warn: 430
    hard: 450
```

### 5.1 Edit the watchlist via Excel (optional)

These helpers require `openpyxl`.

Export YAML to Excel:

```bash
python -m src.watchlist_excel_export --yaml watchlist.yaml --excel watchlist.xlsx
```

Import Excel back to YAML:

```bash
python -m src.watchlist_excel_import --excel watchlist.xlsx --yaml watchlist.yaml
```

Expected columns:

- `name`
- `match_keywords`
- `include_keywords` (optional)
- `exclude_keywords` (optional)
- `stores` (optional)
  `none` is also allowed here if you want to pause an item from Excel.
- `email_indices` (optional)
- `price_range` (optional)
- `size_range` (optional)
- `include_unknown_half_price` (optional)
- `only_half_price` (optional)

If the optional columns are missing during import, these defaults are used:

- `exclude_keywords: []`
- `include_keywords`: falls back to `match_keywords`
- `stores: ["Coles", "Woolworths"]`
- `email_indices`: omitted
- `price_range`: omitted
- `size_range`: omitted
- `include_unknown_half_price: true`
- `only_half_price: false`

### 5.2 Build standalone Excel helper executables (optional)

If you want compiled Windows executables for the Excel helper tools, build them from the project's dev environment. The build script automatically prefers `.venv\Scripts\python.exe` when that environment exists.

```powershell
cd C:\repos\specials-agent
powershell -ExecutionPolicy Bypass -File .\scripts\build_excel_tools.ps1
```

If you want to force the interpreter explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_excel_tools.ps1 -Python .\.venv\Scripts\python.exe
```

This builds:

- `dist\excel-tools\watchlist_excel_export.exe`
- `dist\excel-tools\watchlist_excel_import.exe`

Example usage:

```powershell
.\dist\excel-tools\watchlist_excel_export.exe --yaml watchlist.yaml --excel watchlist.xlsx
.\dist\excel-tools\watchlist_excel_import.exe --excel watchlist.xlsx --yaml watchlist.yaml
```
---

## 6. Useful commands

With the virtual environment activated:

```bash
# Inspect live Coles API response structure
python src/specials_checker.py --test-coles "tim tam"

# Inspect live Woolworths API response structure
python src/specials_checker.py --test-woolies "tim tam"

# Run the full checker without sending email
python src/specials_checker.py --testing

# Run against a different watchlist file for testing
python src/specials_checker.py --testing --watchlist test_watchlist.yaml

# Send a sample email without calling the product APIs
python src/specials_checker.py --test-email

# Run the full checker without email but with normal flow
python src/specials_checker.py --no-email

# Run the full checker and send email
python src/specials_checker.py

# Export and re-import the watchlist through Excel
python -m src.watchlist_excel_export --yaml watchlist.yaml --excel watchlist.xlsx
python -m src.watchlist_excel_import --excel watchlist.xlsx --yaml watchlist.yaml
```

Optional maintenance commands:

```bash
python -m ruff check src
python -m black src
python -m compileall src/watchlist_excel_import.py src/watchlist_excel_export.py src/specials_checker.py
```

If needed:

```bash
python -m pip install black ruff
```

---

## 7. Raspberry Pi setup

Once it works on your PC, copy the repo to the Pi. Example:

```bash
scp -r ./specials-agent openhabian@your_pi_ip:/home/openhabian/
```

On the Pi:

```bash
cd /home/openhabian/specials-agent

sudo apt update
sudo apt install -y python3-venv python3-pip

python3 -m venv .venv
source .venv/bin/activate

pip install requests pyyaml openpyxl
```

Create the runtime config files:

```bash
cp config/email_config.yaml.example email_config.yaml
cp config/limits.yaml.example config/limits.yaml
cp config/secrets.example.yaml config/secrets.yaml
```

Then edit:

```bash
nano email_config.yaml
nano config/secrets.yaml
nano watchlist.yaml
```

Test on the Pi:

```bash
cd /home/openhabian/specials-agent
source .venv/bin/activate

python src/specials_checker.py --testing
python src/specials_checker.py --no-email
```

When ready:

```bash
python src/specials_checker.py
```

---

## 8. Weekly cron job on the Pi

Edit the crontab for user `openhabian`:

```bash
crontab -e
```

Example: every Wednesday at 09:05:

```cron
5 9 * * 3 cd /home/openhabian/specials-agent && /home/openhabian/specials-agent/.venv/bin/python src/specials_checker.py >> /home/openhabian/specials-agent/cron.log 2>&1
```

The `cd` is important because the script reads relative paths such as
`watchlist.yaml`, `config/secrets.yaml`, and `email_config.yaml`.

Sanity checks:

```bash
crontab -l
sudo crontab -u openhabian -l
ls /home/openhabian/specials-agent
ls /home/openhabian/specials-agent/.venv/bin/python
sudo systemctl status cron
tail -n 50 /home/openhabian/specials-agent/cron.log
```

---

## 9. API usage limits and monthly counter

- API calls are counted per store and stored in `config/api_usage.json`.
- The counter rotates automatically at the start of each month.
- In `--testing` mode the script prints both the API calls used in the current
  run and the persisted monthly total.
- `config/limits.yaml` can define warning and hard limits per store.
- Product search pagination is capped to the first 2 pages per keyword/store to
  reduce API usage while still covering the most relevant matches.

Example `config/limits.yaml`:

```yaml
api_limits:
  default:
    warn: 450
    hard: 480
  coles:
    warn: 430
    hard: 450
  woolworths:
    warn: 430
    hard: 450
```

---

## 10. Troubleshooting

- No email arrives
  Check `cron.log` on the Pi or console output during manual runs. Verify the
  Gmail app password and account settings.
- RapidAPI errors such as `401`, `403`, or `429`
  Confirm `RAPIDAPI_KEY` or `config/secrets.yaml`, verify your RapidAPI
  subscription, and use `--test-coles` / `--test-woolies` to inspect the
  response.

Once it's wired up, your Pi becomes a small weekly grocery intel node that
emails you when your favourite snacks go on special.




