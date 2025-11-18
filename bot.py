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
from handlers.add import add_handler
from handlers.delete import delete_handler
from handlers.list import list_handler
from handlers.start import start_handler
from health_handler import start_health_server

# Load environment variables
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Create logs directory if it doesn't exist
os.makedirs("data/logs", exist_ok=True)

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

# Global event for graceful shutdown
shutdown_event = asyncio.Event()


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


async def schedule_scraper() -> None:  # pragma: no cover
    """Schedule daily scraper runs."""
    while not shutdown_event.is_set():
        next_run = calculate_next_run(SCRAPER_HOUR)
        sleep_seconds = (next_run - datetime.now()).total_seconds()

        logger.info(f"Scraper scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Wait for sleep_seconds or until shutdown event is set
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=sleep_seconds)
            # If we got here, shutdown was triggered
            break
        except TimeoutError:
            # Timeout is normal - time to run the scraper
            pass

        if not shutdown_event.is_set():
            await run_scraper()


async def schedule_checker() -> None:  # pragma: no cover
    """Schedule daily checker runs."""
    while not shutdown_event.is_set():
        next_run = calculate_next_run(CHECKER_HOUR)
        sleep_seconds = (next_run - datetime.now()).total_seconds()

        logger.info(f"Checker scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Wait for sleep_seconds or until shutdown event is set
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=sleep_seconds)
            # If we got here, shutdown was triggered
            break
        except TimeoutError:
            # Timeout is normal - time to run the checker
            pass

        if not shutdown_event.is_set():
            await run_checker()


async def schedule_cleanup() -> None:  # pragma: no cover
    """Schedule daily cleanup runs."""
    while not shutdown_event.is_set():
        next_run = calculate_next_run(CLEANUP_HOUR)
        sleep_seconds = (next_run - datetime.now()).total_seconds()

        logger.info(f"Cleanup scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Wait for sleep_seconds or until shutdown event is set
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=sleep_seconds)
            # If we got here, shutdown was triggered
            break
        except TimeoutError:
            # Timeout is normal - time to run the cleanup
            pass

        if not shutdown_event.is_set():
            await run_cleanup()


# ============================================================================
# Command Handlers (Stubs - to be implemented)
# ============================================================================


async def update_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:  # pragma: no cover
    """Handle /update command."""
    await update.message.reply_text(
        "⚠️ Comando /update non ancora implementato.\nUtilizzo: /update <numero> <campo> <valore>"
    )


async def feedback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:  # pragma: no cover
    """Handle /feedback command."""
    await update.message.reply_text(
        "⚠️ Comando /feedback non ancora implementato.\nUtilizzo: /feedback <messaggio>"
    )


# ============================================================================
# Main Application
# ============================================================================


def setup_signal_handlers() -> None:  # pragma: no cover
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:  # pragma: no cover
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
