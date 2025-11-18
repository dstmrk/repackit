# RepackIt Bot 🤖

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

# 2. Crea directory data con permessi corretti
mkdir -p data/logs
chown -R 1000:1000 data  # User repackit nel container ha uid 1000

# 3. Build e avvia con docker-compose
docker-compose up -d

# 4. Verifica i logs
docker-compose logs -f

# 5. Controlla health status
curl http://localhost:8444/health
```

### Comandi Docker Utili

```bash
# Stop del bot
docker-compose down

# Rebuild dopo modifiche
docker-compose build

# Visualizza logs
docker-compose logs -f repackit-bot

# Restart del container
docker-compose restart

# Accedi al container
docker-compose exec repackit-bot /bin/bash
```

### Build manuale Docker

```bash
# 1. Build immagine
docker build -t repackit:latest .

# 2. Crea directory data con permessi corretti
mkdir -p data/logs
chown -R 1000:1000 data  # User repackit nel container

# 3. Run container
docker run -d \
  --name repackit \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -p 8443:8443 \
  -p 8444:8444 \
  repackit:latest
```

## Comandi Bot

- `/start` - Messaggio di benvenuto e registrazione
- `/add <url> <prezzo> <giorni> [soglia]` - Aggiungi prodotto da monitorare
- `/list` - Visualizza prodotti monitorati
- `/delete <numero>` - Rimuovi prodotto
- `/update <numero> <campo> <valore>` - Aggiorna prodotto
- `/feedback <messaggio>` - Invia feedback agli admin

### Esempi

```
/add https://amazon.it/dp/B08N5WRWNW 59.90 30
/add https://amazon.it/dp/B08N5WRWNW 59.90 2024-12-25 5
/update 1 prezzo 55.00
/update 1 scadenza 2024-12-30
/delete 2
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
├── handlers/               # Command handlers
│   ├── start.py
│   ├── add.py
│   ├── list.py
│   ├── delete.py
│   ├── update.py
│   └── feedback.py
├── tests/                  # Unit tests (80%+ coverage)
├── data/                   # Persistent data (gitignored)
│   ├── users.db
│   └── logs/
├── Dockerfile              # Multi-stage build
├── docker-compose.yml      # Production orchestration
└── .github/workflows/      # CI/CD pipelines
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
DATABASE_PATH=./data/users.db

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
2. Verifica permessi file: `chmod 644 data/users.db`
3. Considera WAL mode: `PRAGMA journal_mode=WAL;`

### Permission denied su data/logs

1. Il container usa utente repackit (uid 1000)
2. La directory data deve essere scrivibile: `chown -R 1000:1000 data/`
3. Oppure permessi più aperti: `chmod -R 777 data/` (solo per test)
4. Verifica ownership: `ls -la data/`

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
- 💬 Discussioni: [GitHub Discussions](https://github.com/dstmrk/repackit/discussions)
- 📧 Email: support@repackit.io

---

**Fatto con ❤️ da [@dstmrk](https://github.com/dstmrk)**
