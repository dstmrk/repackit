"""Tests for product_cleanup.py."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import database
import product_cleanup


@pytest.fixture
async def test_db():
    """Create a temporary test database."""
    # Create temporary database file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Override DATABASE_PATH for testing
    original_path = database.DATABASE_PATH
    database.DATABASE_PATH = db_path

    # Initialize database
    await database.init_db()

    yield db_path

    # Cleanup
    database.DATABASE_PATH = original_path
    Path(db_path).unlink(missing_ok=True)
    # Clean up WAL files if they exist
    Path(f"{db_path}-wal").unlink(missing_ok=True)
    Path(f"{db_path}-shm").unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_cleanup_expired_products_with_expired(test_db):
    """Test cleanup when there are expired products."""
    # Create user
    await database.add_user(user_id=123, language_code="it")

    # Create products with different deadlines
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # Add expired product (yesterday)
    await database.add_product(
        user_id=123,
        asin="EXPIRED01",
        price_paid=50.0,
        return_deadline=yesterday,
        min_savings_threshold=0,
    )

    # Add active product (tomorrow)
    await database.add_product(
        user_id=123,
        asin="ACTIVE001",
        price_paid=60.0,
        return_deadline=tomorrow,
        min_savings_threshold=0,
    )

    # Run cleanup
    result = await product_cleanup.cleanup_expired_products()

    # Verify result
    assert result["deleted"] == 1
    assert "timestamp" in result

    # Verify only active product remains
    products = await database.get_user_products(123)
    assert len(products) == 1
    assert products[0]["asin"] == "ACTIVE001"

    # Verify system status was updated
    status = await database.get_all_system_status()
    assert "last_cleanup_run" in status
    assert status["last_cleanup_run"]["value"] == result["timestamp"]


@pytest.mark.asyncio
async def test_cleanup_expired_products_no_expired(test_db):
    """Test cleanup when there are no expired products."""
    # Create user
    await database.add_user(user_id=123, language_code="it")

    # Add only active products
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123,
        asin="ACTIVE001",
        price_paid=50.0,
        return_deadline=tomorrow,
        min_savings_threshold=0,
    )

    # Run cleanup
    result = await product_cleanup.cleanup_expired_products()

    # Verify no products deleted
    assert result["deleted"] == 0
    assert "timestamp" in result

    # Verify product still exists
    products = await database.get_user_products(123)
    assert len(products) == 1


@pytest.mark.asyncio
async def test_cleanup_expired_products_multiple_users(test_db):
    """Test cleanup with multiple users and mixed products."""
    # Create two users
    await database.add_user(user_id=123, language_code="it")
    await database.add_user(user_id=456, language_code="en")

    # Add expired products for both users
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

    await database.add_product(
        user_id=123, asin="EXPIRED01", price_paid=50.0, return_deadline=yesterday
    )
    await database.add_product(
        user_id=123, asin="ACTIVE001", price_paid=60.0, return_deadline=tomorrow
    )
    await database.add_product(
        user_id=456, asin="EXPIRED02", price_paid=70.0, return_deadline=yesterday
    )
    await database.add_product(
        user_id=456, asin="ACTIVE002", price_paid=80.0, return_deadline=tomorrow
    )

    # Run cleanup
    result = await product_cleanup.cleanup_expired_products()

    # Verify 2 expired products deleted
    assert result["deleted"] == 2

    # Verify only active products remain for each user
    products_123 = await database.get_user_products(123)
    assert len(products_123) == 1
    assert products_123[0]["asin"] == "ACTIVE001"

    products_456 = await database.get_user_products(456)
    assert len(products_456) == 1
    assert products_456[0]["asin"] == "ACTIVE002"


@pytest.mark.asyncio
async def test_cleanup_expired_products_empty_database(test_db):
    """Test cleanup with empty database."""
    # Run cleanup on empty database
    result = await product_cleanup.cleanup_expired_products()

    # Verify no products deleted
    assert result["deleted"] == 0
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_cleanup_expired_products_updates_system_status(test_db):
    """Test that cleanup updates system status for health check."""
    # Run cleanup
    result = await product_cleanup.cleanup_expired_products()

    # Verify system status was updated
    status = await database.get_all_system_status()
    assert "last_cleanup_run" in status
    assert status["last_cleanup_run"]["value"] == result["timestamp"]

    # Verify timestamp format (ISO)
    from datetime import datetime

    timestamp = datetime.fromisoformat(result["timestamp"])
    assert timestamp is not None


@pytest.mark.asyncio
async def test_cleanup_error_handling(test_db):
    """Test error handling during cleanup."""
    # Mock database.delete_expired_products to raise an exception
    with patch(
        "product_cleanup.database.delete_expired_products", side_effect=Exception("DB Error")
    ):
        with pytest.raises(Exception, match="DB Error"):
            await product_cleanup.cleanup_expired_products()


@pytest.mark.asyncio
async def test_cleanup_expired_products_boundary_today(test_db):
    """Test that products expiring today are NOT deleted."""
    # Create user
    await database.add_user(user_id=123, language_code="it")

    # Add product expiring today
    today = date.today()
    await database.add_product(
        user_id=123,
        asin="TODAY001",
        price_paid=50.0,
        return_deadline=today,
        min_savings_threshold=0,
    )

    # Run cleanup
    result = await product_cleanup.cleanup_expired_products()

    # Verify product NOT deleted (deadline is today, not before today)
    assert result["deleted"] == 0

    # Verify product still exists
    products = await database.get_user_products(123)
    assert len(products) == 1
    assert products[0]["asin"] == "TODAY001"
