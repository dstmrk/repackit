"""Database operations for RepackIt bot."""

import logging
import os
from datetime import UTC, date, datetime

import aiosqlite

from config import get_config

# Configure logging
logger = logging.getLogger(__name__)

# Load configuration
cfg = get_config()

# Database path and product limits (module-level constants for backward compatibility)
DATABASE_PATH = cfg.database_path
DEFAULT_MAX_PRODUCTS = cfg.default_max_products
INITIAL_MAX_PRODUCTS = cfg.initial_max_products
PRODUCTS_PER_REFERRAL = cfg.products_per_referral
INVITED_USER_BONUS = cfg.invited_user_bonus


async def init_db() -> None:
    """
    Initialize database with required tables.

    Creates users, products, and feedback tables if they don't exist.
    Also creates indexes for optimized queries.
    """
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Enable WAL mode for better concurrency
        await db.execute("PRAGMA journal_mode=WAL")

        # Users table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language_code TEXT,
                max_products INTEGER DEFAULT NULL,
                referred_by INTEGER DEFAULT NULL,
                referral_bonus_given BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Products table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_name TEXT,
                asin TEXT NOT NULL,
                marketplace TEXT NOT NULL DEFAULT 'it',
                price_paid REAL NOT NULL,
                return_deadline DATE NOT NULL,
                min_savings_threshold REAL DEFAULT 0,
                last_notified_price REAL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )

        # Feedback table
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )

        # System status table (for health checks)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS system_status (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_products ON products(user_id)")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_return_deadline ON products(return_deadline)"
        )

        # Composite indexes for common query patterns
        # Scraper queries products by (asin, marketplace) - avoids full table scan
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_asin_marketplace ON products(asin, marketplace)"
        )
        # Cleanup and filtered queries use (user_id, return_deadline)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_deadline ON products(user_id, return_deadline)"
        )

        # Create trigger to enforce product limit at database level
        # This prevents race conditions where concurrent requests could bypass application-level checks
        await db.execute("DROP TRIGGER IF EXISTS check_product_limit_before_insert")
        await db.execute(
            f"""
            CREATE TRIGGER check_product_limit_before_insert
            BEFORE INSERT ON products
            FOR EACH ROW
            BEGIN
                SELECT CASE
                    WHEN (
                        SELECT COUNT(*) FROM products WHERE user_id = NEW.user_id
                    ) >= (
                        SELECT COALESCE(max_products, {DEFAULT_MAX_PRODUCTS})
                        FROM users WHERE user_id = NEW.user_id
                    )
                    THEN RAISE(ABORT, 'Product limit exceeded')
                END;
            END
            """
        )

        await db.commit()
        logger.info(f"Database initialized at {DATABASE_PATH}")


# ============================================================================
# User operations
# ============================================================================


async def add_user(
    user_id: int, language_code: str | None = None, referred_by: int | None = None
) -> None:
    """
    Add a new user to the database.

    Args:
        user_id: Telegram user ID
        language_code: User's language code (e.g., "it", "en")
        referred_by: User ID of the referrer (optional)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, language_code, referred_by)
            VALUES (?, ?, ?)
            """,
            (user_id, language_code, referred_by),
        )
        await db.commit()
        if referred_by:
            logger.info(f"User {user_id} added to database (referred by {referred_by})")
        else:
            logger.info(f"User {user_id} added to database")


async def get_user(user_id: int) -> dict | None:
    """
    Get user information from database.

    Args:
        user_id: Telegram user ID

    Returns:
        User dict with keys: user_id, language_code, created_at
        None if user doesn't exist
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_users() -> list[dict]:
    """
    Get all users from database.

    Returns:
        List of user dicts with keys: user_id, language_code, created_at
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_user_product_limit(user_id: int) -> int:
    """
    Get product limit for a specific user.

    Args:
        user_id: Telegram user ID

    Returns:
        Product limit for this user.
        - If max_products is NULL: returns DEFAULT_MAX_PRODUCTS (21, for admin/special users)
        - If max_products is set: returns that value (personalized limit)
        - If user doesn't exist: returns INITIAL_MAX_PRODUCTS (3, for new users)
    """
    user = await get_user(user_id)
    if not user:
        return INITIAL_MAX_PRODUCTS

    # NULL means admin/special user with max limit
    if user["max_products"] is None:
        return DEFAULT_MAX_PRODUCTS

    return user["max_products"]


async def set_user_max_products(user_id: int, limit: int) -> None:
    """
    Set product limit for a specific user.

    Args:
        user_id: Telegram user ID
        limit: New product limit (capped at DEFAULT_MAX_PRODUCTS)
    """
    # Cap at DEFAULT_MAX_PRODUCTS
    limit = min(limit, DEFAULT_MAX_PRODUCTS)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET max_products = ? WHERE user_id = ?",
            (limit, user_id),
        )
        await db.commit()
        logger.info(f"User {user_id} max_products set to {limit}")


async def increment_user_product_limit(user_id: int, amount: int) -> int:
    """
    Increment user's product limit by the specified amount (capped at DEFAULT_MAX_PRODUCTS).

    Args:
        user_id: Telegram user ID
        amount: Amount to increment by (typically PRODUCTS_PER_REFERRAL = 3)

    Returns:
        New product limit after increment
    """
    current_limit = await get_user_product_limit(user_id)
    new_limit = min(current_limit + amount, DEFAULT_MAX_PRODUCTS)

    await set_user_max_products(user_id, new_limit)
    logger.info(f"User {user_id} product limit incremented by {amount} (now {new_limit})")
    return new_limit


async def mark_referral_bonus_given(user_id: int) -> None:
    """
    Mark that the referral bonus has been given for this user.

    This prevents giving the bonus multiple times if the user adds/removes/readds products.

    Args:
        user_id: Telegram user ID
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET referral_bonus_given = TRUE WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
        logger.info(f"User {user_id} marked as referral bonus given")


# ============================================================================
# Product operations
# ============================================================================


async def add_product(
    user_id: int,
    product_name: str | None,
    asin: str,
    marketplace: str,
    price_paid: float,
    return_deadline: date,
    min_savings_threshold: float = 0,
) -> int:
    """
    Add a new product to monitor.

    Args:
        user_id: Telegram user ID
        product_name: User-defined product name for easy identification
        asin: Amazon Standard Identification Number
        marketplace: Amazon marketplace (it, com, de, fr, etc.)
        price_paid: Price user paid for the product (€)
        return_deadline: Last day to return the product
        min_savings_threshold: Minimum € savings to notify (optional)

    Returns:
        Product ID (database auto-increment ID)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO products (
                user_id, product_name, asin, marketplace, price_paid,
                return_deadline, min_savings_threshold
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                product_name,
                asin,
                marketplace,
                price_paid,
                return_deadline.isoformat(),
                min_savings_threshold,
            ),
        )
        await db.commit()
        product_id = cursor.lastrowid
        product_display = product_name or f"ASIN {asin}"
        logger.info(
            f"Product '{product_display}' from amazon.{marketplace} added for user {user_id} "
            f"(ID: {product_id})"
        )
        return product_id


async def add_product_atomic(
    user_id: int,
    product_name: str | None,
    asin: str,
    marketplace: str,
    price_paid: float,
    return_deadline: date,
    min_savings_threshold: float = 0,
) -> tuple[int, bool]:
    """
    Add a new product to monitor with atomic first-product check.

    This function uses a database transaction to atomically:
    1. Count existing products for the user
    2. Insert the new product
    3. Return both the product ID and whether this was the first product

    This prevents race conditions where multiple concurrent requests could
    both think they're adding the "first product" and trigger duplicate
    referral bonuses.

    Args:
        user_id: Telegram user ID
        product_name: User-defined product name for easy identification
        asin: Amazon Standard Identification Number
        marketplace: Amazon marketplace (it, com, de, fr, etc.)
        price_paid: Price user paid for the product (€)
        return_deadline: Last day to return the product
        min_savings_threshold: Minimum € savings to notify (optional)

    Returns:
        Tuple of (product_id, is_first_product)
        - product_id: Database auto-increment ID
        - is_first_product: True if this was the user's first product, False otherwise

    Example:
        >>> product_id, is_first = await add_product_atomic(123, "iPhone", ...)
        >>> if is_first:
        >>>     await give_referral_bonus(...)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Start IMMEDIATE transaction to lock the database for writing
        await db.execute("BEGIN IMMEDIATE")

        try:
            # Step 1: Count existing products (inside transaction)
            cursor = await db.execute(
                "SELECT COUNT(*) FROM products WHERE user_id = ?",
                (user_id,),
            )
            product_count_before = (await cursor.fetchone())[0]
            is_first_product = product_count_before == 0

            # Step 2: Insert new product (inside same transaction)
            cursor = await db.execute(
                """
                INSERT INTO products (
                    user_id, product_name, asin, marketplace, price_paid,
                    return_deadline, min_savings_threshold
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    product_name,
                    asin,
                    marketplace,
                    price_paid,
                    return_deadline.isoformat(),
                    min_savings_threshold,
                ),
            )

            # Step 3: Commit transaction atomically
            await db.commit()

            product_id = cursor.lastrowid
            product_display = product_name or f"ASIN {asin}"

            logger.info(
                f"Product '{product_display}' from amazon.{marketplace} added for user {user_id} "
                f"(ID: {product_id}, first_product: {is_first_product})"
            )

            return product_id, is_first_product

        except Exception as e:
            # Rollback on any error
            await db.rollback()
            logger.error(f"Error in add_product_atomic for user {user_id}: {e}", exc_info=True)
            raise


async def get_user_products(user_id: int) -> list[dict]:
    """
    Get all products monitored by a user.

    Args:
        user_id: Telegram user ID

    Returns:
        List of product dicts with all fields
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM products
            WHERE user_id = ?
            ORDER BY added_at DESC
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_active_products() -> list[dict]:
    """
    Get all products that haven't expired yet.

    Returns:
        List of product dicts where return_deadline >= today (UTC)
    """
    today = datetime.now(UTC).date().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM products
            WHERE return_deadline >= ?
            ORDER BY user_id, added_at
            """,
            (today,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def update_product(
    product_id: int,
    user_id: int,
    product_name: str | None = None,
    price_paid: float | None = None,
    return_deadline: date | None = None,
    min_savings_threshold: float | None = None,
) -> bool:
    """
    Update product fields.

    Defense-in-depth: requires both product_id and user_id to match,
    preventing accidental modification of other users' products even if
    a bug in the handler passes an incorrect product_id.

    Args:
        product_id: Database product ID
        user_id: Telegram user ID (owner of the product)
        product_name: New product name (optional)
        price_paid: New price paid (optional)
        return_deadline: New return deadline (optional)
        min_savings_threshold: New savings threshold (optional)

    Returns:
        True if product was updated, False if not found or not owned by user
    """
    updates = []
    params = []

    if product_name is not None:
        updates.append("product_name = ?")
        params.append(product_name)

    if price_paid is not None:
        updates.append("price_paid = ?")
        params.append(price_paid)

    if return_deadline is not None:
        updates.append("return_deadline = ?")
        params.append(return_deadline.isoformat())

    if min_savings_threshold is not None:
        updates.append("min_savings_threshold = ?")
        params.append(min_savings_threshold)

    if not updates:
        return False

    params.extend([product_id, user_id])
    query = f"UPDATE products SET {', '.join(updates)} WHERE id = ? AND user_id = ?"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(query, params)
        await db.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Product {product_id} updated for user {user_id}")
        return updated


async def update_last_notified_price(product_id: int, price: float) -> None:
    """
    Update the last notified price for a product.

    Args:
        product_id: Database product ID
        price: Price that was notified to user
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE products SET last_notified_price = ? WHERE id = ?",
            (price, product_id),
        )
        await db.commit()
        logger.debug(f"Product {product_id} last_notified_price updated to {price}")


async def delete_product(product_id: int, user_id: int) -> bool:
    """
    Delete a product from monitoring.

    Defense-in-depth: requires both product_id and user_id to match,
    preventing accidental deletion of other users' products even if
    a bug in the handler passes an incorrect product_id.

    Args:
        product_id: Database product ID
        user_id: Telegram user ID (owner of the product)

    Returns:
        True if product was deleted, False if not found or not owned by user
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM products WHERE id = ? AND user_id = ?",
            (product_id, user_id),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Product {product_id} deleted for user {user_id}")
        return deleted


async def delete_expired_products() -> int:
    """
    Delete all products where return_deadline < today (UTC).

    Returns:
        Number of products deleted
    """
    today = datetime.now(UTC).date().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM products WHERE return_deadline < ?", (today,))
        await db.commit()
        count = cursor.rowcount
        logger.info(f"Deleted {count} expired products")
        return count


# ============================================================================
# Feedback operations
# ============================================================================


async def get_last_feedback_time(user_id: int) -> str | None:
    """
    Get timestamp of user's last feedback submission.

    Args:
        user_id: Telegram user ID

    Returns:
        ISO timestamp string of last feedback, or None if user never submitted feedback
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT created_at FROM feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def add_feedback(user_id: int, message: str) -> int:
    """
    Add user feedback to database.

    Args:
        user_id: Telegram user ID
        message: Feedback message

    Returns:
        Feedback ID
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO feedback (user_id, message) VALUES (?, ?)",
            (user_id, message),
        )
        await db.commit()
        feedback_id = cursor.lastrowid
        logger.info(f"Feedback {feedback_id} added from user {user_id}")
        return feedback_id


async def get_all_feedback() -> list[dict]:
    """
    Get all feedback from database.

    Returns:
        List of feedback dicts with keys: id, user_id, message, created_at
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM feedback ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ============================================================================
# System status operations (for health checks)
# ============================================================================


async def update_system_status(key: str, value: str) -> None:
    """
    Update system status key-value pair.

    Args:
        key: Status key (e.g., "last_scraper_run", "last_checker_run")
        value: Status value (typically ISO timestamp)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO system_status (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        await db.commit()
        logger.debug(f"System status updated: {key} = {value}")


async def get_system_status(key: str) -> dict | None:
    """
    Get system status value.

    Args:
        key: Status key

    Returns:
        Dict with keys: key, value, updated_at
        None if key doesn't exist
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM system_status WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_system_status() -> dict[str, dict]:
    """
    Get all system status entries.

    Returns:
        Dict mapping keys to their status dicts
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM system_status") as cursor:
            rows = await cursor.fetchall()
            return {row["key"]: dict(row) for row in rows}


async def increment_metric(key: str, amount: float = 1.0) -> None:
    """
    Increment a metric counter in system_status atomically.

    If the key doesn't exist, it will be created with the initial value.
    If it exists, the amount will be added to the current value.

    This operation is atomic - it uses a single SQL statement to avoid
    race conditions that could occur with separate read-then-write operations.

    Args:
        key: Metric key (e.g., "products_total_count", "total_savings_generated")
        amount: Amount to increment by (default: 1.0)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Atomic increment using ON CONFLICT DO UPDATE
        # - If key doesn't exist: INSERT with amount as initial value
        # - If key exists: UPDATE by adding amount to current value
        # This is a single atomic SQL operation, no race condition possible
        await db.execute(
            """
            INSERT INTO system_status (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = CAST(system_status.value AS REAL) + CAST(excluded.value AS REAL),
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, str(amount)),
        )
        await db.commit()
        logger.debug(f"Metric incremented: {key} += {amount}")


async def get_metric(key: str) -> float:
    """
    Get a metric counter value from system_status.

    Args:
        key: Metric key (e.g., "products_total_count", "total_savings_generated")

    Returns:
        Metric value as float, or 0.0 if key doesn't exist
    """
    status = await get_system_status(key)
    if status is None:
        return 0.0
    try:
        return float(status["value"])
    except (ValueError, TypeError):
        logger.warning(f"Invalid metric value for {key}: {status['value']}")
        return 0.0


async def get_stats() -> dict:
    """
    Get database statistics for health check.

    Returns:
        Dict with keys: user_count, product_count, unique_product_count,
        products_total_count, total_savings_generated

        - product_count: Total products in database (includes duplicates)
        - unique_product_count: Unique products by (asin, marketplace) pair
          This reflects how many products the scraper actually processes,
          since duplicate ASINs are deduplicated during scraping.
        - products_total_count: Total products registered since beginning (promotional metric)
        - total_savings_generated: Total € savings notified to users (promotional metric)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Count users
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            user_count = (await cursor.fetchone())[0]

        # Count total products (includes duplicates)
        async with db.execute("SELECT COUNT(*) FROM products") as cursor:
            product_count = (await cursor.fetchone())[0]

        # Count unique products by (asin, marketplace) pair
        # This matches the scraper's deduplication logic in data_reader.py
        async with db.execute(
            "SELECT COUNT(DISTINCT asin || '|' || marketplace) FROM products"
        ) as cursor:
            unique_product_count = (await cursor.fetchone())[0]

    # Get promotional metrics from system_status
    products_total_count = await get_metric("products_total_count")
    total_savings_generated = await get_metric("total_savings_generated")

    return {
        "user_count": user_count,
        "product_count": product_count,
        "unique_product_count": unique_product_count,
        "products_total_count": int(products_total_count),
        "total_savings_generated": round(total_savings_generated, 2),
    }
