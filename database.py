"""Database operations for RepackIt bot."""

import logging
import os
from datetime import date, datetime
from typing import Optional

import aiosqlite

# Configure logging
logger = logging.getLogger(__name__)

# Get database path from environment
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/users.db")


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
                asin TEXT NOT NULL,
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

        # Create indexes for performance
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_products ON products(user_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_return_deadline ON products(return_deadline)"
        )

        await db.commit()
        logger.info(f"Database initialized at {DATABASE_PATH}")


# ============================================================================
# User operations
# ============================================================================


async def add_user(user_id: int, language_code: Optional[str] = None) -> None:
    """
    Add a new user to the database.

    Args:
        user_id: Telegram user ID
        language_code: User's language code (e.g., "it", "en")
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, language_code)
            VALUES (?, ?)
            """,
            (user_id, language_code),
        )
        await db.commit()
        logger.info(f"User {user_id} added to database")


async def get_user(user_id: int) -> Optional[dict]:
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
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
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


# ============================================================================
# Product operations
# ============================================================================


async def add_product(
    user_id: int,
    asin: str,
    price_paid: float,
    return_deadline: date,
    min_savings_threshold: float = 0,
) -> int:
    """
    Add a new product to monitor.

    Args:
        user_id: Telegram user ID
        asin: Amazon Standard Identification Number
        price_paid: Price user paid for the product (€)
        return_deadline: Last day to return the product
        min_savings_threshold: Minimum € savings to notify (optional)

    Returns:
        Product ID (database auto-increment ID)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO products (user_id, asin, price_paid, return_deadline, min_savings_threshold)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, asin, price_paid, return_deadline.isoformat(), min_savings_threshold),
        )
        await db.commit()
        product_id = cursor.lastrowid
        logger.info(f"Product {asin} added for user {user_id} (ID: {product_id})")
        return product_id


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
        List of product dicts where return_deadline >= today
    """
    today = date.today().isoformat()
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
    price_paid: Optional[float] = None,
    return_deadline: Optional[date] = None,
    min_savings_threshold: Optional[float] = None,
) -> bool:
    """
    Update product fields.

    Args:
        product_id: Database product ID
        price_paid: New price paid (optional)
        return_deadline: New return deadline (optional)
        min_savings_threshold: New savings threshold (optional)

    Returns:
        True if product was updated, False if not found
    """
    updates = []
    params = []

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

    params.append(product_id)
    query = f"UPDATE products SET {', '.join(updates)} WHERE id = ?"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(query, params)
        await db.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Product {product_id} updated")
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


async def delete_product(product_id: int) -> bool:
    """
    Delete a product from monitoring.

    Args:
        product_id: Database product ID

    Returns:
        True if product was deleted, False if not found
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Product {product_id} deleted")
        return deleted


async def delete_expired_products() -> int:
    """
    Delete all products where return_deadline < today.

    Returns:
        Number of products deleted
    """
    today = date.today().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM products WHERE return_deadline < ?", (today,)
        )
        await db.commit()
        count = cursor.rowcount
        logger.info(f"Deleted {count} expired products")
        return count


# ============================================================================
# Feedback operations
# ============================================================================


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
        async with db.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
