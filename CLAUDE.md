# CLAUDE.md - RepackIt Bot Documentation

## Project Overview

**RepackIt** is a Telegram bot that helps users save money on Amazon purchases by monitoring price drops within the return window. Users can register products they've already purchased, and the bot automatically checks daily for price reductions, notifying them when they can request a partial refund or return/repurchase.

### Core Philosophy
- **Quality First**: Code coverage ≥80%, enforced linting and formatting
- **Webhook-Only**: No polling mode, production-grade from day one
- **Modular Design**: Each component can run independently for testing
- **Performance**: Async operations wherever possible
- **Minimal Docker**: Small images, no unnecessary dependencies

---

## Technology Stack

- **Language**: Python 3.11+
- **Package Manager**: `uv` (not pip)
- **Telegram Library**: `python-telegram-bot` (webhook mode)
- **Web Scraping**: Playwright (headless mode)
- **Database**: SQLite
- **Code Quality**: Black (formatter) + Ruff (linter)
- **Testing**: pytest with ≥80% coverage
- **CI/CD**: SonarCloud integration
- **Containerization**: Docker with multi-stage builds

---

## Project Structure

```
repackit/
├── bot.py                    # Main bot with webhook + scheduler
├── data_reader.py            # Amazon scraper (Playwright)
├── checker.py                # Price comparison & notifications
├── product_cleanup.py        # Removes expired products
├── broadcast.py              # Admin-only manual broadcast script
├── health_handler.py         # Health check endpoint
├── handlers/                 # Command handlers (one file per command)
│   ├── __init__.py
│   ├── start.py
│   ├── add.py
│   ├── list.py
│   ├── delete.py
│   ├── update.py
│   └── feedback.py
├── tests/                    # Unit tests mirroring src structure
│   ├── test_bot.py
│   ├── test_data_reader.py
│   ├── test_checker.py
│   ├── test_product_cleanup.py
│   ├── test_broadcast.py
│   └── handlers/
│       ├── test_start.py
│       └── ...
├── data/                     # Persistent data (mounted volume)
│   ├── users.db
│   └── logs/
├── .env                      # Environment variables (gitignored)
├── .env.example              # Template for .env
├── pyproject.toml            # uv dependencies + tool config
├── Dockerfile                # Multi-stage build
├── docker-compose.yml        # Production orchestration
├── .github/workflows/        # CI/CD pipelines
│   ├── test.yml
│   ├── lint.yml
│   └── docker.yml
├── .pre-commit-config.yaml   # Local git hooks
└── CLAUDE.md                 # This file
```

---

## Database Schema

### `users` Table
```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,      -- Telegram user ID
    language_code TEXT,                -- Auto-detected from Telegram (e.g., "it")
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `products` Table
```sql
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    asin TEXT NOT NULL,                          -- Amazon Standard Identification Number
    price_paid REAL NOT NULL,                    -- Price user paid (€)
    return_deadline DATE NOT NULL,               -- Last day to return
    min_savings_threshold REAL DEFAULT 0,        -- Minimum € to notify (optional)
    last_notified_price REAL,                    -- Prevents duplicate notifications
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### `feedback` Table
```sql
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### `system_status` Table
```sql
CREATE TABLE system_status (
    key TEXT PRIMARY KEY,                         -- Status key (e.g., "last_scraper_run")
    value TEXT NOT NULL,                          -- Status value (ISO timestamp)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Important Notes**:
- Users never see the database `id`. Commands use 1-based indexing from their personal product list.
- `last_notified_price` follows OctoTracker pattern: only notify if new price is **lower** than last notification.
- `return_deadline` is stored as DATE, supporting both "30 giorni" and "2024-12-25" input formats.
- `system_status` tracks scheduled task execution for health checks (see `health_handler.py`).

---

## Environment Variables

Reference `.env.example` for the template. All variables:

```bash
# Telegram Bot
TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
WEBHOOK_URL=https://your-domain.com
WEBHOOK_SECRET=your-secret-token-here

# Server Ports
BOT_PORT=8443          # Telegram webhook listener
HEALTH_PORT=8444       # Health check endpoint

# Database
DATABASE_PATH=./data/users.db

# Scheduler (24-hour format, e.g., 9 = 09:00)
SCRAPER_HOUR=9         # Daily scraping time
CHECKER_HOUR=10        # Daily price check time
CLEANUP_HOUR=2         # Daily cleanup time (removes expired products)

# Admin
ADMIN_USER_ID=123456789  # Telegram user ID for broadcast.py script verification

# Amazon Affiliate
AMAZON_AFFILIATE_TAG=yourtag-21  # Amazon affiliate tag for monetization

# Logging
LOG_LEVEL=INFO         # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Development Setup**:
- Use Cloudflare Tunnel or ngrok for `WEBHOOK_URL` during local development
- Keep `.env` gitignored, commit `.env.example` instead

---

## Core Components

### 1. `bot.py` - Main Application

**Responsibilities**:
- Initialize webhook on startup
- Route commands to handlers
- Run three scheduled tasks (scraper, checker, cleanup)
- Health check endpoint integration

**Scheduler Pattern** (from OctoTracker):
```python
# Sleep-based scheduling - calculates exact sleep duration
async def schedule_scraper():
    while True:
        await run_scraper()
        next_run = calculate_next_run(hour=SCRAPER_HOUR)
        await asyncio.sleep(next_run - datetime.now())
```

**Key Features**:
- Async architecture throughout
- Graceful shutdown handling
- Secret-based webhook validation

---

### 2. `data_reader.py` - Amazon Scraper

**Responsibilities**:
- Parse ASIN from Amazon URLs (supports multiple formats)
- Scrape current price using Playwright
- Handle anti-bot measures gracefully

**ASIN Parsing** (Modular for Future Marketplaces):
```python
def extract_asin(url: str) -> tuple[str, str]:
    """
    Returns (asin, marketplace).
    Examples:
    - amazon.it/dp/B08N5WRWNW → ("B08N5WRWNW", "it")
    - amazon.it/gp/product/B08N5WRWNW → ("B08N5WRWNW", "it")
    """
    # Regex pattern supporting .it, .com, .de, .fr, etc.
    # Currently only .it is scraped, but code is prepared for expansion
```

**Scraping Strategy**:
- **Headless Playwright**: Fast, lightweight
- **Rate Limiting**: 1-2 second delay between requests
- **Error Handling**: Skip failed scrapes, log as WARNING, retry next day
- **User Agent Rotation**: Randomize to avoid detection (future enhancement)

**Async Pattern**:
```python
async def scrape_products(products: list) -> dict:
    """Scrapes all products concurrently with rate limiting."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Concurrent scraping with semaphore control
```

**Can Run Standalone**:
```bash
uv run python data_reader.py  # Manual scraping execution
```

---

### 3. `checker.py` - Price Comparison & Notifications

**Responsibilities**:
- Compare scraped prices vs. `price_paid`
- Apply `min_savings_threshold` filter
- Send notifications only if price < `last_notified_price`
- Update `last_notified_price` after notification

**Notification Logic**:
```python
if current_price < price_paid:
    savings = price_paid - current_price
    if savings >= min_savings_threshold:
        if last_notified_price is None or current_price < last_notified_price:
            send_notification(user_id, savings, current_price)
            update_last_notified_price(product_id, current_price)
```

**Message Format**:
```
🎉 Prezzo in calo su Amazon!

Il prodotto che stai monitorando è sceso a €45.99
Prezzo pagato: €59.90
Risparmio: €13.91

Scadenza reso: 15/12/2024 (tra 12 giorni)

🔗 [Vai al prodotto](https://amazon.it/dp/B08N5WRWNW?tag=yourtag-21)
```

**Affiliate URL Construction**:
All product URLs sent to users include the `AMAZON_AFFILIATE_TAG` for monetization:
```python
# Format: https://amazon.it/dp/{ASIN}?tag={AFFILIATE_TAG}
url = f"https://amazon.it/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
```

**Can Run Standalone**:
```bash
uv run python checker.py  # Manual check execution
```

---

### 4. `product_cleanup.py` - Expired Product Removal

**Responsibilities**:
- Run daily at `CLEANUP_HOUR` (default: 02:00)
- Delete products where `return_deadline < today`
- Log cleanup operations

**Can Run Standalone**:
```bash
uv run python product_cleanup.py  # Manual cleanup
```

---

### 5. `broadcast.py` - Admin Broadcast Script

**Responsibilities**:
- Send broadcast messages to all registered users
- Admin-only script (not a bot command for enhanced security)
- Requires manual execution by admin

**Security Design**:
Unlike a `/broadcast` bot command, this is a standalone Python script that must be executed manually. This prevents abuse even if an attacker gains access to `ADMIN_USER_ID`.

**Usage**:
```bash
uv run python broadcast.py "Messaggio da inviare a tutti gli utenti"
```

**Implementation Notes**:
- Validates `ADMIN_USER_ID` from environment
- Sends message to all users in database
- Implements rate limiting (avoid Telegram flood limits)
- Logs all broadcast operations
- Reports delivery statistics (sent, failed)

**Example Output**:
```
[INFO] Starting broadcast to 1,234 users
[INFO] Progress: 500/1234 (40%)
[INFO] Progress: 1000/1234 (81%)
[INFO] Broadcast completed: 1,230 sent, 4 failed
```

---

### 6. `health_handler.py` - Health Check Endpoint

**Responsibilities**:
- HTTP server for monitoring bot health
- Runs on separate port (`HEALTH_PORT`, default: 8444)
- Integration with UptimeRobot and monitoring services
- Tracks execution of scheduled tasks

**Health Check Logic**:
Returns `healthy` status only if ALL conditions are met:
- Scraper ran within last 2 days
- Checker ran within last 2 days
- Cleanup ran within last 2 days

Returns `unhealthy` if ANY task is stale (>2 days) or never ran.

**Endpoint**: `GET /health`

**Response Format**:
```json
{
  "status": "healthy",
  "timestamp": "2024-11-18T14:30:00.123456",
  "stats": {
    "users": 150,
    "products_total": 245,
    "products_active": 180
  },
  "tasks": {
    "scraper": {
      "status": "ok",
      "last_run": "2024-11-18T09:00:00"
    },
    "checker": {
      "status": "ok",
      "last_run": "2024-11-18T10:00:00"
    },
    "cleanup": {
      "status": "ok",
      "last_run": "2024-11-18T02:00:00"
    }
  },
  "thresholds": {
    "max_days_since_last_run": 2
  }
}
```

**Task Status Values**:
- `ok`: Task ran within threshold (≤2 days)
- `stale`: Task didn't run for >2 days
- `never_run`: Task has never executed
- `error`: Invalid timestamp or other error

**System Status Tracking**:
Each scheduled task updates the database after execution:
```python
from datetime import datetime
import database

# After successful scraper run
await database.update_system_status("last_scraper_run", datetime.now().isoformat())

# After successful checker run
await database.update_system_status("last_checker_run", datetime.now().isoformat())

# After successful cleanup run
await database.update_system_status("last_cleanup_run", datetime.now().isoformat())
```

**Database Schema** (system_status table):
```sql
CREATE TABLE system_status (
    key TEXT PRIMARY KEY,              -- e.g., "last_scraper_run"
    value TEXT NOT NULL,               -- ISO timestamp
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Running Standalone**:
```bash
# Start health check server only (for testing)
uv run python health_handler.py
# Server runs on http://0.0.0.0:8444/health
```

**UptimeRobot Configuration**:
- Monitor Type: HTTP(s)
- URL: `https://your-domain.com:8444/health`
- Keyword: `"healthy"` (monitor looks for this in response)
- Interval: 5 minutes

**Integration with Bot**:
The health check server runs as a background thread in `bot.py`:
```python
from health_handler import start_health_server

# Start health server in background
start_health_server()  # Non-blocking, runs in daemon thread
```

---

### 7. `handlers/` - Command Handlers

Each command in a separate file for maintainability.

#### `/start`
Welcome message explaining the bot's purpose.

#### `/add`
**Conversational flow** (step-by-step):

The `/add` command now uses a conversational flow that guides users through adding a product in three steps:

**Step 1 - URL**:
- Bot asks: "Inviami il link del prodotto Amazon.it"
- User sends: `https://amazon.it/dp/B08N5WRWNW`
- Validation:
  - URL must be from amazon.it (not .com, .de, etc.)
  - ASIN must be extractable from URL
  - Marketplace must be "it"

**Step 2 - Price**:
- Bot asks: "Inviami il prezzo che hai pagato in euro"
- User sends: `59.90` or `59,90`
- Validation:
  - Must be a valid number (accepts both `.` and `,` as decimal separator)
  - Must be positive (> 0)
  - Max 16 digits total (including decimals)

**Step 3 - Deadline**:
- Bot asks: "Inviami la scadenza del reso"
- User can send either:
  - Number of days (1-365): `30` → 30 days from today
  - Date in format gg-mm-aaaa: `25-12-2024` → specific date
- Validation:
  - If number: must be between 1 and 365
  - If date: must be in format gg-mm-aaaa and in the future

**Canceling**:
- Users can type `/cancel` at any step to abort the conversation

**Note**: The optional `min_savings_threshold` parameter is not asked in the conversational flow (set to NULL by default). Users can update it later with `/update` if needed.

#### `/list`
Shows user's monitored products:
```
I tuoi prodotti monitorati:

1. 📦 [Nome Prodotto]
   Prezzo pagato: €59.90
   Scadenza: 15/12/2024
   Soglia: €5.00

2. 📦 [Altro Prodotto]
   ...
```

**Note**: Numbers 1, 2, 3... are **not** database IDs, but list indices.

#### `/delete <numero>`
**Example**: `/delete 2` removes the 2nd item from user's list.

#### `/update <numero> <campo> <valore>`
Allows updating price_paid, return_deadline, or min_savings_threshold.

**Example**:
```
/update 1 prezzo 55.00
/update 1 scadenza 2024-12-30
/update 1 soglia 10
```

#### `/feedback <messaggio>`
Stores user feedback in database for admin review.

---

## Logging Strategy

**Configuration**:
- Use `TimedRotatingFileHandler` with daily rotation
- Keep only last 3 days of logs (today + 2 previous days)
- Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Separate log files in `data/logs/`:
  - `bot.log` - Main bot operations
  - `scraper.log` - Scraping activities
  - `checker.log` - Price checks
  - `cleanup.log` - Cleanup operations

**Example Setup**:
```python
from logging.handlers import TimedRotatingFileHandler

handler = TimedRotatingFileHandler(
    filename='data/logs/bot.log',
    when='midnight',
    interval=1,
    backupCount=2  # Keep today + 2 previous days
)
```

**Log Levels**:
- `DEBUG`: Development details (use sparingly in production)
- `INFO`: Normal operations (scraping started, notifications sent)
- `WARNING`: Scraping failures, missing data
- `ERROR`: Database errors, critical failures
- `CRITICAL`: Bot cannot start

---

## Development Workflow

### Initial Setup
```bash
# Clone repository
git clone <repo-url>
cd repackit

# Install dependencies (dev mode)
uv sync --extra dev

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Setup pre-commit hooks
uv run pre-commit install

# Initialize database
uv run python -c "from bot import init_db; init_db()"
```

### Running Locally
```bash
# Start bot (requires webhook URL via tunnel)
uv run python bot.py

# Run individual components manually
uv run python data_reader.py
uv run python checker.py
uv run python product_cleanup.py

# Admin-only broadcast (manual execution for security)
uv run python broadcast.py "Your message here"
```

### Code Quality Checks
```bash
# Format code
uv run black .

# Lint code
uv run ruff check --fix .

# Run tests with coverage
uv run pytest --cov=. --cov-report=html

# Check coverage threshold
uv run pytest --cov=. --cov-fail-under=80
```

### Git Workflow
```bash
# Pre-commit hooks run automatically on commit
git add .
git commit -m "feat: add product monitoring"

# Hooks will run black + ruff automatically
# If checks fail, fix issues and commit again
```

---

## Production Deployment (Docker)

### Build & Run
```bash
# Build image
docker-compose build

# Start container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down
```

### Dockerfile Strategy
```dockerfile
# Multi-stage build for minimal size
FROM python:3.11-slim AS builder
# Install uv and dependencies

FROM python:3.11-slim AS runtime
# Copy only necessary files
# Install Playwright browsers
# Run as non-root user
```

### Volume Persistence
```yaml
volumes:
  - ./data:/app/data  # Database + logs persist across restarts
```

---

## CI/CD Pipelines (GitHub Actions)

### 1. `test.yml` - Unit Tests
- Runs on every push/PR
- Executes `pytest --cov=. --cov-fail-under=80`
- Uploads coverage to SonarCloud

### 2. `lint.yml` - Code Quality
- Runs `black --check .`
- Runs `ruff check .`
- Fails if code isn't formatted

### 3. `docker.yml` - Container Build
- Builds Docker image
- Pushes to registry on main branch

### 4. SonarCloud Integration
- Enforces ≥80% code coverage
- Detects code smells, bugs, vulnerabilities
- Configured via `sonar-project.properties`

---

## Testing Strategy

### Test Structure
Mirror the source structure in `tests/`:
```
tests/
├── test_bot.py
├── test_data_reader.py
├── test_checker.py
├── test_product_cleanup.py
├── test_broadcast.py
└── handlers/
    ├── test_start.py
    ├── test_add.py
    └── ...
```

### Testing Principles
1. **Unit Tests**: Test each function in isolation
2. **Mocking**: Mock external dependencies (Telegram API, Playwright, database)
3. **Coverage**: Every new feature must include tests
4. **Fixtures**: Use pytest fixtures for common setups (db, bot instance)

### Example Test
```python
@pytest.mark.asyncio
async def test_add_product_valid_input(mock_db):
    """Test /add with valid ASIN and price."""
    result = await add_product(
        user_id=123,
        url="https://amazon.it/dp/B08N5WRWNW",
        price=59.90,
        days=30,
        threshold=5
    )
    assert result.success == True
    assert mock_db.products.count() == 1
```

### Running Tests
```bash
# All tests
uv run pytest

# With coverage report
uv run pytest --cov=. --cov-report=html
open htmlcov/index.html

# Specific test file
uv run pytest tests/test_data_reader.py

# Verbose output
uv run pytest -v
```

---

## Amazon Scraping Details

### ASIN Extraction Patterns
```python
# Supported URL formats:
# - https://www.amazon.it/dp/B08N5WRWNW
# - https://amazon.it/gp/product/B08N5WRWNW/ref=...
# - https://www.amazon.it/Product-Name/dp/B08N5WRWNW/...
# - https://amzn.eu/d/B08N5WRWNW (short link)

# Regex: r'/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})'
```

### Affiliate URL Construction
When sending product links to users, always construct clean URLs with the affiliate tag:
```python
def build_affiliate_url(asin: str, marketplace: str = "it") -> str:
    """
    Build Amazon affiliate URL from ASIN.

    Args:
        asin: Amazon Standard Identification Number (10 chars)
        marketplace: Country code (it, com, de, fr, etc.)

    Returns:
        Clean affiliate URL: https://amazon.{marketplace}/dp/{asin}?tag={tag}
    """
    return f"https://amazon.{marketplace}/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
```

**Important Notes**:
- Always use clean `/dp/{ASIN}` format (not `/gp/product/` or complex URLs)
- Affiliate tag is the **only** query parameter needed
- Works across all Amazon marketplaces (.it, .com, .de, etc.)
- URL is short and user-friendly for Telegram messages

### Price Scraping Selectors
Amazon's HTML structure (subject to change):
```python
# Primary selectors (try in order):
PRICE_SELECTORS = [
    '.a-price .a-offscreen',          # Most common
    '#priceblock_ourprice',           # Legacy
    '#priceblock_dealprice',          # Deal price
    '.a-price-whole',                 # Separated integer part
]
```

### Anti-Bot Measures
1. **User-Agent Rotation**: Randomize browser fingerprint
2. **Rate Limiting**: 1-2s delay between requests
3. **Error Handling**: Graceful degradation if blocked
4. **Future**: Proxy rotation if needed

### Playwright Configuration
```python
browser = await p.chromium.launch(
    headless=True,
    args=['--no-sandbox', '--disable-dev-shm-usage']  # Docker compatibility
)
```

---

## Future Enhancements

### Phase 1 (Current)
- [x] Basic product monitoring (ASIN, price, deadline)
- [x] Daily scraping + notifications
- [x] User commands (add, list, delete, update)
- [x] Cleanup of expired products

### Phase 2 (Planned)
- [ ] Multi-marketplace support (.com, .de, .fr, .es, .uk)
- [ ] Amazon Affiliate API integration (avoid scraping)
- [ ] Price history graphs (optional, requires storage)
- [ ] User preferences (notification time, language)

### Phase 3 (Ideas)
- [ ] Multi-language support (EN, DE, FR, ES)
- [ ] Price prediction ML model
- [ ] Browser extension for easier product addition
- [ ] Notification via email/push (in addition to Telegram)

---

## Troubleshooting

### Bot Not Receiving Messages
1. Check `WEBHOOK_URL` is publicly accessible (HTTPS required)
2. Verify webhook is set: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Check logs: `docker-compose logs -f` or `tail -f data/logs/bot.log`

### Scraping Failures
1. Check if Amazon changed HTML structure (update selectors)
2. Verify Playwright browsers installed: `uv run playwright install chromium`
3. Test manually: `uv run python data_reader.py`

### Database Locked Errors
SQLite doesn't support high concurrency. If errors occur:
1. Ensure only one bot instance is running
2. Check file permissions on `data/users.db`
3. Consider WAL mode: `PRAGMA journal_mode=WAL;`

### Coverage Below 80%
1. Run `pytest --cov=. --cov-report=html`
2. Open `htmlcov/index.html` to see uncovered lines
3. Add tests for missing cases
4. Mock external dependencies properly

---

## Code Style Guidelines

### Imports
```python
# Standard library
import asyncio
from datetime import datetime, timedelta

# Third-party
from telegram import Update
from telegram.ext import ContextTypes

# Local
from handlers.start import start_handler
```

### Naming Conventions
- **Functions**: `snake_case` (e.g., `extract_asin`, `send_notification`)
- **Classes**: `PascalCase` (e.g., `ProductDatabase`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `SCRAPER_HOUR`, `DATABASE_PATH`)
- **Private**: Prefix with `_` (e.g., `_calculate_sleep_duration`)

### Type Hints
Always use type hints for function signatures:
```python
async def extract_asin(url: str) -> tuple[str, str]:
    """Returns (asin, marketplace)."""
    ...

def calculate_savings(price_paid: float, current_price: float) -> float:
    """Returns savings amount."""
    return price_paid - current_price
```

### Docstrings
Use Google-style docstrings:
```python
def parse_deadline(user_input: str, purchase_date: datetime) -> datetime:
    """
    Parses return deadline from user input.

    Args:
        user_input: Either "30" (days) or "2024-12-25" (date)
        purchase_date: Date of original purchase

    Returns:
        Deadline as datetime object

    Raises:
        ValueError: If input format is invalid
    """
```

### Error Handling
```python
try:
    price = await scrape_price(asin)
except PlaywrightError as e:
    logger.warning(f"Scraping failed for {asin}: {e}")
    return None  # Skip and retry tomorrow
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

---

## Dependency Management (pyproject.toml)

```toml
[project]
name = "repackit"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "python-telegram-bot[webhooks]>=20.0",
    "playwright>=1.40",
    "aiosqlite>=0.19",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.1",
    "black>=23.0",
    "ruff>=0.1",
    "pre-commit>=3.5",
]

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]  # Line too long (handled by black)

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## Security Considerations

1. **Environment Variables**: Never commit `.env` to git
2. **Webhook Secret**: Use strong random token for `WEBHOOK_SECRET`
3. **Admin Commands**: Verify `user_id == ADMIN_USER_ID` before execution
4. **SQL Injection**: Use parameterized queries (SQLite's `?` placeholders)
5. **User Input**: Validate all user inputs (URLs, prices, dates)
6. **Docker**: Run as non-root user, minimal attack surface

---

## Performance Optimization

### Database
- Add indexes on frequently queried columns:
  ```sql
  CREATE INDEX idx_user_products ON products(user_id);
  CREATE INDEX idx_return_deadline ON products(return_deadline);
  ```

### Scraping
- Use connection pooling for Playwright
- Concurrent scraping with `asyncio.gather()` + semaphore
- Cache ASIN → product name mappings (optional)

### Memory
- Limit concurrent scraping tasks (e.g., max 10 simultaneous)
- Close Playwright browser after batch completion
- Use streaming for large datasets

---

## Support & Contribution

### Reporting Issues
Create detailed bug reports with:
- Steps to reproduce
- Expected vs actual behavior
- Log excerpts (sanitize sensitive data)
- Environment (Docker/local, OS, Python version)

### Pull Request Process
1. Fork repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Write tests for new functionality
4. Ensure coverage ≥80%
5. Run linters: `black` + `ruff`
6. Submit PR with clear description

### Code Review Checklist
- [ ] Tests pass (`pytest`)
- [ ] Coverage ≥80% (`pytest --cov`)
- [ ] Linting passes (`black --check` + `ruff check`)
- [ ] Docstrings for public functions
- [ ] Type hints on function signatures
- [ ] Logs use appropriate levels
- [ ] No hardcoded secrets

---

## Frequently Asked Questions

**Q: Can I use pip instead of uv?**
A: No, the project is standardized on `uv` for faster dependency resolution and better reproducibility.

**Q: Why webhook-only and no polling?**
A: Webhooks are production-ready, more efficient, and required for scalability. Polling is unsuitable for production bots.

**Q: How do I test webhook locally?**
A: Use Cloudflare Tunnel, ngrok, or similar to expose localhost. Update `WEBHOOK_URL` in `.env`.

**Q: What if Amazon blocks scraping?**
A: Implement user-agent rotation, proxy rotation, or migrate to Amazon Affiliate API (future phase).

**Q: How many users can this handle?**
A: Current architecture: ~1000-5000 users comfortably. For more, migrate to PostgreSQL and horizontal scaling.

**Q: Can I run multiple bot instances?**
A: No, SQLite doesn't support concurrent writes. Use single instance or migrate to PostgreSQL for multi-instance setups.

---

## Contact & Resources

- **Repository**: https://github.com/dstmrk/repackit
- **Reference Project**: https://github.com/dstmrk/octotracker
- **Telegram Bot API**: https://core.telegram.org/bots/api
- **python-telegram-bot Docs**: https://docs.python-telegram-bot.org/
- **Playwright Docs**: https://playwright.dev/python/

---

**Last Updated**: 2024-11-18
**Maintained By**: @dstmrk

---

*This document is the single source of truth for RepackIt development. Update it whenever architectural decisions change.*
