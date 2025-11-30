# Grocery Specials Checker (Coles & Woolworths)

This project can run on your **PC** for testing and then on a **Raspberry Pi**
(e.g. OpenHABian) in production. It:

- Checks Coles & Woolworths product data via RapidAPI
- Matches against your **watchlist** (e.g. Tim Tams, Smith's chips)
- Builds a simple text/Markdown report
- Emails it to you weekly using **Gmail + app password**

---

## 1. RapidAPI setup

Create a RapidAPI account and subscribe to these two APIs:

- **Coles Product Price API**  
  https://rapidapi.com/data-holdings-group-data-holdings-group-default/api/coles-product-price-api

- **Woolworths Products API**  
  https://rapidapi.com/data-holdings-group-data-holdings-group-default/api/woolworths-products-api

From either API's "Code Snippets" panel, copy your **X-RapidAPI-Key**.

---

## 2. Files in this bundle

- `specials_checker.py`  
  Main script with:
  - Coles & Woolworths API calls
  - Watchlist handling
  - Report generation
  - Gmail email sending
  - Test helpers (`--test-coles`, `--test-woolies`, `--no-email`)

- `watchlist.yaml`  
  Starter watchlist (Tim Tams, Smith's chips).

- `email_config.yaml.example`  
  Template for Gmail credentials & target address.

- `README.md`  
  This file with instructions.

---

## 3. Testing on your PC

You can test locally on Windows/macOS/Linux using a virtual environment.

### 3.1. Unzip and enter the folder

Put the `grocery_specials_v2.zip` content in a folder, e.g.:

- Windows: `C:\Users\<you>\grocery_specials\`
- macOS/Linux: `~/grocery_specials/`

Then:

```bash
cd /path/to/grocery_specials
```

### 3.2. Create a virtual environment & install dependencies

**Windows (PowerShell):**

```powershell
cd C:\Users\<you>\grocery_specials

py -3 -m venv venv
.env\Scripts\Activate.ps1

pip install requests pyyaml
```

**macOS/Linux (bash/zsh):**

```bash
cd ~/grocery_specials

python3 -m venv venv
source venv/bin/activate

pip install requests pyyaml
```

### 3.3. Set your RapidAPI key

After subscribing to the two APIs and getting your key:

**Windows (PowerShell in the venv):**

```powershell
$env:RAPIDAPI_KEY="your_real_key_here"
```

**macOS/Linux:**

```bash
export RAPIDAPI_KEY="your_real_key_here"
```

---

## 4. Configure email (optional while testing)

Copy the template and edit:

```bash
cp email_config.yaml.example email_config.yaml
nano email_config.yaml   # or use your preferred editor
```

Fill in:

```yaml
gmail_user: "youraddress@gmail.com"
gmail_app_password: "your_16_char_app_password"
to_email: "where_to_send_report@gmail.com"
```

Lock it down (optional but recommended):

```bash
chmod 600 email_config.yaml
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
    only_half_price: true
  - name: "Smith's Chips"
    match_keywords: ["smith chips", "smith's chips"]
    only_half_price: false
```

- `name` – friendly label for the item.
- `match_keywords` – search terms used against both Coles & Woolies.
- `only_half_price` – if `true`, only keep results that appear to be ~50% off.

Add as many items as you like.

---

## 6. Use the test helpers

With the venv activated and `RAPIDAPI_KEY` set:

```bash
# Test Coles API shape with a keyword
python specials_checker.py --test-coles "tim tam"

# Test Woolworths API shape
python specials_checker.py --test-woolies "tim tam"
```

These commands will:

- Call the corresponding API.
- Print top-level JSON keys.
- Show a few product objects (trimmed pretty JSON).

Use these outputs to confirm (or adjust) field names in:

- `normalise_coles_product`
- `normalise_woolies_product`

If you see different field names (e.g. `UnitPrice` instead of `CurrentPrice`),
edit the script accordingly.

---

## 7. Run the full checker (no email vs email)

To run the full watchlist scan **without** sending an email:

```bash
python specials_checker.py --no-email
```

To run with email enabled (requires `email_config.yaml`):

```bash
python specials_checker.py
```

You should see the report printed in the terminal, and (when email is enabled)
an email should arrive at `to_email`.

---

## 8. Deploying to Raspberry Pi (OpenHABian)

Once it works on your PC:

1. Copy the entire folder to your Pi, e.g.:

   ```bash
   scp -r ./grocery_specials openhabian@your_pi_ip:/home/openhabian/
   ```

2. On the Pi, create a virtualenv and install deps:

   ```bash
   cd /home/openhabian/grocery_specials

   sudo apt update
   sudo apt install -y python3-venv python3-pip

   python3 -m venv venv
   source venv/bin/activate

   pip install requests pyyaml
   ```

3. Set your RapidAPI key on the Pi:

   ```bash
   echo 'export RAPIDAPI_KEY="your_real_key_here"' >> ~/.bashrc
   source ~/.bashrc
   ```

4. Place your `email_config.yaml` and `watchlist.yaml` in the same folder.

5. Test on the Pi:

   ```bash
   cd /home/openhabian/grocery_specials
   source venv/bin/activate
   python specials_checker.py --no-email
   ```

   Then, when happy:

   ```bash
   python specials_checker.py
   ```

---

## 9. Add a weekly cron job on the Pi

Edit crontab for user `openhabian`:

```bash
crontab -e
```

Add a line to run every Wednesday at 09:05:

```cron
5 9 * * 3 /home/openhabian/grocery_specials/venv/bin/python /home/openhabian/grocery_specials/specials_checker.py >> /home/openhabian/grocery_specials/cron.log 2>&1
```

Check paths:

```bash
ls /home/openhabian/grocery_specials
ls /home/openhabian/grocery_specials/venv/bin/python
```

Ensure cron is running:

```bash
sudo systemctl status cron
```

---

## 10. Troubleshooting tips

- **No email arrives**  
  - Check `cron.log` (on the Pi) or the console output (on PC).
  - Verify Gmail app password & account.
  - Check Gmail's security page for blocked sign-in attempts.

- **RapidAPI errors (401/403/429/etc.)**  
  - Confirm `RAPIDAPI_KEY` exported in the environment.
  - Make sure your subscription plan allows the volume of requests.
  - Use `--test-coles` and `--test-woolies` to see exact error JSON.

Once it’s wired up, your PI becomes a small weekly grocery intel node,
politely emailing you whenever your favourite snacks dance on special.
