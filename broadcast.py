"""Admin broadcast script for sending messages to all users.

This is a standalone script that must be run manually by administrators.
It is NOT a bot command for enhanced security.

Usage:
    uv run python broadcast.py "Your message to all users"

Example:
    uv run python broadcast.py "Manutenzione programmata domani alle 14:00"
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime

from dotenv import load_dotenv

import database
from config import get_config
from utils.logging_config import setup_rotating_file_handler
from utils.retry import httpx_post_with_retry

# Load environment variables
load_dotenv()

# Configure logging with shared utility
cfg = get_config()
file_handler = setup_rotating_file_handler(
    "data/broadcast.log",
    format_string="%(asctime)s - %(levelname)s - %(message)s",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        file_handler,
    ],
)
logger = logging.getLogger(__name__)


async def send_message_to_user(user_id: int, message: str) -> bool:
    """
    Send a message to a specific user via Telegram Bot API.

    Uses retry with exponential backoff for transient network errors.

    Args:
        user_id: Telegram user ID
        message: Message text to send (HTML format - use <b>, <i>, <code> tags)

    Returns:
        True if message was sent successfully, False otherwise
    """
    url = f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": message,
        "parse_mode": "HTML",
    }

    response = await httpx_post_with_retry(url, payload, timeout=10.0)

    if response is None:
        logger.error(f"Failed to send to user {user_id}: request failed after retries")
        return False

    if response.status_code == 200:
        return True
    else:
        logger.warning(
            f"Failed to send to user {user_id}: HTTP {response.status_code} - {response.text}"
        )
        return False


async def broadcast_message(message: str) -> tuple[int, int]:
    """
    Broadcast a message to all registered users.

    Uses a semaphore to limit concurrent Telegram API calls within each batch,
    preventing burst rate limiting violations.

    Args:
        message: Message text to broadcast (HTML format - use <b>, <i>, <code> tags)

    Returns:
        Tuple of (sent_count, failed_count)
    """
    # Get all users
    users = await database.get_all_users()
    total_users = len(users)

    if total_users == 0:
        logger.warning("No users found in database")
        return 0, 0

    logger.info(f"Starting broadcast to {total_users} users")
    logger.info(f"Message: {message[:100]}{'...' if len(message) > 100 else ''}")

    sent_count = 0
    failed_count = 0

    # Semaphore to limit concurrent Telegram API calls
    semaphore = asyncio.Semaphore(cfg.max_concurrent_telegram_calls)

    async def send_with_semaphore(user_id: int) -> bool:
        async with semaphore:
            return await send_message_to_user(user_id, message)

    # Process users in batches
    for i in range(0, total_users, cfg.batch_size):
        batch = users[i : i + cfg.batch_size]
        batch_results = await asyncio.gather(
            *[send_with_semaphore(user["user_id"]) for user in batch],
            return_exceptions=True,
        )

        # Count successes and failures
        for result in batch_results:
            if isinstance(result, Exception):
                failed_count += 1
            elif result:
                sent_count += 1
            else:
                failed_count += 1

        # Log progress
        progress = min(i + cfg.batch_size, total_users)
        percentage = (progress / total_users) * 100
        logger.info(f"Progress: {progress}/{total_users} ({percentage:.0f}%)")

        # Rate limiting: wait between batches (except for last batch)
        if i + cfg.batch_size < total_users:
            await asyncio.sleep(cfg.delay_between_batches)

    logger.info(f"Broadcast completed: {sent_count} sent, {failed_count} failed")
    return sent_count, failed_count


async def main():  # pragma: no cover
    """Main function."""
    # Check if cfg.telegram_token is set
    if not cfg.telegram_token:
        logger.error("cfg.telegram_token not found in environment variables")
        sys.exit(1)

    # Check if cfg.admin_user_id is set
    if not cfg.admin_user_id:
        logger.error("cfg.admin_user_id not found in environment variables")
        sys.exit(1)

    # Check command line arguments
    if len(sys.argv) < 2:
        print('Usage: python broadcast.py "Your message to all users"')
        print('Example: python broadcast.py "Manutenzione programmata domani alle 14:00"')
        sys.exit(1)

    # Get message from command line
    message = " ".join(sys.argv[1:])

    if not message.strip():
        logger.error("Message cannot be empty")
        sys.exit(1)

    # Log broadcast initiation
    logger.info("=" * 80)
    logger.info(f"Broadcast initiated at {datetime.now(UTC).isoformat()}")
    logger.info(f"Admin user ID: {cfg.admin_user_id}")
    logger.info("=" * 80)

    # Initialize database
    await database.init_db()

    # Perform broadcast
    try:
        sent, failed = await broadcast_message(message)

        # Final summary
        logger.info("=" * 80)
        logger.info("BROADCAST SUMMARY")
        logger.info(f"Total sent: {sent}")
        logger.info(f"Total failed: {failed}")
        logger.info(
            f"Success rate: {(sent / (sent + failed) * 100):.1f}%" if (sent + failed) > 0 else "N/A"
        )
        logger.info("=" * 80)

        if failed > 0:
            logger.warning(f"{failed} messages failed to send. Check logs for details.")

    except KeyboardInterrupt:
        logger.warning("Broadcast interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Broadcast failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
