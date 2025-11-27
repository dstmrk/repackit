# RepackIt Bot 🤖📦

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![Unit Tests](https://github.com/dstmrk/repackit/actions/workflows/test.yml/badge.svg)](https://github.com/dstmrk/repackit/actions/workflows/test.yml)
[![Lint](https://github.com/dstmrk/repackit/actions/workflows/lint.yml/badge.svg)](https://github.com/dstmrk/repackit/actions/workflows/lint.yml)
[![Docker Build](https://github.com/dstmrk/repackit/actions/workflows/docker.yml/badge.svg)](https://github.com/dstmrk/repackit/actions/workflows/docker.yml)

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
- ✅ **Limite 20 prodotti** per utente
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

### Quick Start

```bash
# 1. Configura .env
cp .env.example .env
vim .env  # Inserisci le tue credenziali

# 2. Build e avvia con docker-compose
docker-compose up -d

# 3. Verifica i logs
docker-compose logs -f

# 4. Controlla health status
curl http://localhost:8444/health
```

## Comandi Bot

### Comandi Principali

- `/start` - Messaggio di benvenuto e registrazione
- `/help` - Mostra tutti i comandi disponibili con descrizioni dettagliate
- `/add` - **Aggiungi prodotto** (flusso conversazionale guidato)
  - Step 1: Invia URL Amazon.it
  - Step 2: Invia prezzo pagato
  - Step 3: Invia scadenza reso (numero giorni o data gg-mm-aaaa)
  - Step 4: Invia la soglia di risparmio minimo che vuoi avere
- `/list` - **Visualizza prodotti** monitorati (mostra conteggio 5/20)
- `/delete` - **Rimuovi prodotto** con conferma inline keyboard
  - Mostra lista prodotti con bottoni cliccabili
  - Richiede conferma prima di eliminare
- `/update` - **Aggiorna prodotto** (flusso conversazionale con inline keyboards)
  - Step 1: Seleziona prodotto da lista
  - Step 2: Scegli campo (prezzo/scadenza/soglia)
  - Step 3: Inserisci nuovo valore
- `/feedback` - **Invia feedback** (flusso conversazionale con validazione)
  - Scrivi messaggio (min 10, max 1000 caratteri)
  - Conferma con anteprima prima di inviare

### Limiti

- **Massimo 20 prodotti** per utente
- **Validazione automatica** su tutti gli input
- **Supporto /cancel** in ogni flusso conversazionale

### Esempio Utilizzo

```bash
# 1. Aggiungi un prodotto
Utente: /add
Bot: Inviami il link del prodotto Amazon.it
Utente: https://amazon.it/dp/B08N5WRWNW
Bot: Inviami il prezzo che hai pagato in euro
Utente: 59.90
Bot: Inviami la scadenza del reso
Utente: 30
Bot: ✅ Prodotto aggiunto con successo!

# 2. Visualizza lista
Utente: /list
Bot: Hai 1/20 prodotti monitorati. [mostra lista]

# 3. Aggiorna prezzo
Utente: /update
Bot: [mostra lista prodotti con bottoni]
Utente: [clicca prodotto 1]
Bot: [mostra opzioni: Prezzo/Scadenza/Soglia]
Utente: [clicca "Prezzo pagato"]
Bot: Inviami il nuovo prezzo in euro
Utente: 55.00
Bot: ✅ Prezzo aggiornato con successo!

# 4. Rimuovi prodotto
Utente: /delete
Bot: [mostra prodotto con conferma]
Utente: [clicca "Sì, elimina"]
Bot: ✅ Prodotto eliminato

# 5. Invia feedback
Utente: /feedback
Bot: Scrivi il tuo feedback
Utente: Il bot funziona benissimo!
Bot: [mostra anteprima con conferma]
Utente: [clicca "Sì, invia"]
Bot: ✅ Feedback inviato con successo!
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
│   ├── add.py             # Add product (3-step conversation)
│   ├── list.py            # List products (with count)
│   ├── delete.py          # Delete product (with confirmation)
│   ├── update.py          # Update product (3-step conversation)
│   └── feedback.py        # Send feedback (with validation)
├── tests/                  # Unit tests (91%+ coverage)
│   └── handlers/          # Handler tests
├── data/                   # Persistent data (gitignored)
│   ├── repackit.db        # SQLite database
│   └── logs/              # Rotating logs (3 days)
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
  "timestamp": "2024-11-18T14:30:00.123456",
  "stats": {
    "users": 150,
    "products_total": 245,
    "products_active": 180
  },
  "tasks": {
    "scraper": {"status": "ok", "last_run": "2024-11-18T09:00:00"},
    "checker": {"status": "ok", "last_run": "2024-11-18T10:00:00"},
    "cleanup": {"status": "ok", "last_run": "2024-11-18T02:00:00"}
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

# Logging
LOG_LEVEL=INFO
```

## Troubleshooting

### Bot non riceve messaggi

1. Verifica che `WEBHOOK_URL` sia pubblicamente accessibile (HTTPS)
2. Controlla webhook status: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Verifica logs: `docker-compose logs -f`

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
