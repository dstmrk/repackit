# RepackIt Bot 🤖📦

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![Unit Tests](https://github.com/dstmrk/repackit/actions/workflows/test.yml/badge.svg)](https://github.com/dstmrk/repackit/actions/workflows/test.yml)
[![Lint](https://github.com/dstmrk/repackit/actions/workflows/lint.yml/badge.svg)](https://github.com/dstmrk/repackit/actions/workflows/lint.yml)
[![Docker Build](https://github.com/dstmrk/repackit/actions/workflows/docker.yml/badge.svg)](https://github.com/dstmrk/repackit/actions/workflows/docker.yml)
[![Docker Publish](https://github.com/dstmrk/repackit/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/dstmrk/repackit/actions/workflows/docker-publish.yml)
[![Docker Image Version](https://ghcr-badge.egpl.dev/dstmrk/repackit/latest_tag?trim=major&label=latest)](https://github.com/dstmrk/repackit/pkgs/container/repackit)

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=bugs)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=dstmrk_repackit&metric=coverage)](https://sonarcloud.io/summary/new_code?id=dstmrk_repackit)

Un bot Telegram che ti avvisa se il prezzo dei tuoi acquisti Amazon scende durante il periodo di reso, permettendoti di riacquistarli a meno e fare il reso del primo ordine.

## Caratteristiche

- ✅ Monitoraggio automatico prezzi Amazon
- ✅ Notifiche intelligenti sui ribassi
- ✅ Gestione scadenze reso
- ✅ Soglie di risparmio personalizzabili
- ✅ **Flussi conversazionali** per tutti i comandi
- ✅ **Validazione robusta** con inline keyboards
- ✅ **Sistema referral gamificato** con slot dinamici (3-21)
- ✅ **5 touchpoint virali** per crescita organica
- ✅ Health check endpoint per monitoring
- ✅ Webhook-only (production-ready)
- ✅ Docker support con multi-stage build

## Requisiti

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) per dependency management
- PostgreSQL/SQLite per database
- Account bot Telegram (via [@BotFather](https://t.me/botfather))

## Setup Locale (Sviluppo)

### 1. Clona il repository

```bash
git clone https://github.com/dstmrk/repackit.git
cd repackit
```

### 2. Installa dipendenze

```bash
# Installa uv se non l'hai già
curl -LsSf https://astral.sh/uv/install.sh | sh

# Installa le dipendenze del progetto
uv sync --extra dev
```

### 3. Configura environment variables

```bash
cp .env.example .env
# Modifica .env con i tuoi valori
```

### 4. Installa Playwright browsers

```bash
uv run playwright install chromium
```

### 5. Avvia il bot

```bash
# Per sviluppo locale, usa un tunnel (ngrok, Cloudflare Tunnel, etc.)
# per esporre il webhook pubblicamente

uv run python bot.py
```

## Deployment con Docker (Produzione)

### Quick Start (Immagine Pre-Built da GHCR)

```bash
# 1. Configura .env
cp .env.example .env
vim .env  # Inserisci le tue credenziali

# 2. Avvia con docker compose (usa immagine da GHCR)
docker compose pull  # Scarica ultima versione
docker compose up -d

# 3. Verifica i logs
docker compose logs -f

# 4. Controlla health status
curl http://localhost:8444/health

# 5. Aggiorna a nuova versione
docker compose pull
docker compose up -d
```

### Build Locale (Sviluppo)

Per sviluppare localmente e fare build dell'immagine:

```bash
# Usa il file di override per build locale
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Oppure crea un alias per comodità
alias dc-dev='docker compose -f docker-compose.yml -f docker-compose.dev.yml'
dc-dev up -d
```

### Pubblicazione Nuova Versione

Il workflow GitHub pubblica automaticamente nuove immagini su GHCR quando viene creato un tag:

```bash
# 1. Crea un nuovo tag (semantic versioning)
git tag v1.0.0
git push origin v1.0.0

# 2. Il workflow GitHub Actions:
#    - Builda l'immagine Docker
#    - La pubblica su ghcr.io/dstmrk/repackit:v1.0.0
#    - La tagga anche come :latest

# 3. Gli utenti possono aggiornare con:
docker compose pull
docker compose up -d
```

## Comandi Bot

### Comandi Principali

- `/start` - Messaggio di benvenuto e registrazione
- `/help` - Mostra tutti i comandi disponibili con descrizioni dettagliate
- `/add` - **Aggiungi prodotto** (flusso conversazionale in 5 step)
  - Step 1: Nome prodotto
  - Step 2: URL Amazon.it
  - Step 3: Prezzo pagato
  - Step 4: Scadenza reso (numero giorni o data gg-mm-aaaa)
  - Step 5: Risparmio minimo per notifica
- `/list` - **Visualizza prodotti** monitorati (mostra conteggio 5/20)
- `/delete` - **Rimuovi prodotto** con conferma inline keyboard
  - Mostra lista prodotti con bottoni cliccabili
  - Richiede conferma prima di eliminare
- `/update` - **Aggiorna prodotto** (flusso conversazionale con inline keyboards)
  - Step 1: Seleziona prodotto da lista
  - Step 2: Scegli campo (nome/prezzo/scadenza/soglia)
  - Step 3: Inserisci nuovo valore
- `/feedback` - **Invia feedback** (flusso conversazionale con validazione)
  - Scrivi messaggio (min 10, max 1000 caratteri)
  - Conferma con anteprima prima di inviare

### Limiti

- **Massimo 20 prodotti** per utente
- **Validazione automatica** su tutti gli input
- **Supporto /cancel** in ogni flusso conversazionale

### Esempio Utilizzo

```
# 1. Aggiungi un prodotto
Utente: /add
Bot: Come vuoi chiamare questo prodotto?
Utente: iPhone 15 Pro
Bot: Inviami il link del prodotto Amazon.it
Utente: https://amazon.it/dp/B08N5WRWNW
Bot: Inviami il prezzo che hai pagato in euro
Utente: 59.90
Bot: Inviami la scadenza del reso
Utente: 30
Bot: Qual è il risparmio minimo per cui vuoi essere notificato?
Utente: 5
Bot: ✅ Prodotto aggiunto con successo!

# 2. Visualizza lista
Utente: /list
Bot: Hai 1/20 prodotti monitorati. [mostra lista con nomi]

# 3. Aggiorna prodotto
Utente: /update
Bot: [mostra lista prodotti con bottoni]
Utente: [clicca su "iPhone 15 Pro"]
Bot: [mostra opzioni: Nome/Prezzo/Scadenza/Soglia]
Utente: [clicca "Prezzo pagato"]
Bot: Inviami il nuovo prezzo in euro
Utente: 55.00
Bot: ✅ Prezzo aggiornato con successo!
```

## Admin Script

### Broadcast Messaggi

```bash
# Invia messaggio a tutti gli utenti registrati
uv run python broadcast.py "Manutenzione programmata domani alle 14:00"
```

**Nota**: Lo script broadcast richiede `ADMIN_USER_ID` configurato in `.env`.

## Development

### Esegui test

```bash
# Tutti i test con coverage
uv run pytest --cov=. --cov-report=html

# Test specifici
uv run pytest tests/test_bot.py -v

# Con coverage minima 80%
uv run pytest --cov=. --cov-fail-under=80
```

### Linting & Formatting

```bash
# Format code
uv run black .

# Lint code
uv run ruff check --fix .

# Pre-commit hooks
uv run pre-commit install
uv run pre-commit run --all-files
```

### Struttura Progetto

```
repackit/
├── bot.py                  # Main bot (webhook + scheduler)
├── data_reader.py          # Amazon scraper (Playwright)
├── checker.py              # Price comparison & notifications
├── product_cleanup.py      # Expired products removal
├── broadcast.py            # Admin broadcast script
├── health_handler.py       # Health check endpoint
├── database.py             # Database operations
├── handlers/               # Command handlers (conversational flows)
│   ├── start.py           # Welcome message
│   ├── help.py            # Help command
│   ├── add.py             # Add product (5-step conversation)
│   ├── list.py            # List products (with count)
│   ├── delete.py          # Delete product (with confirmation)
│   ├── update.py          # Update product (conversational flow)
│   ├── feedback.py        # Send feedback (with validation)
│   └── validators.py      # Shared validation logic
├── tests/                  # Unit tests (91%+ coverage)
│   └── handlers/          # Handler tests
├── data/                   # Persistent data (gitignored)
│   ├── repackit.db        # SQLite database
│   ├── repackit.log       # Main bot log (rotating, 3 days)
│   └── broadcast.log      # Broadcast script log
├── Dockerfile              # Multi-stage build
├── docker-compose.yml      # Production orchestration
├── .github/workflows/      # CI/CD pipelines
│   ├── test.yml           # Unit tests
│   ├── lint.yml           # Code quality (black + ruff)
│   └── docker.yml         # Docker build
├── CLAUDE.md              # Complete technical documentation
└── README.md              # This file
```

## Monitoring

### Health Check Endpoint

```bash
curl http://localhost:8444/health
```

Risposta esempio:
```json
{
  "status": "healthy",
  "timestamp": "2024-11-18 14:30:00",
  "stats": {
    "users": 150,
    "products_total": 245,
    "products_unique": 180,
    "products_total_count": 1250,
    "total_savings_generated": 3450.75
  },
  "tasks": {
    "scraper": {"status": "ok", "last_run": "2024-11-18 09:00:00"},
    "checker": {"status": "ok", "last_run": "2024-11-18 10:00:00"},
    "cleanup": {"status": "ok", "last_run": "2024-11-18 02:00:00"}
  }
}
```

### Integrazione UptimeRobot

1. Crea monitor HTTP(s)
2. URL: `https://your-domain.com:8444/health`
3. Keyword: `"healthy"`
4. Intervallo: 5 minuti

## Environment Variables

Variabili richieste in `.env`:

```bash
# Telegram
TELEGRAM_TOKEN=your_bot_token
WEBHOOK_URL=https://your-domain.com
WEBHOOK_SECRET=your_secret_token

# Server
BOT_PORT=8443
HEALTH_PORT=8444

# Database
DATABASE_PATH=./data/repackit.db

# Scheduler (24h format)
SCRAPER_HOUR=9
CHECKER_HOUR=10
CLEANUP_HOUR=2

# Admin
ADMIN_USER_ID=your_telegram_user_id

# Amazon
AMAZON_AFFILIATE_TAG=yourtag-21

# Product Limits & Referral System
DEFAULT_MAX_PRODUCTS=21
INITIAL_MAX_PRODUCTS=3
PRODUCTS_PER_REFERRAL=3
INVITED_USER_BONUS=3

# Telegram Rate Limiting
TELEGRAM_MESSAGES_PER_SECOND=30  # Telegram API hard limit
BATCH_SIZE=10  # Batch size for notifications and broadcasts
DELAY_BETWEEN_BATCHES=1.0  # Delay in seconds between batches

# Logging
LOG_LEVEL=INFO
```

## Troubleshooting

### Bot non riceve messaggi

1. Verifica che `WEBHOOK_URL` sia pubblicamente accessibile (HTTPS)
2. Controlla webhook status: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Verifica logs: `docker compose logs -f`

### Scraping fallisce

1. Verifica Playwright browsers installati: `uv run playwright install chromium`
2. Testa manualmente: `uv run python data_reader.py`
3. Controlla se Amazon ha cambiato HTML structure

### Database locked

1. Assicurati che solo un'istanza del bot sia in esecuzione
2. Verifica permessi file: `chmod 644 data/repackit.db`
3. Considera WAL mode: `PRAGMA journal_mode=WAL;`

## Contributing

1. Fork il repository
2. Crea feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m "feat: add amazing feature"`
4. Push to branch: `git push origin feature/amazing-feature`
5. Apri Pull Request

### Requisiti Pull Request

- ✅ Test pass (`pytest`)
- ✅ Coverage ≥80% (`pytest --cov`)
- ✅ Linting pass (`black` + `ruff`)
- ✅ Docstrings per funzioni pubbliche
- ✅ Type hints sulle signatures

## License

Questo progetto è rilasciato sotto licenza MIT. Vedi `LICENSE` per dettagli.

## Documentazione Completa

Per documentazione dettagliata su architettura, design decisions e deployment, consulta [CLAUDE.md](./CLAUDE.md).

## Supporto

- 🐛 Bug reports: [GitHub Issues](https://github.com/dstmrk/repackit/issues)
