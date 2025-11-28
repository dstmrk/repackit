"""Main Telegram bot with webhook and scheduler."""

import asyncio
import logging
import os
import signal
from datetime import UTC, datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler

import checker
import database
import product_cleanup
from data_reader import scrape_prices
from handlers.add import add_conversation_handler
from handlers.delete import delete_callback_query_handler, delete_command_handler
from handlers.feedback import feedback_callback_handler, feedback_conversation_handler
from handlers.help import help_handler
from handlers.list import list_handler
from handlers.start import start_handler
from handlers.update import update_conversation_handler
from health_handler import HEALTH_PORT, start_health_server

# Load environment variables
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Create logs directory if it doesn't exist
os.makedirs("data/logs", exist_ok=True)

# Setup rotating file handler (daily rotation, keep 2 backups + today = 3 days total)
file_handler = TimedRotatingFileHandler(
    filename="data/logs/bot.log",
    when="midnight",
    interval=1,
    backupCount=2,
)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        file_handler,
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
    now = datetime.now(UTC)
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
        await database.update_system_status("last_scraper_run", datetime.now(UTC).isoformat())

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


async def schedule_task(task_name: str, hour: int, task_func) -> None:  # pragma: no cover
    """
    Generic scheduler for daily tasks.

    Args:
        task_name: Human-readable name for logging (e.g., "Scraper", "Checker")
        hour: Hour of day to run (0-23)
        task_func: Async function to execute
    """
    while not shutdown_event.is_set():
        next_run = calculate_next_run(hour)
        sleep_seconds = (next_run - datetime.now(UTC)).total_seconds()

        logger.info(f"{task_name} scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        # Wait for sleep_seconds or until shutdown event is set
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=sleep_seconds)
            # If we got here, shutdown was triggered
            break
        except TimeoutError:
            # Timeout is normal - time to run the task
            pass

        if not shutdown_event.is_set():
            await task_func()


async def schedule_scraper() -> None:  # pragma: no cover
    """Schedule daily scraper runs."""
    await schedule_task("Scraper", SCRAPER_HOUR, run_scraper)


async def schedule_checker() -> None:  # pragma: no cover
    """Schedule daily checker runs."""
    await schedule_task("Checker", CHECKER_HOUR, run_checker)


async def schedule_cleanup() -> None:  # pragma: no cover
    """Schedule daily cleanup runs."""
    await schedule_task("Cleanup", CLEANUP_HOUR, run_cleanup)


# ============================================================================
# Main Application
# ============================================================================


def validate_environment() -> list[str]:
    """
    Validate all required environment variables are set.

    Returns:
        List of missing variable names (empty if all are set)
    """
    required_vars = {
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "WEBHOOK_URL": WEBHOOK_URL,
        "WEBHOOK_SECRET": WEBHOOK_SECRET,
    }

    missing = [name for name, value in required_vars.items() if not value]
    return missing


def setup_signal_handlers() -> None:  # pragma: no cover
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def post_init(application: Application) -> None:  # pragma: no cover
    """Initialize background tasks after bot startup."""
    logger.info("Starting background tasks...")

    # Start scheduler tasks
    scraper_task = asyncio.create_task(schedule_scraper())
    checker_task = asyncio.create_task(schedule_checker())
    cleanup_task = asyncio.create_task(schedule_cleanup())

    # Store tasks to prevent garbage collection
    application.bot_data["scraper_task"] = scraper_task
    application.bot_data["checker_task"] = checker_task
    application.bot_data["cleanup_task"] = cleanup_task

    logger.info(f"Scraper scheduled for {calculate_next_run(SCRAPER_HOUR)}")
    logger.info(f"Checker scheduled for {calculate_next_run(CHECKER_HOUR)}")
    logger.info(f"Cleanup scheduled for {calculate_next_run(CLEANUP_HOUR)}")

    # Start health check server (async background task)
    health_task = asyncio.create_task(start_health_server())
    application.bot_data["health_task"] = health_task

    # Allow event loop to process
    await asyncio.sleep(0)


def main() -> None:  # pragma: no cover
    """Main bot application."""
    logger.info("Starting RepackIt bot...")

    # Validate environment variables
    missing_vars = validate_environment()
    if missing_vars:
        logger.error(
            f"Missing required environment variables: {', '.join(missing_vars)}\n"
            "Please set them in your .env file or environment."
        )
        return

    # Initialize database (synchronously)
    logger.info("Initializing database...")
    asyncio.run(database.init_db())

    # Create bot application with post_init callback
    logger.info("Creating bot application...")
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .connect_timeout(10.0)
        .read_timeout(30.0)
        .write_timeout(15.0)
        .pool_timeout(10.0)
        .build()
    )

    # Register command handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(add_conversation_handler)
    application.add_handler(CommandHandler("list", list_handler))
    application.add_handler(delete_command_handler)
    application.add_handler(delete_callback_query_handler)
    application.add_handler(update_conversation_handler)
    application.add_handler(feedback_conversation_handler)
    application.add_handler(feedback_callback_handler)

    logger.info("✅ Bot configured!")
    logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}")
    logger.info(f"🔌 Webhook port: {BOT_PORT}")
    logger.info(f"🏥 Health check port: {HEALTH_PORT}")
    logger.info("🚀 Starting webhook server...")

    # Start webhook server (synchronous call, manages its own event loop)
    application.run_webhook(
        listen="0.0.0.0",
        port=BOT_PORT,
        url_path=TELEGRAM_TOKEN,
        secret_token=WEBHOOK_SECRET,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}",
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
        bootstrap_retries=3,
    )


if __name__ == "__main__":
    # Setup signal handlers
    setup_signal_handlers()

    # Run bot
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
