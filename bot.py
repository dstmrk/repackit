"""Main Telegram bot with webhook and scheduler."""

import asyncio
import contextlib
import logging
import os
import signal
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import checker
import database
import product_cleanup
from data_reader import scrape_prices
from health_handler import start_health_server

# Load environment variables
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/logs/bot.log"),
    ],
)
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
BOT_PORT = int(os.getenv("BOT_PORT", "8443"))

# Scheduler configuration
SCRAPER_HOUR = int(os.getenv("SCRAPER_HOUR", "9"))
CHECKER_HOUR = int(os.getenv("CHECKER_HOUR", "10"))
CLEANUP_HOUR = int(os.getenv("CLEANUP_HOUR", "2"))

# Global flag for graceful shutdown
shutdown_flag = False


def calculate_next_run(hour: int) -> datetime:
    """
    Calculate next run time for a scheduled task.

    Args:
        hour: Hour of day to run (0-23)

    Returns:
        Datetime of next scheduled run
    """
    now = datetime.now()
    next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)

    # If the time has already passed today, schedule for tomorrow
    if next_run <= now:
        next_run += timedelta(days=1)

    return next_run


async def run_scraper() -> None:
    """Run the scraper task."""
    try:
        logger.info("Starting scheduled scraper run")

        # Get all active products
        products = await database.get_all_active_products()

        if not products:
            logger.info("No active products to scrape")
            return

        # Scrape prices
        results = await scrape_prices(products)
        logger.info(f"Scraper completed: {len(results)}/{len(products)} prices scraped")

        # Update system status
        await database.update_system_status("last_scraper_run", datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Error in scraper task: {e}", exc_info=True)


async def run_checker() -> None:
    """Run the checker task."""
    try:
        logger.info("Starting scheduled checker run")
        stats = await checker.check_and_notify()
        logger.info(
            f"Checker completed: {stats['notifications_sent']} notifications sent, "
            f"{stats['errors']} errors"
        )
    except Exception as e:
        logger.error(f"Error in checker task: {e}", exc_info=True)


async def run_cleanup() -> None:
    """Run the cleanup task."""
    try:
        logger.info("Starting scheduled cleanup run")
        result = await product_cleanup.cleanup_expired_products()
        logger.info(f"Cleanup completed: {result['deleted']} expired products removed")
    except Exception as e:
        logger.error(f"Error in cleanup task: {e}", exc_info=True)


async def schedule_scraper() -> None:
    """Schedule daily scraper runs."""
    while not shutdown_flag:
        next_run = calculate_next_run(SCRAPER_HOUR)
        sleep_seconds = (next_run - datetime.now()).total_seconds()

        logger.info(f"Scraper scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Sleep until next run (check shutdown flag every minute)
        while sleep_seconds > 0 and not shutdown_flag:
            await asyncio.sleep(min(60, sleep_seconds))
            sleep_seconds -= 60

        if not shutdown_flag:
            await run_scraper()


async def schedule_checker() -> None:
    """Schedule daily checker runs."""
    while not shutdown_flag:
        next_run = calculate_next_run(CHECKER_HOUR)
        sleep_seconds = (next_run - datetime.now()).total_seconds()

        logger.info(f"Checker scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Sleep until next run (check shutdown flag every minute)
        while sleep_seconds > 0 and not shutdown_flag:
            await asyncio.sleep(min(60, sleep_seconds))
            sleep_seconds -= 60

        if not shutdown_flag:
            await run_checker()


async def schedule_cleanup() -> None:
    """Schedule daily cleanup runs."""
    while not shutdown_flag:
        next_run = calculate_next_run(CLEANUP_HOUR)
        sleep_seconds = (next_run - datetime.now()).total_seconds()

        logger.info(f"Cleanup scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Sleep until next run (check shutdown flag every minute)
        while sleep_seconds > 0 and not shutdown_flag:
            await asyncio.sleep(min(60, sleep_seconds))
            sleep_seconds -= 60

        if not shutdown_flag:
            await run_cleanup()


# ============================================================================
# Command Handlers (Stubs - to be implemented)
# ============================================================================


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text(
        "👋 Benvenuto su RepackIt!\n\n"
        "Ti aiuto a risparmiare monitorando i prezzi Amazon durante il periodo di reso.\n\n"
        "Comandi disponibili:\n"
        "/add - Aggiungi un prodotto da monitorare\n"
        "/list - Visualizza i tuoi prodotti\n"
        "/delete - Rimuovi un prodotto\n"
        "/update - Modifica un prodotto\n"
        "/feedback - Invia un feedback"
    )


async def add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add command."""
    await update.message.reply_text(
        "⚠️ Comando /add non ancora implementato.\n"
        "Utilizzo: /add <url> <prezzo> <giorni|data> [soglia]"
    )


async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list command."""
    await update.message.reply_text("⚠️ Comando /list non ancora implementato.")


async def delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command."""
    await update.message.reply_text(
        "⚠️ Comando /delete non ancora implementato.\n" "Utilizzo: /delete <numero>"
    )


async def update_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /update command."""
    await update.message.reply_text(
        "⚠️ Comando /update non ancora implementato.\n" "Utilizzo: /update <numero> <campo> <valore>"
    )


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /feedback command."""
    await update.message.reply_text(
        "⚠️ Comando /feedback non ancora implementato.\n" "Utilizzo: /feedback <messaggio>"
    )


# ============================================================================
# Main Application
# ============================================================================


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        global shutdown_flag
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_flag = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:
    """Main bot application."""
    logger.info("Starting RepackIt bot...")

    # Validate environment variables
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not set")
        return

    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL not set")
        return

    # Initialize database
    logger.info("Initializing database...")
    await database.init_db()

    # Start health check server
    logger.info("Starting health check server...")
    start_health_server()

    # Create bot application
    logger.info("Creating bot application...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("add", add_handler))
    application.add_handler(CommandHandler("list", list_handler))
    application.add_handler(CommandHandler("delete", delete_handler))
    application.add_handler(CommandHandler("update", update_handler))
    application.add_handler(CommandHandler("feedback", feedback_handler))

    # Setup webhook
    logger.info(f"Setting up webhook: {WEBHOOK_URL}")
    await application.bot.set_webhook(
        url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}",
        secret_token=WEBHOOK_SECRET,
        allowed_updates=["message", "callback_query"],
    )

    # Start scheduler tasks
    logger.info("Starting scheduler tasks...")
    scheduler_tasks = [
        asyncio.create_task(schedule_scraper()),
        asyncio.create_task(schedule_checker()),
        asyncio.create_task(schedule_cleanup()),
    ]

    # Start webhook server
    logger.info(f"Starting webhook server on port {BOT_PORT}...")
    await application.run_webhook(
        listen="0.0.0.0",
        port=BOT_PORT,
        url_path=TELEGRAM_TOKEN,
        secret_token=WEBHOOK_SECRET,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}",
    )

    # Graceful shutdown
    logger.info("Shutting down...")
    for task in scheduler_tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    await application.shutdown()
    logger.info("Bot stopped")


if __name__ == "__main__":
    # Setup signal handlers
    setup_signal_handlers()

    # Run bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
