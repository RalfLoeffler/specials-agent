# specials-agent

A Python automation project using Playwright for web automation and testing.

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
