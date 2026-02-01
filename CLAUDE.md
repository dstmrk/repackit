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
- **Amazon Price Data**: Amazon Creator API (OAuth 2.0)
- **Database**: SQLite
- **Code Quality**: Ruff (formatter + linter)
- **Testing**: pytest with ≥80% coverage
- **CI/CD**: SonarCloud integration
- **Containerization**: Docker with multi-stage builds

---

## Project Structure

```
repackit/
├── bot.py                    # Main bot with webhook + scheduler
├── amazon_api.py             # Amazon Creator API client (OAuth + GetItems)
├── data_reader.py            # Amazon price fetcher (via Creator API)
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
├── utils/                    # Utility modules
│   ├── keyboards.py          # Inline keyboard builders
│   ├── logging_config.py     # Shared logging configuration
│   └── retry.py              # Retry with exponential backoff
├── tests/                    # Unit tests mirroring src structure
│   ├── test_bot.py
│   ├── test_data_reader.py
│   ├── test_checker.py
│   ├── test_product_cleanup.py
│   ├── test_broadcast.py
│   ├── utils/                # Utility tests
│   │   └── test_retry.py
│   └── handlers/
│       ├── test_start.py
│       └── ...
├── data/                     # Persistent data (mounted volume)
│   ├── repackit.db
│   ├── repackit.log
│   └── broadcast.log
├── .env                      # Environment variables (gitignored)
├── .env.example              # Template for .env
├── pyproject.toml            # uv dependencies + tool config
├── Dockerfile                # Multi-stage build
├── docker-compose.yml        # Production orchestration
├── .github/workflows/        # CI/CD pipelines
│   ├── ci.yml                # Unified lint + test workflow
│   └── docker.yml
├── .pre-commit-config.yaml   # Local git hooks
└── CLAUDE.md                 # This file
```

---

## Database Schema

### `users` Table
```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,                   -- Telegram user ID
    language_code TEXT,                             -- Auto-detected from Telegram (e.g., "it")
    max_products INTEGER DEFAULT NULL,              -- Product slot limit (NULL = admin with 21 slots)
    referred_by INTEGER DEFAULT NULL,               -- User ID of referrer (for referral system)
    referral_bonus_given BOOLEAN DEFAULT FALSE,     -- Tracks if inviter received bonus
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
- `feedback.created_at` is used for rate limiting: users can submit one feedback every 24 hours (see `/feedback` handler).
- **Referral System**:
  - `max_products`: User's slot limit (3-21). NULL = admin with 21 slots.
  - `referred_by`: Stores referrer's user_id. NULL if no referral.
  - `referral_bonus_given`: Prevents duplicate bonuses. Set TRUE after inviter receives +3 slots.

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
DATABASE_PATH=./data/repackit.db

# Scheduler (24-hour format, e.g., 9 = 09:00)
SCRAPER_HOUR=9         # Daily scraping time
CHECKER_HOUR=10        # Daily price check time
CLEANUP_HOUR=2         # Daily cleanup time (removes expired products)

# Admin
ADMIN_USER_ID=123456789  # Telegram user ID for broadcast.py script verification

# Amazon Affiliate
AMAZON_AFFILIATE_TAG=yourtag-21  # Amazon affiliate tag for monetization

# Amazon Creator API
AMAZON_CLIENT_ID=your-client-id          # Credential Id from Creator API CSV
AMAZON_CLIENT_SECRET=your-client-secret  # Secret from Creator API CSV
AMAZON_CREDENTIAL_VERSION=2.2            # 2.1=NA, 2.2=EU, 2.3=FE

# Product Limits & Referral System
DEFAULT_MAX_PRODUCTS=21       # Max cap for all users
INITIAL_MAX_PRODUCTS=3        # Slots for new users (no referral)
PRODUCTS_PER_REFERRAL=3       # Bonus for inviter when invitee adds first product
INVITED_USER_BONUS=3          # Extra slots for invited user at registration

# Telegram Rate Limiting
TELEGRAM_MESSAGES_PER_SECOND=30  # Telegram API hard limit (30 messages/second)
BATCH_SIZE=10                    # Batch size for notifications and broadcasts
DELAY_BETWEEN_BATCHES=1.0        # Delay in seconds between batches

# Retry Settings (exponential backoff)
TELEGRAM_MAX_RETRIES=3           # Max retry attempts for transient errors
TELEGRAM_RETRY_BASE_DELAY=1.0    # Base delay in seconds (doubles each retry)

# Logging
LOG_LEVEL=INFO         # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Development Setup**:
- Use Cloudflare Tunnel or ngrok for `WEBHOOK_URL` during local development
- Keep `.env` gitignored, commit `.env.example` instead

**Configuration Management**:
All environment variables are centralized in `config.py` using a dataclass for type-safety and validation. Rate limiting settings can be adjusted via environment variables without code changes.

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

### 2. `amazon_api.py` - Amazon Creator API Client

**Responsibilities**:
- OAuth 2.0 token management (Cognito) with automatic caching and refresh
- Batch product lookups via GetItems API (max 10 ASINs per request)
- Price extraction from `offersV2` response (prefers BuyBox winner)

**Authentication**:
- Uses client credentials flow (client_id + client_secret)
- Tokens cached for 1 hour (with 60s refresh buffer)
- Regional endpoints: NA (2.1), EU (2.2), FE (2.3)

**Key Class: `AmazonCreatorAPI`**:
```python
api = get_api_client()  # Singleton
prices = await api.get_items(["B08N5WRWNW", "B09B2SBHQK"], marketplace="it")
# Returns: {"B08N5WRWNW": 59.49, "B09B2SBHQK": 45.00}
```

**Price Extraction Logic**:
1. Look for BuyBox winner listing (`isBuyBoxWinner: true`)
2. Fallback to first listing with a price
3. Extract `offersV2.listings[].price.money.amount`

---

### 3. `data_reader.py` - Amazon Price Fetcher

**Responsibilities**:
- Parse ASIN from Amazon URLs (supports multiple formats)
- Fetch current prices via Creator API (through `amazon_api.py`)
- Deduplicate API calls (same ASIN across multiple users = 1 API call)

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
```

**API Strategy**:
- **Batch Requests**: Groups ASINs by marketplace, sends batched API calls (max 10/request)
- **Deduplication**: If 10 users monitor the same ASIN, it's fetched only once
- **Error Handling**: Skip failed fetches, log as WARNING, retry next day

**Can Run Standalone**:
```bash
uv run python data_reader.py                    # Fetch all products from DB
uv run python data_reader.py B08N5WRWNW         # Fetch single ASIN (amazon.it)
uv run python data_reader.py B08N5WRWNW de      # Fetch single ASIN (amazon.de)
```

---

### 4. `checker.py` - Price Comparison & Notifications

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

**Message Format** (HTML):
```
🎉 Prezzo in calo su Amazon!

📦 iPhone 15 Pro

Prezzo attuale: €45.99
Prezzo pagato: €59.90
💰 Risparmio: €13.91

📅 Scadenza reso: 15/12/2024 (tra 12 giorni)

🔗 Vai al prodotto

[📢 Dillo a un amico]  ← Inline button
```

**Affiliate URL Construction**:
All product URLs sent to users include the `AMAZON_AFFILIATE_TAG` for monetization:
```python
# Format: https://amazon.it/dp/{ASIN}?tag={AFFILIATE_TAG}
url = f"https://amazon.it/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
```

**Viral Growth Strategy: "Momento di Gloria"**:

The notification includes a share button that leverages the user's peak satisfaction moment. When users receive a price drop alert, they're most motivated to share the bot with friends.

**Implementation**:
- **Share Button**: Inline keyboard button "📢 Dillo a un amico" below notification
- **Pre-filled Message**: Uses Telegram's native share API with personalized text:
  ```
  🎉 Ho appena risparmiato €13.91 su Amazon grazie a @repackit_bot!
  Monitora i tuoi acquisti e ti avvisa se il prezzo scende. Provalo!
  ```
- **Timing**: Appears only on price drop notifications (when user is happiest)
- **Non-intrusive**: Optional button, doesn't interrupt the main message

**Technical Details**:
```python
# Build share URL with pre-filled message
share_text = (
    f"🎉 Ho appena risparmiato €{savings:.2f} su Amazon grazie a @repackit_bot! "
    "Monitora i tuoi acquisti e ti avvisa se il prezzo scende. Provalo!"
)
share_url = f"https://t.me/share/url?url=https://t.me/repackit_bot&text={quote_plus(share_text)}"

# Add inline button to notification
keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📢 Dillo a un amico", url=share_url)]
])
```

**Why This Works**:
- **Emotional Timing**: Users feel smart/successful when they save money
- **Social Proof**: Real savings amount creates credibility ("€13.91 saved!")
- **Low Friction**: One tap to share via any Telegram chat
- **Natural Word-of-Mouth**: Users genuinely want to help friends save money

**Can Run Standalone**:
```bash
uv run python checker.py  # Manual check execution
```

---

### 5. `product_cleanup.py` - Expired Product Removal

**Responsibilities**:
- Run daily at `CLEANUP_HOUR` (default: 02:00)
- Delete products where `return_deadline < today`
- Log cleanup operations

**Can Run Standalone**:
```bash
uv run python product_cleanup.py  # Manual cleanup
```

---

### 6. `broadcast.py` - Admin Broadcast Script

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

### 7. `health_handler.py` - Health Check Endpoint

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

### 8. `handlers/` - Command Handlers

Each command in a separate file for maintainability.

#### `/start`
Welcome message explaining the bot's purpose.

#### `/help`
Shows all available commands with descriptions and explains how the bot works.

**Message includes**:
- List of all commands organized by category:
  - Gestione prodotti: `/add`, `/list`, `/delete`, `/update`
  - Invita amici: `/share`
  - Informazioni e supporto: `/start`, `/help`, `/feedback`
- Brief explanation of how the bot works (4-step process)
- Automatic monitoring reminder
- Hint about inviting friends with `/share` to earn more product slots

**Benefits**:
- Helps new users discover all features
- Quick reference for command syntax
- Explains the bot's purpose and workflow
- Promotes referral system awareness

#### `/share`
Shows user's referral link and explains the referral system for earning more product slots.

**Message includes**:
- User's current slot count (e.g., "6/21")
- Personal referral link: `https://t.me/repackit_bot?start=USER_ID`
- How the system works:
  1. Share personal link
  2. Friend receives 6 slots (instead of 3)
  3. When friend adds first product, inviter gets +3 slots
- Maximum cap (21 slots)
- Inline share button with pre-filled message

**Benefits**:
- Makes referral system discoverable
- Provides easy-to-share link
- Explains mutual benefits clearly
- Encourages active invitations

#### `/add`
**Conversational flow** (step-by-step):

The `/add` command uses a conversational flow that guides users through adding a product in five steps:

**Step 1 - Product Name**:
- Bot asks: "Come vuoi chiamare questo prodotto?"
- User sends: `iPhone 15 Pro` or `Cuffie Sony`
- Validation:
  - Must be between 3 and 100 characters
  - Used to identify the product in lists and notifications

**Step 2 - URL**:
- Bot asks: "Inviami il link del prodotto Amazon.it"
- User sends: `https://amazon.it/dp/B08N5WRWNW`
- Validation:
  - URL must be from amazon.it (not .com, .de, etc.)
  - ASIN must be extractable from URL
  - Marketplace must be "it"

**Step 3 - Price**:
- Bot asks: "Inviami il prezzo che hai pagato in euro"
- User sends: `59.90` or `59,90`
- Validation:
  - Must be a valid number (accepts both `.` and `,` as decimal separator)
  - Must be positive (> 0)
  - Max 16 digits total (including decimals)

**Step 4 - Deadline**:
- Bot asks: "Inviami la scadenza del reso"
- User can send either:
  - Number of days (1-365): `30` → 30 days from today
  - Date in format gg-mm-aaaa: `09-05-2025` → specific date
- Validation:
  - If number: must be between 1 and 365
  - If date: must be in format gg-mm-aaaa and in the future

**Step 5 - Minimum Savings**:
- Bot asks: "Qual è il risparmio minimo per cui vuoi essere notificato?"
- User sends: `5` (for €5.00) or `0` (for any price drop)
- Validation:
  - Must be a non-negative number
  - Must be less than the price paid
  - Setting to 0 means notify for any price reduction

**Canceling**:
- Users can type `/cancel` at any step to abort the conversation

**Product Limit**:
- Users have dynamic slot limits (3-21 slots) based on referrals
- When limit is reached, bot shows clear error message with suggestion to use `/delete`
- Prevents abuse and ensures system scalability

**Contextual /share Hint**:
After successfully adding a product, if user has <3 slots available and <21 total:
- Shows separate message with current slot count
- Suggests using `/share` to invite friends and earn more slots
- Example: "Hai 5/6 prodotti monitorati. 💡 Suggerimento: Stai esaurendo gli slot! Usa /share per invitare amici e guadagnare più spazio."
- Perfect timing: user just consumed a slot → immediate awareness

#### `/list`
Shows user's monitored products:
```
I tuoi prodotti monitorati:

1. 📦 [iPhone 15 Pro]
   💰 Prezzo pagato: €59.90
   📅 Scadenza reso: 09/05/2025 (tra 170 giorni)
   🎯 Risparmio minimo: €5.00

2. 📦 [Cuffie Sony]
   💰 Prezzo pagato: €45.00
   📅 Scadenza reso: 15/05/2025 (tra 176 giorni)

Hai 5/21 prodotti monitorati.
Usa /delete per rimuoverne uno, /update per modificarne uno.
```

**Features**:
- Shows product name (user-defined) for easy identification
- Shows product count vs. limit (e.g., "5/21 prodotti monitorati")
- Shows minimum savings threshold only if > 0
- Provides quick command references for delete and update actions
- Numbers 1, 2, 3... are **not** database IDs, but list indices for easy reference

**Contextual /share Hint**:
If user has <3 slots available and <21 total:
- Shows inline hint after product list
- Message: "💡 Suggerimento: Stai esaurendo gli slot! Usa /share per invitare amici e guadagnare più spazio."
- Smart targeting: only shows to users who can benefit (not at max)
- Contextual timing: user checks products → sees problem → immediate solution

#### `/delete`
**Button-based selection with confirmation**:

The `/delete` command uses inline keyboard buttons for product selection and confirmation to prevent accidental deletions.

**Flow**:
1. User sends: `/delete`
2. Bot shows list of products with inline buttons:
   ```
   🗑️ Elimina un prodotto

   Seleziona il prodotto che vuoi rimuovere dal monitoraggio:

   [1. iPhone 15 Pro - €59.90]
   [2. Cuffie Sony - €45.00]
   [❌ Annulla]
   ```
3. User clicks a product button
4. Bot shows product details with confirmation buttons:
   ```
   ⚠️ Sei sicuro di voler eliminare questo prodotto?

   📦 iPhone 15 Pro
   🔖 ASIN: B08N5WRWNW
   💰 Prezzo pagato: €59.90
   📅 Scadenza reso: 09/05/2025
   🎯 Risparmio minimo: €5.00

   [✅ Sì, elimina] [❌ No, annulla]
   ```
5. User clicks one of the buttons:
   - **Sì, elimina**: Product is deleted permanently
   - **No, annulla**: Operation is canceled, product remains

**Benefits**:
- No need to remember product numbers
- Visual list makes selection easier
- Prevents accidental deletions with confirmation step
- Shows product details (including name) before confirming
- Modern UX with inline buttons

#### `/update`
**Conversational flow with inline buttons**:

The `/update` command uses a conversational flow that guides users through updating product information with interactive buttons.

**Flow**:
1. User sends: `/update`
2. Bot shows list of products with inline buttons:
   ```
   🔄 Aggiorna un prodotto

   Seleziona il prodotto che vuoi modificare:

   [1. iPhone 15 Pro - €59.90]
   [2. Cuffie Sony - €45.00]
   [❌ Annulla]
   ```
3. User clicks a product button
4. Bot shows field options with inline buttons:
   ```
   📦 Prodotto selezionato: iPhone 15 Pro

   Cosa vuoi modificare?

   [📦 Nome prodotto]
   [💰 Prezzo pagato]
   [📅 Scadenza reso]
   [🎯 Risparmio minimo]
   [❌ Annulla]
   ```
5. User clicks a field button (e.g., "Prezzo pagato")
6. Bot asks for new value with validation instructions:
   ```
   💰 Aggiorna prezzo pagato

   Inviami il nuovo prezzo in euro.

   Esempio: 59.90 oppure 59,90

   Oppure scrivi /cancel per annullare.
   ```
7. User sends new value (e.g., `55.00`)
8. Bot validates and updates, then shows confirmation:
   ```
   ✅ Prezzo aggiornato con successo!

   📦 iPhone 15 Pro
   💰 Nuovo prezzo: €55.00
   ```

**Validation Rules**:
- **Nome prodotto**: Must be between 3 and 100 characters
- **Prezzo**: Must be a positive number (supports both `.` and `,` as decimal separator)
- **Scadenza**: Accepts either:
  - Number of days (1-365): `30` → 30 days from today
  - Date in format gg-mm-aaaa: `09-05-2025` → specific date
  - Must be in the future
- **Risparmio minimo**: Must be a non-negative number less than the price paid

**Canceling**:
- Users can click "Annulla" button at any step
- Users can type `/cancel` when entering new value

**Benefits**:
- Intuitive product selection with visual list (shows product name)
- Can update product name for better identification
- Clear field options with emoji icons
- Step-by-step validation with helpful examples
- No need to remember command syntax

#### `/feedback`
**Conversational flow with validation and confirmation**:

The `/feedback` command uses a conversational flow to collect user feedback with validation and preview confirmation.

**Flow**:
1. User sends: `/feedback`
2. Bot asks: "Scrivi il tuo feedback, suggerimento o segnalazione di bug"
3. User writes feedback message
4. Bot validates length:
   - Minimum: 10 characters (prevents spam like "ok", "test")
   - Maximum: 1000 characters (keeps feedback manageable)
5. Bot shows preview with confirmation buttons:
   ```
   📝 Anteprima del tuo feedback:

   [Feedback text or truncated preview...]

   Lunghezza: 45 caratteri

   Vuoi inviare questo feedback?

   [✅ Sì, invia] [❌ No, annulla]
   ```
6. User clicks confirm → feedback saved to database
7. Bot shows thank you message

**Validation Rules**:
- **Min length**: 10 characters (prevents trivial feedback)
- **Max length**: 1000 characters (prevents abuse)
- **Whitespace**: Leading/trailing spaces automatically stripped
- **Characters**: Supports emojis and special characters

**Rate Limiting** (Anti-Spam):
- Users can submit **one feedback every 24 hours**
- If user tries to submit again within 24 hours, bot shows:
  - Time remaining until next feedback allowed (in hours or minutes)
  - Friendly message explaining the rate limit
- Rate limit resets exactly 24 hours after last submission
- Implementation: `FEEDBACK_RATE_LIMIT_HOURS = 24` in `handlers/feedback.py`
- Database function: `database.get_last_feedback_time(user_id)` checks `created_at` timestamp
- **Fail-open design**: If timestamp parsing fails, allow feedback (prevents blocking legitimate users)

**Preview Features**:
- Shows first 200 characters for long feedback
- Displays total character count
- Inline keyboard for easy confirmation/cancellation

**Canceling**:
- Users can click "Annulla" button
- Users can type `/cancel` when writing feedback

**Benefits**:
- Prevents accidental submissions with confirmation step
- Clear validation with helpful error messages
- Visual preview ensures users see what they're sending
- Better quality feedback with length requirements

---

## Referral System ("Dropbox Strategy")

RepackIt implements a gamified referral system inspired by Dropbox's successful growth strategy. Users are incentivized to invite friends through product slot rewards.

### System Overview

**Core Concept**: Users start with limited product slots and unlock more by inviting friends who actively use the bot.

**Slot Allocation**:
- **New user (no referral)**: 3 slots
- **Invited user**: 6 slots (3 base + 3 bonus)
- **Inviter reward**: +3 slots when invitee adds first product
- **Maximum cap**: 21 slots for all users

**Progression Example**:
- User A starts: 3 slots
- User A invites User B: User B gets 6 slots immediately
- User B adds first product: User A gets +3 (now 6 slots)
- User A invites User C: User C gets 6 slots
- User C adds first product: User A gets +3 (now 9 slots)
- ...and so on until User A reaches 21 slots

### Database Schema

The referral system adds two fields to the `users` table:

```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    language_code TEXT,
    max_products INTEGER DEFAULT NULL,
    referred_by INTEGER DEFAULT NULL,              -- User ID of referrer
    referral_bonus_given BOOLEAN DEFAULT FALSE,    -- Prevents duplicate bonuses
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Fields**:
- `referred_by`: Stores the referrer's user_id (NULL if no referral)
- `referral_bonus_given`: Tracks if the inviter has received their bonus (prevents abuse)

### Referral Flow

#### 1. Sharing Referral Link

Users share a deep link with their Telegram user ID:
```
https://t.me/repackit_bot?start=123456789
```

The link is simple and uses Telegram's native deep linking (`/start` parameter).

#### 2. New User Registration (`/start` handler)

When a new user clicks a referral link:

```python
# Parse referral code from /start parameter
if context.args:
    referral_code = context.args[0]  # "123456789"

    # Validate: must be positive integer, not self-referral
    if referral_code.isdigit():
        referrer_id = int(referral_code)
        if referrer_id > 0 and referrer_id != user_id:
            # Verify referrer exists in database
            referrer = await database.get_user(referrer_id)
            if referrer:
                referred_by = referrer_id
                # New user gets 6 slots (3 base + 3 bonus)
                await database.set_user_max_products(user_id, 6)
```

**New User Experience**:
- Welcome message includes: "🎁 **Hai ricevuto 3 slot bonus** per essere stato invitato! Hai 6 slot disponibili."
- If referral code is invalid: "ℹ️ Il codice di invito che hai usato non è valido (l'invitante non risulta esistente)."

#### 3. First Product Addition (`/add` handler)

When the invited user adds their **first product**, the inviter receives their reward:

```python
# After adding product
user_products = await database.get_user_products(user_id)
if len(user_products) == 1:  # First product!
    user = await database.get_user(user_id)

    # Check if user has referrer and bonus not yet given
    if user["referred_by"] and not user["referral_bonus_given"]:
        referrer_id = user["referred_by"]
        current_limit = await database.get_user_product_limit(referrer_id)

        # Only give bonus if referrer is not already at cap (21)
        if current_limit < 21:
            new_limit = await database.increment_user_product_limit(referrer_id, 3)

            # Mark bonus as given (prevents duplicates)
            await database.mark_referral_bonus_given(user_id)

            # Notify referrer
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 Un amico che hai invitato ha aggiunto il suo primo prodotto!\n"
                     f"💎 Hai ricevuto +3 slot (ora ne hai {new_limit}/21)"
            )
```

**Why "First Product" Trigger?**:
- **Anti-spam**: Prevents fake account creation (users must actually use the bot)
- **Quality signaling**: Inviter only gets rewarded for active users
- **User engagement**: Encourages invitees to try the bot immediately

### Corner Cases Handled

#### 1. Duplicate Bonus Prevention
**Problem**: User adds product → deletes → re-adds → inviter gets double bonus?
**Solution**: `referral_bonus_given` flag. Once set to TRUE, bonus is never given again.

```python
if not user["referral_bonus_given"]:
    # Give bonus
    await database.mark_referral_bonus_given(user_id)
```

#### 2. Inviter Already at Cap
**Problem**: Inviter has 21 slots. Should we notify them?
**Solution**: No notification, but mark bonus as given to prevent future checks.

```python
if current_limit < 21:
    # Give bonus and notify
else:
    # Just mark as given (no notification)
    await database.mark_referral_bonus_given(user_id)
```

#### 3. Invalid Referral Code
**Problem**: User uses malformed link (`?start=abc`) or non-existent referrer
**Solution**: Validate format (must be digits) and check referrer exists. Show transparent error.

```python
if not referral_code.isdigit():
    logger.warning(f"Malformed referral code: {referral_code}")
    # Continue registration without referral

referrer = await database.get_user(referrer_id)
if not referrer:
    # Show: "Il codice di invito non è valido"
    referred_by = None  # Continue as regular user
```

#### 4. Self-Referral
**Problem**: User tries to invite themselves
**Solution**: Silently ignore (no error message, no bonus).

```python
if referrer_id == user_id:
    logger.warning(f"User {user_id} attempted self-referral")
    # Continue as regular user, no referral tracking
```

#### 5. Existing User Clicks Referral Link
**Problem**: Registered user clicks referral link again
**Solution**: Ignore referral parameter for existing users.

```python
existing_user = await database.get_user(user_id)
if existing_user:
    # Don't overwrite referred_by, just show welcome message
```

#### 6. Referrer Deleted from Database
**Problem**: Invitee's `referred_by` points to deleted user
**Solution**: Check if referrer exists before incrementing.

```python
referrer = await database.get_user(referrer_id)
if not referrer:
    logger.warning(f"Referrer {referrer_id} not found")
    # Mark bonus as given anyway (prevents future retries)
```

#### 7. Notification Failure
**Problem**: Bot blocked by referrer or network error
**Solution**: Catch exception, log warning, but don't block product addition.

```python
try:
    await context.bot.send_message(referrer_id, notification_text)
except Exception as e:
    logger.warning(f"Could not notify referrer {referrer_id}: {e}")
    # Product addition still succeeds
```

### Configuration

Environment variables in `.env`:

```bash
# Product Limits & Referral System
DEFAULT_MAX_PRODUCTS=21       # Max cap for all users
INITIAL_MAX_PRODUCTS=3        # Slots for new users (no referral)
PRODUCTS_PER_REFERRAL=3       # Bonus for inviter when invitee adds first product
INVITED_USER_BONUS=3          # Extra slots for invited user at registration
```

**Clean Multiples of 3**:
- 3 → 6 → 9 → 12 → 15 → 18 → 21
- Makes progression intuitive and "round" numbers

### Anti-Abuse Measures

1. **Database Flag**: `referral_bonus_given` prevents double bonuses
2. **Self-Referral Detection**: `referrer_id == user_id` check
3. **Referrer Validation**: Verify referrer exists in database
4. **First Product Requirement**: Must actually use the bot (not just register)
5. **Cap Enforcement**: All users limited to 21 slots (prevents infinite growth)
6. **Existing User Check**: Referral only applies to new registrations

### Database Functions

```python
# Increment user's product limit (capped at 21)
new_limit = await database.increment_user_product_limit(user_id, 3)

# Mark that referral bonus has been given
await database.mark_referral_bonus_given(user_id)

# Add user with referral
await database.add_user(user_id, language_code, referred_by=referrer_id)
```

### Why This Works

**Psychological Triggers**:
- **Scarcity**: Limited slots create perceived value
- **Achievement**: Unlocking slots feels like progression
- **Reciprocity**: Invited users want to help their referrer
- **Social Proof**: "My friend uses this and got value"

**Compared to Alternatives**:
- **vs. Unlimited slots**: Creates no urgency to invite
- **vs. Paid slots**: Reduces viral potential, paywall friction
- **vs. Random rewards**: Unpredictable, less motivating
- **vs. One-time bonus**: Dropbox model proven to drive sustained growth

**Dropbox Growth Stats** (for reference):
- Permanent storage rewards drove 60% growth
- Users with referrals had 2x retention
- 35% of daily signups came from referrals

### Viral Touchpoints

The referral system is fully integrated into the UX with **5 strategic touchpoints**:

1. **📢 Momento di Gloria** (Passive Viral Growth)
   - **Where**: Price drop notifications
   - **What**: Share button with pre-filled message
   - **Why**: Users are happiest when saving money → natural sharing moment
   - **Impact**: Emotional timing drives authentic word-of-mouth

2. **🎁 /share Command** (Active Discovery)
   - **Where**: Dedicated command for referrals
   - **What**: Shows personal link + current slot count + system explanation
   - **Why**: Makes referral system discoverable and accessible
   - **Impact**: Users can actively invite whenever they want

3. **📖 /help Command** (Organic Discovery)
   - **Where**: Help message
   - **What**: Mentions `/share` in "Invita amici" category + hint at bottom
   - **Why**: New users discover referral system while learning bot
   - **Impact**: Increases awareness without being pushy

4. **📦 /list Command** (Contextual Prompt)
   - **Where**: After product list when <3 slots available and <21 total
   - **What**: Inline hint "Stai esaurendo gli slot! Usa /share..."
   - **Why**: User sees problem (low slots) → immediate solution presented
   - **Impact**: Perfect timing when user realizes space is limited

5. **➕ /add Command** (Immediate Awareness)
   - **Where**: After successfully adding product, when <3 slots available and <21 total
   - **What**: Separate message with slot count + /share hint
   - **Why**: User just consumed a slot → immediate awareness of impact
   - **Impact**: Best timing - user sees consequence in real-time

**Key Design Principles**:
- **Non-intrusive**: Hints only appear when genuinely helpful (<3 slots)
- **Consistent**: Same logic across /list and /add (DRY principle)
- **Smart targeting**: Never shows to users at max capacity (21 slots)
- **Progressive disclosure**: From passive (notification button) to active (dedicated command)

### Testing

Tests cover all corner cases:
```python
# Test referral bonus on first product
async def test_first_product_gives_referral_bonus()

# Test no double bonus if product deleted and re-added
async def test_no_double_bonus_after_product_removal()

# Test inviter at cap doesn't get notified
async def test_referrer_at_cap_no_notification()

# Test invalid referral codes
async def test_invalid_referral_code_handling()

# Test self-referral prevention
async def test_self_referral_ignored()
```

All 347 tests pass with 97% coverage.

---

## Logging Strategy

**Configuration**:
- Use `TimedRotatingFileHandler` with daily rotation
- Keep only last 3 days of logs (today + 2 previous days)
- Log format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Log files stored directly in `data/`:
  - `repackit.log` - Main bot operations (bot.py, scraper, checker, cleanup)
  - `broadcast.log` - Broadcast script operations

**Example Setup**:
```python
from logging.handlers import TimedRotatingFileHandler

handler = TimedRotatingFileHandler(
    filename='data/repackit.log',
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
uv run ruff format .

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

# Hooks will run ruff format + ruff check automatically
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
# No browser dependencies needed (uses Amazon Creator API)
# Run as non-root user (via gosu privilege drop)
```

### Volume Persistence
```yaml
volumes:
  - ./data:/app/data  # Database + logs persist across restarts
```

---

## CI/CD Pipelines (GitHub Actions)

### 1. `ci.yml` - Unified Lint + Test
- Runs on every push/PR
- **Lint job**: Runs `ruff format --check .` and `ruff check .`
- **Test job**: Executes `pytest --cov=. --cov-report=xml`
- Uploads coverage to SonarCloud

### 2. `docker.yml` - Container Build
- Builds Docker image
- Pushes to registry on main branch

### 3. SonarCloud Integration
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
├── test_amazon_api.py
├── test_data_reader.py
├── test_checker.py
├── test_product_cleanup.py
├── test_broadcast.py
├── utils/
│   └── test_retry.py
└── handlers/
    ├── test_start.py
    ├── test_add.py
    └── ...
```

### Testing Principles
1. **Unit Tests**: Test each function in isolation
2. **Mocking**: Mock external dependencies (Telegram API, Amazon Creator API, database)
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

### Amazon Creator API

Price data is fetched via the official Amazon Creator API (replaced Playwright scraping).

**Authentication**: OAuth 2.0 client credentials via Amazon Cognito
**Endpoint**: `https://creatorsapi.amazon/catalog/v1/getItems`
**Resources requested**: `offersV2.listings.price`, `offersV2.listings.availability`, `offersV2.listings.condition`, `offersV2.listings.isBuyBoxWinner`, `itemInfo.title`

**Regional token endpoints**:
- NA (version 2.1): `creatorsapi.auth.us-east-1.amazoncognito.com`
- EU (version 2.2): `creatorsapi.auth.eu-south-2.amazoncognito.com`
- FE (version 2.3): `creatorsapi.auth.us-west-2.amazoncognito.com`

**Benefits over Playwright scraping**:
- No browser dependency (~500MB savings in Docker image)
- Reliable structured data (no HTML parsing fragility)
- Official API with proper rate limits
- Batch requests (up to 10 ASINs per call)

---

## Future Enhancements

### Phase 1 (Current)
- [x] Basic product monitoring (ASIN, price, deadline)
- [x] Daily price checking + notifications
- [x] User commands (add, list, delete, update)
- [x] Cleanup of expired products
- [x] Viral growth strategy ("Momento di Gloria" share button)
- [x] Referral system with slot rewards (Dropbox-style gamification)
- [x] Amazon Creator API integration (replaced Playwright scraping)

### Phase 2 (Planned)
- [ ] Multi-marketplace support (.com, .de, .fr, .es, .uk)
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
3. Check logs: `docker-compose logs -f` or `tail -f data/repackit.log`

### Price Fetch Failures
1. Verify Amazon Creator API credentials in `.env` (`AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET`)
2. Check API token endpoint connectivity (see regional endpoints in `amazon_api.py`)
3. Test manually: `uv run python data_reader.py <ASIN>`
4. Check logs for API errors (401 = bad credentials, 429 = rate limited)

### Database Locked Errors
SQLite doesn't support high concurrency. If errors occur:
1. Ensure only one bot instance is running
2. Check file permissions on `data/repackit.db`
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
    prices = await api_client.get_items(asins, marketplace)
except AmazonCreatorAPIError as e:
    logger.warning(f"API call failed: {e}")
    return {}  # Skip and retry tomorrow
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

### Telegram Message Formatting

**IMPORTANT**: All bot messages use **HTML formatting** (`parse_mode="HTML"`), not Markdown.

HTML is more robust and prevents parsing errors with special characters like underscores (`_`), asterisks (`*`), and brackets that may appear in user input or channel references (e.g., `@channel_name`).

**HTML Tags**:
- **Bold**: `<b>text</b>` (not `*text*`)
- **Italic**: `<i>text</i>` (not `_text_`)
- **Code**: `<code>text</code>` (not `` `text` ``)
- **Links**: `<a href="url">text</a>` (not `[text](url)`)

**Example**:
```python
await update.message.reply_text(
    "✅ <b>Prodotto aggiunto!</b>\n\n"
    f"📦 <b>{product_name}</b>\n"
    f"🔖 ASIN: <code>{asin}</code>\n"
    f"💰 Prezzo: €{price:.2f}\n\n"
    "<i>Monitorerò il prezzo ogni giorno!</i>",
    parse_mode="HTML"
)
```

**Why HTML over Markdown**:
- Markdown fails when URLs contain underscores (e.g., `@repackit_updates`)
- HTML is more predictable with special characters in user input
- Easier to escape when needed (use `&lt;`, `&gt;`, `&amp;`)
- More consistent with Telegram's internal formatting

**Consistency**: All bot messages (handlers, notifications, broadcasts) use `parse_mode="HTML"` exclusively.

---

## Dependency Management (pyproject.toml)

```toml
[project]
name = "repackit"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "python-telegram-bot[webhooks]>=21.0",
    "aiosqlite>=0.19",
    "python-dotenv>=1.0",
    "httpx>=0.25",
    "aiohttp>=3.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.1",
    "ruff>=0.1",
    "pre-commit>=3.5",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501", "SIM117", "SIM116"]  # Line too long handled by ruff format

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

### API
- Batch ASINs per request (max 10, handled automatically by `amazon_api.py`)
- OAuth token caching (1 hour, with 60s refresh buffer)
- Deduplication: same ASIN across multiple users = 1 API call

### Memory
- No browser dependency (lightweight HTTP-only client)
- Minimal memory footprint compared to previous Playwright-based approach

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
5. Run linters: `ruff format` + `ruff check`
6. Submit PR with clear description

### Code Review Checklist
- [ ] Tests pass (`pytest`)
- [ ] Coverage ≥80% (`pytest --cov`)
- [ ] Linting passes (`ruff format --check` + `ruff check`)
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
- **Amazon Creator API Docs**: https://programma-affiliazione.amazon.it/creatorsapi/docs/en-us/get-started/using-sdk

---

**Last Updated**: 2024-12-06
**Maintained By**: @dstmrk

---

*This document is the single source of truth for RepackIt development. Update it whenever architectural decisions change.*
