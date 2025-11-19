"""Product cleanup script - removes expired products from database."""

import asyncio
import logging
from datetime import UTC, datetime

import database

# Configure logging
logger = logging.getLogger(__name__)


async def cleanup_expired_products() -> dict:
    """
    Remove all products with expired return deadlines.

    This function should be run daily via scheduler to clean up the database.
    It deletes all products where return_deadline < today.

    Returns:
        Dict with statistics:
        - deleted: Number of products deleted
        - timestamp: ISO timestamp of cleanup execution
    """
    logger.info("Starting product cleanup")

    try:
        # Delete expired products
        deleted_count = await database.delete_expired_products()

        # Update system status for health check
        timestamp = datetime.now(UTC).isoformat()
        await database.update_system_status("last_cleanup_run", timestamp)

        logger.info(f"Cleanup completed: {deleted_count} expired products removed")

        return {
            "deleted": deleted_count,
            "timestamp": timestamp,
        }

    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # Setup logging for manual testing
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Load environment variables
    from dotenv import load_dotenv

    load_dotenv()

    # Initialize database
    asyncio.run(database.init_db())

    # Run cleanup
    print("Running product cleanup...")
    result = asyncio.run(cleanup_expired_products())

    print("\nResults:")
    print(f"  Products deleted: {result['deleted']}")
    print(f"  Timestamp: {result['timestamp']}")
