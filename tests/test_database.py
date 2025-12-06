"""Tests for database operations."""

import asyncio
from datetime import date, timedelta

import pytest

import database

# ============================================================================
# Initialization tests
# ============================================================================


@pytest.mark.asyncio
async def test_init_db_creates_tables(test_db):
    """Test that init_db creates all required tables."""
    import aiosqlite

    async with aiosqlite.connect(test_db) as db:
        # Check users table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ) as cursor:
            assert await cursor.fetchone() is not None

        # Check products table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
        ) as cursor:
            assert await cursor.fetchone() is not None

        # Check feedback table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'"
        ) as cursor:
            assert await cursor.fetchone() is not None


@pytest.mark.asyncio
async def test_init_db_creates_indexes(test_db):
    """Test that init_db creates performance indexes."""
    import aiosqlite

    async with aiosqlite.connect(test_db) as db:
        # Check simple indexes exist
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_user_products'"
        ) as cursor:
            assert await cursor.fetchone() is not None

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_return_deadline'"
        ) as cursor:
            assert await cursor.fetchone() is not None

        # Check composite indexes exist (PERF #1)
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_asin_marketplace'"
        ) as cursor:
            assert await cursor.fetchone() is not None

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_user_deadline'"
        ) as cursor:
            assert await cursor.fetchone() is not None


# ============================================================================
# User operation tests
# ============================================================================


@pytest.mark.asyncio
async def test_add_user(test_db):
    """Test adding a user."""
    await database.add_user(123456, "it")

    user = await database.get_user(123456)
    assert user is not None
    assert user["user_id"] == 123456
    assert user["language_code"] == "it"


@pytest.mark.asyncio
async def test_add_user_duplicate_ignores(test_db):
    """Test that adding duplicate user is ignored."""
    await database.add_user(123456, "it")
    await database.add_user(123456, "en")  # Should be ignored

    user = await database.get_user(123456)
    assert user["language_code"] == "it"  # Original value preserved


@pytest.mark.asyncio
async def test_get_user_nonexistent(test_db):
    """Test getting a user that doesn't exist."""
    user = await database.get_user(999999)
    assert user is None


@pytest.mark.asyncio
async def test_get_all_users(test_db):
    """Test getting all users."""
    await database.add_user(111, "it")
    await database.add_user(222, "en")
    await database.add_user(333, "de")

    users = await database.get_all_users()
    assert len(users) == 3
    assert {u["user_id"] for u in users} == {111, 222, 333}


@pytest.mark.asyncio
async def test_get_user_product_limit_nonexistent_user(test_db):
    """Test getting product limit for user that doesn't exist."""
    # Should return INITIAL_MAX_PRODUCTS (5) for non-existent users
    limit = await database.get_user_product_limit(999999)
    assert limit == database.INITIAL_MAX_PRODUCTS


@pytest.mark.asyncio
async def test_get_user_product_limit_null_max_products(test_db):
    """Test getting product limit for user with NULL max_products (admin/VIP)."""
    # Add user without setting max_products (defaults to NULL)
    await database.add_user(111, "it")

    # NULL should return DEFAULT_MAX_PRODUCTS (21)
    limit = await database.get_user_product_limit(111)
    assert limit == database.DEFAULT_MAX_PRODUCTS


@pytest.mark.asyncio
async def test_get_user_product_limit_with_custom_limit(test_db):
    """Test getting product limit for user with custom limit."""
    # Add user and set custom limit
    await database.add_user(111, "it")
    await database.set_user_max_products(111, 10)

    # Should return the custom limit
    limit = await database.get_user_product_limit(111)
    assert limit == 10


@pytest.mark.asyncio
async def test_set_user_max_products(test_db):
    """Test setting user's max products."""
    await database.add_user(111, "it")

    # Set to 10
    await database.set_user_max_products(111, 10)
    limit = await database.get_user_product_limit(111)
    assert limit == 10

    # Update to 15
    await database.set_user_max_products(111, 15)
    limit = await database.get_user_product_limit(111)
    assert limit == 15


@pytest.mark.asyncio
async def test_set_user_max_products_capped_at_default(test_db):
    """Test that set_user_max_products caps at DEFAULT_MAX_PRODUCTS."""
    await database.add_user(111, "it")

    # Try to set to 100 (should be capped to DEFAULT_MAX_PRODUCTS = 21)
    await database.set_user_max_products(111, 100)
    limit = await database.get_user_product_limit(111)
    assert limit == database.DEFAULT_MAX_PRODUCTS


@pytest.mark.asyncio
async def test_increment_user_product_limit(test_db):
    """Test incrementing user's product limit."""
    await database.add_user(111, "it")
    await database.set_user_max_products(111, 6)

    # Increment by 3
    new_limit = await database.increment_user_product_limit(111, 3)
    assert new_limit == 9

    # Verify in database
    limit = await database.get_user_product_limit(111)
    assert limit == 9


@pytest.mark.asyncio
async def test_increment_user_product_limit_capped_at_default(test_db):
    """Test that increment caps at DEFAULT_MAX_PRODUCTS."""
    await database.add_user(111, "it")
    await database.set_user_max_products(111, 19)

    # Try to increment by 5 (should be capped to 21)
    new_limit = await database.increment_user_product_limit(111, 5)
    assert new_limit == database.DEFAULT_MAX_PRODUCTS


@pytest.mark.asyncio
async def test_mark_referral_bonus_given(test_db):
    """Test marking referral bonus as given."""
    await database.add_user(111, "it", referred_by=222)

    # Initially False
    user = await database.get_user(111)
    assert user["referral_bonus_given"] is False or user["referral_bonus_given"] == 0

    # Mark as given
    await database.mark_referral_bonus_given(111)

    # Now True
    user = await database.get_user(111)
    assert user["referral_bonus_given"] is True or user["referral_bonus_given"] == 1


@pytest.mark.asyncio
async def test_add_user_with_referral(test_db):
    """Test adding user with referral."""
    # Add referrer first
    await database.add_user(222, "it")

    # Add referred user
    await database.add_user(111, "it", referred_by=222)

    # Check referred_by is set
    user = await database.get_user(111)
    assert user["referred_by"] == 222
    assert user["referral_bonus_given"] is False or user["referral_bonus_given"] == 0


# ============================================================================
# Product operation tests
# ============================================================================


@pytest.mark.asyncio
async def test_add_product(test_db):
    """Test adding a product."""
    await database.add_user(123456, "it")

    deadline = date.today() + timedelta(days=30)
    product_id = await database.add_product(
        user_id=123456,
        product_name="Test Product",
        asin="B08N5WRWNW",
        marketplace="it",
        price_paid=59.90,
        return_deadline=deadline,
        min_savings_threshold=5.0,
    )

    assert product_id > 0

    products = await database.get_user_products(123456)
    assert len(products) == 1
    assert products[0]["asin"] == "B08N5WRWNW"
    assert products[0]["marketplace"] == "it"
    assert products[0]["price_paid"] == 59.90
    assert products[0]["min_savings_threshold"] == 5.0


@pytest.mark.asyncio
async def test_add_product_atomic_first_product(test_db):
    """Test add_product_atomic correctly identifies first product."""
    await database.add_user(123456, "it")

    deadline = date.today() + timedelta(days=30)

    # First product should return is_first_product=True
    product_id_1, is_first_1 = await database.add_product_atomic(
        user_id=123456,
        product_name="First Product",
        asin="B08N5WRWNW",
        marketplace="it",
        price_paid=59.90,
        return_deadline=deadline,
        min_savings_threshold=5.0,
    )

    assert product_id_1 > 0
    assert is_first_1 is True, "First product should be flagged as first"

    # Second product should return is_first_product=False
    product_id_2, is_first_2 = await database.add_product_atomic(
        user_id=123456,
        product_name="Second Product",
        asin="B09ABC123",
        marketplace="it",
        price_paid=29.90,
        return_deadline=deadline,
        min_savings_threshold=0,
    )

    assert product_id_2 > 0
    assert product_id_2 != product_id_1
    assert is_first_2 is False, "Second product should NOT be flagged as first"

    # Verify both products exist
    products = await database.get_user_products(123456)
    assert len(products) == 2


@pytest.mark.asyncio
async def test_add_product_atomic_concurrent_safety(test_db):
    """Test add_product_atomic prevents race conditions with concurrent inserts."""
    await database.add_user(123456, "it")

    deadline = date.today() + timedelta(days=30)

    # Simulate concurrent requests by calling add_product_atomic multiple times
    # In a real race condition, both might see count=0 and think they're first
    # But with atomic transaction, only the first should get is_first=True

    # Due to SQLite's IMMEDIATE transaction locking, these will be serialized
    # The first to acquire the lock will see count=0, second will see count=1
    results = await asyncio.gather(
        database.add_product_atomic(
            user_id=123456,
            product_name="Concurrent Product 1",
            asin="B08N5WRWNW",
            marketplace="it",
            price_paid=59.90,
            return_deadline=deadline,
            min_savings_threshold=5.0,
        ),
        database.add_product_atomic(
            user_id=123456,
            product_name="Concurrent Product 2",
            asin="B09ABC123",
            marketplace="it",
            price_paid=29.90,
            return_deadline=deadline,
            min_savings_threshold=0,
        ),
    )

    product_id_1, is_first_1 = results[0]
    product_id_2, is_first_2 = results[1]

    # Exactly one should be marked as first
    first_flags = [is_first_1, is_first_2]
    assert sum(first_flags) == 1, "Exactly one product should be flagged as first"
    assert product_id_1 != product_id_2, "Products should have different IDs"

    # Verify both products exist
    products = await database.get_user_products(123456)
    assert len(products) == 2


@pytest.mark.asyncio
async def test_product_limit_trigger_enforcement(test_db):
    """Test database trigger enforces product limit and prevents race conditions."""
    import aiosqlite

    # Create user with limit of 3 products
    await database.add_user(123456, "it")
    await database.set_user_max_products(123456, 3)

    deadline = date.today() + timedelta(days=30)

    # Add 3 products successfully (within limit)
    for i in range(3):
        await database.add_product_atomic(
            user_id=123456,
            product_name=f"Product {i + 1}",
            asin=f"ASIN0000{i + 1}",
            marketplace="it",
            price_paid=50.0 + i * 10,
            return_deadline=deadline,
            min_savings_threshold=5.0,
        )

    # Verify 3 products exist
    products = await database.get_user_products(123456)
    assert len(products) == 3

    # Attempt to add 4th product should fail due to trigger
    with pytest.raises(aiosqlite.IntegrityError) as exc_info:
        await database.add_product_atomic(
            user_id=123456,
            product_name="Product 4 (should fail)",
            asin="ASIN00004",
            marketplace="it",
            price_paid=80.0,
            return_deadline=deadline,
            min_savings_threshold=5.0,
        )

    # Verify error message from trigger
    assert "Product limit exceeded" in str(exc_info.value)

    # Verify still only 3 products (4th was rejected)
    products = await database.get_user_products(123456)
    assert len(products) == 3

    # Test concurrent attempts cannot bypass limit
    # Both should fail since we're already at limit
    results = await asyncio.gather(
        database.add_product_atomic(
            user_id=123456,
            product_name="Concurrent Product A",
            asin="ASINCONC1",
            marketplace="it",
            price_paid=90.0,
            return_deadline=deadline,
            min_savings_threshold=0,
        ),
        database.add_product_atomic(
            user_id=123456,
            product_name="Concurrent Product B",
            asin="ASINCONC2",
            marketplace="it",
            price_paid=100.0,
            return_deadline=deadline,
            min_savings_threshold=0,
        ),
        return_exceptions=True,  # Capture exceptions instead of raising
    )

    # Both should fail with IntegrityError
    assert all(isinstance(result, aiosqlite.IntegrityError) for result in results)
    assert all("Product limit exceeded" in str(result) for result in results)

    # Verify still only 3 products (neither concurrent request succeeded)
    products = await database.get_user_products(123456)
    assert len(products) == 3


@pytest.mark.asyncio
async def test_get_user_products_empty(test_db):
    """Test getting products for user with no products."""
    await database.add_user(123456, "it")
    products = await database.get_user_products(123456)
    assert products == []


@pytest.mark.asyncio
async def test_get_user_products_multiple(test_db):
    """Test getting multiple products for a user."""
    await database.add_user(123456, "it")

    deadline = date.today() + timedelta(days=30)

    await database.add_product(123456, "Product 1", "ASIN00001", "it", 50.0, deadline)
    await database.add_product(123456, "Product 2", "ASIN00002", "it", 60.0, deadline)
    await database.add_product(123456, "Product 3", "ASIN00003", "it", 70.0, deadline)

    products = await database.get_user_products(123456)
    assert len(products) == 3


@pytest.mark.asyncio
async def test_get_all_active_products(test_db):
    """Test getting all active products."""
    await database.add_user(111, "it")
    await database.add_user(222, "it")

    # Add active products
    future_date = date.today() + timedelta(days=10)
    await database.add_product(111, "Active Product 1", "ACTIVE001", "it", 50.0, future_date)
    await database.add_product(222, "Active Product 2", "ACTIVE002", "com", 60.0, future_date)

    # Add expired product
    past_date = date.today() - timedelta(days=1)
    await database.add_product(111, "Expired Product", "EXPIRED01", "de", 70.0, past_date)

    active = await database.get_all_active_products()
    assert len(active) == 2
    assert {p["asin"] for p in active} == {"ACTIVE001", "ACTIVE002"}


@pytest.mark.asyncio
async def test_update_product(test_db):
    """Test updating product fields."""
    await database.add_user(123456, "it")

    deadline = date.today() + timedelta(days=30)
    product_id = await database.add_product(
        123456, "Test Product", "B08N5WRWNW", "it", 59.90, deadline
    )

    # Update price
    success = await database.update_product(product_id, 123456, price_paid=55.00)
    assert success is True

    products = await database.get_user_products(123456)
    assert products[0]["price_paid"] == 55.00

    # Update deadline
    new_deadline = date.today() + timedelta(days=40)
    success = await database.update_product(product_id, 123456, return_deadline=new_deadline)
    assert success is True

    # Update threshold
    success = await database.update_product(product_id, 123456, min_savings_threshold=10.0)
    assert success is True

    products = await database.get_user_products(123456)
    assert products[0]["min_savings_threshold"] == 10.0


@pytest.mark.asyncio
async def test_update_product_nonexistent(test_db):
    """Test updating a product that doesn't exist."""
    success = await database.update_product(99999, 123456, price_paid=50.0)
    assert success is False


@pytest.mark.asyncio
async def test_update_last_notified_price(test_db):
    """Test updating last notified price."""
    await database.add_user(123456, "it")

    deadline = date.today() + timedelta(days=30)
    product_id = await database.add_product(
        123456, "Test Product", "B08N5WRWNW", "it", 59.90, deadline
    )

    # Initially None
    products = await database.get_user_products(123456)
    assert products[0]["last_notified_price"] is None

    # Update to 50.00
    await database.update_last_notified_price(product_id, 50.00)
    products = await database.get_user_products(123456)
    assert products[0]["last_notified_price"] == 50.00

    # Update to 45.00 (new lower price)
    await database.update_last_notified_price(product_id, 45.00)
    products = await database.get_user_products(123456)
    assert products[0]["last_notified_price"] == 45.00


@pytest.mark.asyncio
async def test_delete_product(test_db):
    """Test deleting a product."""
    await database.add_user(123456, "it")

    deadline = date.today() + timedelta(days=30)
    product_id = await database.add_product(
        123456, "Test Product", "B08N5WRWNW", "it", 59.90, deadline
    )

    # Delete product (defense-in-depth: verify user owns product)
    success = await database.delete_product(product_id, 123456)
    assert success is True

    # Verify deleted
    products = await database.get_user_products(123456)
    assert len(products) == 0


@pytest.mark.asyncio
async def test_delete_product_nonexistent(test_db):
    """Test deleting a product that doesn't exist."""
    success = await database.delete_product(99999, 123456)
    assert success is False


@pytest.mark.asyncio
async def test_delete_product_wrong_user(test_db):
    """Test that a user cannot delete another user's product (defense-in-depth)."""
    user1 = 111111
    user2 = 222222

    await database.add_user(user1, "it")
    await database.add_user(user2, "it")

    deadline = date.today() + timedelta(days=30)
    product_id = await database.add_product(
        user1, "User1 Product", "B08N5WRWNW", "it", 59.90, deadline
    )

    # User2 tries to delete User1's product
    success = await database.delete_product(product_id, user2)
    assert success is False

    # Product should still exist
    products = await database.get_user_products(user1)
    assert len(products) == 1

    # User1 can delete their own product
    success = await database.delete_product(product_id, user1)
    assert success is True


@pytest.mark.asyncio
async def test_update_product_wrong_user(test_db):
    """Test that a user cannot update another user's product (defense-in-depth)."""
    user1 = 111111
    user2 = 222222

    await database.add_user(user1, "it")
    await database.add_user(user2, "it")

    deadline = date.today() + timedelta(days=30)
    product_id = await database.add_product(
        user1, "User1 Product", "B08N5WRWNW", "it", 59.90, deadline
    )

    # User2 tries to update User1's product
    success = await database.update_product(product_id, user2, price_paid=10.00)
    assert success is False

    # Product should still have original price
    products = await database.get_user_products(user1)
    assert products[0]["price_paid"] == 59.90

    # User1 can update their own product
    success = await database.update_product(product_id, user1, price_paid=55.00)
    assert success is True
    products = await database.get_user_products(user1)
    assert products[0]["price_paid"] == 55.00


@pytest.mark.asyncio
async def test_delete_expired_products(test_db):
    """Test deleting expired products."""
    await database.add_user(123456, "it")

    # Add active products
    future_date = date.today() + timedelta(days=10)
    await database.add_product(123456, "Active 1", "ACTIVE001", "it", 50.0, future_date)
    await database.add_product(123456, "Active 2", "ACTIVE002", "com", 60.0, future_date)

    # Add expired products
    past_date1 = date.today() - timedelta(days=1)
    past_date2 = date.today() - timedelta(days=10)
    await database.add_product(123456, "Expired 1", "EXPIRED01", "de", 70.0, past_date1)
    await database.add_product(123456, "Expired 2", "EXPIRED02", "fr", 80.0, past_date2)

    # Delete expired
    count = await database.delete_expired_products()
    assert count == 2

    # Verify only active products remain
    products = await database.get_user_products(123456)
    assert len(products) == 2
    assert {p["asin"] for p in products} == {"ACTIVE001", "ACTIVE002"}


# ============================================================================
# Feedback operation tests
# ============================================================================


@pytest.mark.asyncio
async def test_add_feedback(test_db):
    """Test adding feedback."""
    await database.add_user(123456, "it")

    feedback_id = await database.add_feedback(123456, "Great bot!")
    assert feedback_id > 0

    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 1
    assert all_feedback[0]["user_id"] == 123456
    assert all_feedback[0]["message"] == "Great bot!"


@pytest.mark.asyncio
async def test_get_all_feedback_multiple(test_db):
    """Test getting multiple feedback entries."""
    await database.add_user(111, "it")
    await database.add_user(222, "en")

    await database.add_feedback(111, "Feedback 1")
    await database.add_feedback(222, "Feedback 2")
    await database.add_feedback(111, "Feedback 3")

    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 3


@pytest.mark.asyncio
async def test_get_all_feedback_empty(test_db):
    """Test getting feedback when none exists."""
    all_feedback = await database.get_all_feedback()
    assert all_feedback == []


# ============================================================================
# System status and metrics operation tests
# ============================================================================


@pytest.mark.asyncio
async def test_increment_metric_creates_new_key(test_db):
    """Test incrementing a metric that doesn't exist yet."""
    # Increment by default amount (1.0)
    await database.increment_metric("test_counter")

    value = await database.get_metric("test_counter")
    assert value == 1.0


@pytest.mark.asyncio
async def test_increment_metric_with_custom_amount(test_db):
    """Test incrementing a metric with custom amount."""
    # Increment by 5.5
    await database.increment_metric("test_counter", 5.5)

    value = await database.get_metric("test_counter")
    assert value == 5.5


@pytest.mark.asyncio
async def test_increment_metric_multiple_times(test_db):
    """Test incrementing a metric multiple times."""
    await database.increment_metric("test_counter", 10.0)
    await database.increment_metric("test_counter", 5.0)
    await database.increment_metric("test_counter", 2.5)

    value = await database.get_metric("test_counter")
    assert value == 17.5


@pytest.mark.asyncio
async def test_increment_metric_products_total_count(test_db):
    """Test incrementing products_total_count metric (promotional metric)."""
    # Simulate adding 3 products
    await database.increment_metric("products_total_count")
    await database.increment_metric("products_total_count")
    await database.increment_metric("products_total_count")

    value = await database.get_metric("products_total_count")
    assert value == 3.0


@pytest.mark.asyncio
async def test_increment_metric_total_savings_generated(test_db):
    """Test incrementing total_savings_generated metric (promotional metric)."""
    # Simulate 3 notifications with different savings
    await database.increment_metric("total_savings_generated", 10.50)
    await database.increment_metric("total_savings_generated", 5.25)
    await database.increment_metric("total_savings_generated", 15.00)

    value = await database.get_metric("total_savings_generated")
    assert value == 30.75


@pytest.mark.asyncio
async def test_get_metric_nonexistent(test_db):
    """Test getting a metric that doesn't exist returns 0.0."""
    value = await database.get_metric("nonexistent_metric")
    assert value == 0.0


@pytest.mark.asyncio
async def test_get_stats_includes_promotional_metrics(test_db):
    """Test that get_stats includes promotional metrics."""
    # Add some test data
    await database.add_user(123456, "it")
    deadline = date.today() + timedelta(days=30)
    await database.add_product(123456, "Test Product", "B08N5WRWNW", "it", 59.90, deadline)

    # Increment promotional metrics
    await database.increment_metric("products_total_count", 5.0)
    await database.increment_metric("total_savings_generated", 25.50)

    # Get stats
    stats = await database.get_stats()

    # Check standard fields
    assert stats["user_count"] == 1
    assert stats["product_count"] == 1
    assert stats["unique_product_count"] == 1

    # Check promotional metrics
    assert stats["products_total_count"] == 5
    assert stats["total_savings_generated"] == 25.50


@pytest.mark.asyncio
async def test_get_stats_promotional_metrics_default_zero(test_db):
    """Test that promotional metrics default to 0 when not set."""
    # Add user but don't increment metrics
    await database.add_user(123456, "it")

    stats = await database.get_stats()

    # Promotional metrics should be 0
    assert stats["products_total_count"] == 0
    assert stats["total_savings_generated"] == 0.0
