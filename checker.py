"""Price checker and notification sender."""

import asyncio
import logging
import os
from datetime import UTC, date, datetime

from telegram import Bot
from telegram.error import TelegramError

import database
from data_reader import build_affiliate_url, scrape_prices

# Configure logging
logger = logging.getLogger(__name__)

# Get bot token from environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# Rate limiting configuration (to avoid Telegram bans)
NOTIFICATION_BATCH_SIZE = 10  # Send max 10 notifications at once
DELAY_BETWEEN_BATCHES = 1.0  # 1 second delay between batches


async def _send_notification_safe(bot: Bot, notif: dict) -> bool:
    """
    Safely send a notification, catching exceptions and returning success status.

    Args:
        bot: Telegram Bot instance
        notif: Notification dict with keys: user_id, asin, marketplace, current_price,
               price_paid, savings, return_deadline

    Returns:
        True if notification was sent successfully, False otherwise
    """
    try:
        await send_price_drop_notification(
            bot=bot,
            user_id=notif["user_id"],
            asin=notif["asin"],
            marketplace=notif["marketplace"],
            current_price=notif["current_price"],
            price_paid=notif["price_paid"],
            savings=notif["savings"],
            return_deadline=notif["return_deadline"],
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send notification to user {notif['user_id']}: {e}", exc_info=False)
        return False


def _should_notify(
    product_id: int,
    current_price: float,
    price_paid: float,
    min_savings: float,
    last_notified: float | None,
) -> tuple[bool, float]:
    """
    Check if a product should trigger a notification.

    Args:
        product_id: Database product ID
        current_price: Current scraped price
        price_paid: Price user paid
        min_savings: Minimum savings threshold
        last_notified: Last notified price (or None)

    Returns:
        Tuple of (should_notify: bool, savings: float)
    """
    # Check if price dropped
    if current_price >= price_paid:
        logger.debug(
            f"Product {product_id}: current price (€{current_price}) "
            f">= paid (€{price_paid}), no notification"
        )
        return False, 0.0

    # Calculate savings
    savings = price_paid - current_price

    # Check if savings meets threshold
    if savings < min_savings:
        logger.debug(
            f"Product {product_id}: savings (€{savings}) "
            f"< threshold (€{min_savings}), no notification"
        )
        return False, savings

    # Check if we should notify (new price lower than last notified)
    if last_notified is not None and current_price >= last_notified:
        logger.debug(
            f"Product {product_id}: current price (€{current_price}) "
            f">= last notified (€{last_notified}), no notification"
        )
        return False, savings

    return True, savings


async def _process_product_price_check(
    product: dict, current_prices: dict
) -> tuple[dict | None, dict | None]:
    """
    Process a single product for price checking.

    Returns:
        Tuple of (price_drop_notification, unavailable_notification)
        Either can be None if no notification needed.
    """
    product_id = product["id"]
    user_id = product["user_id"]
    asin = product["asin"]
    price_paid = product["price_paid"]
    return_deadline = date.fromisoformat(product["return_deadline"])
    min_savings = product["min_savings_threshold"] or 0
    last_notified = product["last_notified_price"]
    marketplace = product.get("marketplace", "it")
    consecutive_failures = product.get("consecutive_failures", 0)

    current_price = current_prices.get(product_id)

    # Handle scraping failure
    if current_price is None:
        new_failure_count = await database.increment_consecutive_failures(product_id)
        logger.debug(
            f"No price data for product {product_id} (ASIN: {asin}), "
            f"consecutive failures: {new_failure_count}"
        )

        if new_failure_count == 3:
            return None, {
                "user_id": user_id,
                "asin": asin,
                "marketplace": marketplace,
                "return_deadline": return_deadline,
            }
        return None, None

    # Scraping succeeded - reset failures if needed
    if consecutive_failures > 0:
        await database.reset_consecutive_failures(product_id)
        logger.debug(f"Product {product_id} scraped successfully, failures reset")

    # Check if we should notify about price drop
    should_notify, savings = _should_notify(
        product_id, current_price, price_paid, min_savings, last_notified
    )

    if should_notify:
        return {
            "product_id": product_id,
            "user_id": user_id,
            "asin": asin,
            "marketplace": marketplace,
            "current_price": current_price,
            "price_paid": price_paid,
            "savings": savings,
            "return_deadline": return_deadline,
        }, None

    return None, None


async def _send_price_drop_notifications_batch(bot: Bot, notifications: list) -> dict:
    """
    Send price drop notifications in batches and update database.

    Args:
        bot: Telegram Bot instance
        notifications: List of price drop notification dicts

    Returns:
        Dict with 'sent' and 'errors' counts
    """
    stats = {"sent": 0, "errors": 0}

    for i in range(0, len(notifications), NOTIFICATION_BATCH_SIZE):
        batch = notifications[i : i + NOTIFICATION_BATCH_SIZE]

        # Send batch concurrently
        batch_results = await asyncio.gather(
            *[_send_notification_safe(bot, notif) for notif in batch],
            return_exceptions=True,
        )

        # Process results
        for j, result in enumerate(batch_results):
            notif = batch[j]

            if isinstance(result, Exception):
                logger.error(
                    f"Error notifying user {notif['user_id']} for product "
                    f"{notif['product_id']}: {result}"
                )
                stats["errors"] += 1
            elif result:
                # Success: update last_notified_price
                await database.update_last_notified_price(
                    notif["product_id"], notif["current_price"]
                )
                stats["sent"] += 1
                logger.info(
                    f"Notification sent to user {notif['user_id']} for product "
                    f"{notif['product_id']} (€{notif['savings']:.2f} savings)"
                )
            else:
                stats["errors"] += 1

        # Rate limiting between batches
        if i + NOTIFICATION_BATCH_SIZE < len(notifications):
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    return stats


async def _send_notifications_in_batches(bot: Bot, notifications: list, notification_type: str):
    """
    Send unavailable product notifications in batches with rate limiting.

    Args:
        bot: Telegram Bot instance
        notifications: List of notification dicts
        notification_type: Type of notification (currently only "unavailable" supported)
    """
    stats = {"sent": 0, "errors": 0}

    for i in range(0, len(notifications), NOTIFICATION_BATCH_SIZE):
        batch = notifications[i : i + NOTIFICATION_BATCH_SIZE]

        batch_results = await asyncio.gather(
            *[
                send_unavailable_notification(
                    bot,
                    notif["user_id"],
                    notif["asin"],
                    notif["marketplace"],
                    notif["return_deadline"],
                )
                for notif in batch
            ],
            return_exceptions=True,
        )

        # Process results
        for result in batch_results:
            if isinstance(result, Exception):
                logger.error(f"Error sending {notification_type} notification: {result}")
                stats["errors"] += 1
            else:
                stats["sent"] += 1

        # Rate limiting between batches
        if i + NOTIFICATION_BATCH_SIZE < len(notifications):
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    return stats


async def check_and_notify() -> dict:
    """
    Check all active products for price drops and send notifications.

    This is the main function that orchestrates the checking process:
    1. Get all active products from database
    2. Scrape current prices from Amazon
    3. Compare with prices paid
    4. Send notifications for significant drops
    5. Update last_notified_price

    Returns:
        Dict with statistics:
        - total_products: Total products checked
        - scraped: Successfully scraped prices
        - notifications_sent: Notifications sent to users
        - errors: Number of errors encountered
    """
    logger.info("Starting price check process")

    stats = {"total_products": 0, "scraped": 0, "notifications_sent": 0, "errors": 0}

    try:
        # Get all active products
        products = await database.get_all_active_products()
        stats["total_products"] = len(products)

        if not products:
            logger.info("No active products to check")
            return stats

        logger.info(f"Checking {len(products)} active products")

        # Scrape current prices
        current_prices = await scrape_prices(products)
        stats["scraped"] = len(current_prices)
        logger.info(f"Successfully scraped {len(current_prices)}/{len(products)} prices")

        # Check if Telegram token is set
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN not set, cannot send notifications")
            stats["errors"] += 1
            return stats

        bot = Bot(token=TELEGRAM_TOKEN)

        # Process each product and collect notifications
        price_drop_notifications = []
        unavailable_notifications = []

        for product in products:
            price_drop, unavailable = await _process_product_price_check(product, current_prices)
            if price_drop:
                price_drop_notifications.append(price_drop)
            if unavailable:
                unavailable_notifications.append(unavailable)

        # Send price drop notifications
        logger.info(f"Found {len(price_drop_notifications)} price drop notifications to send")
        if price_drop_notifications:
            result_stats = await _send_price_drop_notifications_batch(bot, price_drop_notifications)
            stats["notifications_sent"] += result_stats["sent"]
            stats["errors"] += result_stats["errors"]

        # Send unavailable product notifications
        logger.info(
            f"Found {len(unavailable_notifications)} unavailable product notifications to send"
        )
        if unavailable_notifications:
            result_stats = await _send_notifications_in_batches(
                bot, unavailable_notifications, "unavailable"
            )
            stats["notifications_sent"] += result_stats["sent"]
            stats["errors"] += result_stats["errors"]

        # Update system status
        await database.update_system_status("last_checker_run", datetime.now(UTC).isoformat())

        logger.info(
            f"Price check completed: {stats['notifications_sent']} notifications sent, "
            f"{stats['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Error in check_and_notify: {e}", exc_info=True)
        stats["errors"] += 1

    return stats


async def send_price_drop_notification(
    bot: Bot,
    user_id: int,
    asin: str,
    marketplace: str,
    current_price: float,
    price_paid: float,
    savings: float,
    return_deadline: date,
) -> None:
    """
    Send price drop notification to user via Telegram.

    Args:
        bot: Telegram Bot instance
        user_id: Telegram user ID
        asin: Amazon product ASIN
        marketplace: Amazon marketplace (it, com, de, etc.)
        current_price: Current product price
        price_paid: Price user paid
        savings: Amount saved
        return_deadline: Last day to return product

    Raises:
        TelegramError: If notification fails to send
    """
    # Calculate days remaining
    today = date.today()
    days_remaining = (return_deadline - today).days

    # Build affiliate URL
    product_url = build_affiliate_url(asin, marketplace)

    # Format deadline
    deadline_str = return_deadline.strftime("%d/%m/%Y")

    # Build message
    message = (
        "🎉 *Prezzo in calo su Amazon!*\n\n"
        f"Il prodotto che stai monitorando è sceso a *€{current_price:.2f}*\n"
        f"Prezzo pagato: €{price_paid:.2f}\n"
        f"💰 Risparmio: *€{savings:.2f}*\n\n"
        f"📅 Scadenza reso: {deadline_str}"
    )

    # Add days remaining info
    if days_remaining > 0:
        message += f" (tra {days_remaining} giorni)"
    elif days_remaining == 0:
        message += " (*oggi*)"
    else:
        message += " (*scaduto*)"

    message += f"\n\n🔗 [Vai al prodotto]({product_url})"

    # Send message
    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=False,
        )
    except TelegramError as e:
        logger.error(f"Failed to send message to user {user_id}: {e}")
        raise


async def send_unavailable_notification(
    bot: Bot,
    user_id: int,
    asin: str,
    marketplace: str,
    return_deadline: date,
) -> None:
    """
    Send notification about potentially unavailable product.

    Args:
        bot: Telegram Bot instance
        user_id: Telegram user ID
        asin: Amazon product ASIN
        marketplace: Amazon marketplace (it, com, de, etc.)
        return_deadline: Last day to return product

    Raises:
        TelegramError: If notification fails to send
    """
    # Build affiliate URL
    product_url = build_affiliate_url(asin, marketplace)

    # Calculate days remaining
    today = date.today()
    days_remaining = (return_deadline - today).days
    deadline_str = return_deadline.strftime("%d/%m/%Y")

    # Build message
    message = (
        "⚠️ *Prodotto non disponibile*\n\n"
        "Non sono riuscito a recuperare il prezzo del prodotto che stai monitorando "
        "per 3 volte consecutive.\n\n"
        "Il prodotto potrebbe essere:\n"
        "• Temporaneamente non disponibile\n"
        "• Rimosso da Amazon\n"
        "• Bloccato geograficamente\n\n"
        f"📅 Scadenza reso: {deadline_str}"
    )

    # Add days remaining info
    if days_remaining > 0:
        message += f" (tra {days_remaining} giorni)"
    elif days_remaining == 0:
        message += " (*oggi*)"
    else:
        message += " (*scaduto*)"

    message += (
        f"\n\n🔗 [Controlla il prodotto]({product_url})\n\n"
        "_Continuerò a monitorarlo. Se il prezzo torna disponibile, riceverai una notifica._"
    )

    # Send message
    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=False,
        )
    except TelegramError as e:
        logger.error(f"Failed to send unavailable notification to user {user_id}: {e}")
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

    # Run checker
    print("Running price checker...")
    stats = asyncio.run(check_and_notify())

    print("\nResults:")
    print(f"  Total products: {stats['total_products']}")
    print(f"  Prices scraped: {stats['scraped']}")
    print(f"  Notifications sent: {stats['notifications_sent']}")
    print(f"  Errors: {stats['errors']}")
