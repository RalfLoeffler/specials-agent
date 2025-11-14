# specials-agent

Automated grocery sale scraper for Australian supermarkets (Coles and Woolworths) using Playwright. Get email alerts when items on your watchlist go on sale!

## Features

- 🛒 **Automated Scraping** - Monitors grocery store websites for specials
- 📧 **Email Alerts** - Sends notifications when watchlist items are on sale
- 🍪 **Cookie/Session Management** - Saves your postcode and location preferences
- 🧪 **Scrape Test Mode** - Test without sending emails
- 📝 **Detailed Logging** - Track all scraping activities
- 🥧 **Raspberry Pi Ready** - Deploy on Raspberry Pi with cron scheduling

## Project Structure

```
specials-agent/
├── .github/
│   └── copilot-instructions.md
├── src/
│   ├── __init__.py
│   └── main.py
├── tests/
│   ├── __init__.py
│   └── test_main.py
├── environment.yml
├── pyproject.toml
├── .flake8
├── .gitignore
└── README.md
```

## Setup

### Prerequisites

- [Mamba](https://mamba.readthedocs.io/) or [Conda](https://docs.conda.io/) installed

### Installation

1. Create the Mamba environment:
   ```bash
   mamba env create -f environment.yml
   ```

2. Activate the environment:
   ```bash
   mamba activate specials-agent
   ```

3. Install Playwright browsers:
   ```bash
   playwright install
   ```

## Quick Start

### 1. Set Up Your Location (Postcode/Cookies)

Stores require your postcode to show local specials:

```bash
python setup_session.py
```

This opens a browser where you can:
- Enter your postcode
- Accept cookies
- Set your preferred store

See [COOKIE_GUIDE.md](COOKIE_GUIDE.md) for details.

### 2. Configure Your Watchlist

Edit `src/main.py` and update the `WATCHLIST`:

```python
WATCHLIST = [
    "Tim Tams",
    "Nescafe",
    "Coca-Cola",
    "Laundry detergent"
]
```

### 3. Test Run (No Emails)

```bash
python -m src.main --scrape-test
```

This runs the scraper without sending emails and shows you what it found.

### 4. Production Run

Once tested, configure email settings and run normally:

```bash
python -m src.main
```

## Development

### Code Quality Tools

This project uses several tools to maintain code quality:

- **Black**: Code formatter (line length: 88)
- **Flake8**: Linting
- **Mypy**: Static type checking
- **Pytest**: Testing framework

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src tests
```

### Linting

```bash
flake8 src tests
```

### Type Checking

```bash
mypy src tests
```

## Usage

Run the main script:

```bash
python -m src.main
```

## License

This project is open source.
