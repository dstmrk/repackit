"""Tests for health check handler."""

import asyncio
import contextlib
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from aiohttp import web

import database
import health_handler


@pytest.fixture
async def test_db():
    """Create a temporary test database."""
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
    Path(f"{db_path}-wal").unlink(missing_ok=True)
    Path(f"{db_path}-shm").unlink(missing_ok=True)


# ============================================================================
# Database system_status tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_system_status(test_db):
    """Test updating system status."""
    await database.update_system_status("last_scraper_run", "2024-01-15T10:00:00")

    status = await database.get_system_status("last_scraper_run")
    assert status is not None
    assert status["key"] == "last_scraper_run"
    assert status["value"] == "2024-01-15T10:00:00"


@pytest.mark.asyncio
async def test_update_system_status_overwrite(test_db):
    """Test that updating same key overwrites value."""
    await database.update_system_status("last_scraper_run", "2024-01-15T10:00:00")
    await database.update_system_status("last_scraper_run", "2024-01-15T11:00:00")

    status = await database.get_system_status("last_scraper_run")
    assert status["value"] == "2024-01-15T11:00:00"


@pytest.mark.asyncio
async def test_get_system_status_nonexistent(test_db):
    """Test getting status that doesn't exist."""
    status = await database.get_system_status("nonexistent_key")
    assert status is None


@pytest.mark.asyncio
async def test_get_all_system_status(test_db):
    """Test getting all system status entries."""
    await database.update_system_status("last_scraper_run", "2024-01-15T10:00:00")
    await database.update_system_status("last_checker_run", "2024-01-15T11:00:00")
    await database.update_system_status("last_cleanup_run", "2024-01-15T02:00:00")

    all_status = await database.get_all_system_status()
    assert len(all_status) == 3
    assert "last_scraper_run" in all_status
    assert "last_checker_run" in all_status
    assert "last_cleanup_run" in all_status


@pytest.mark.asyncio
async def test_get_stats_empty(test_db):
    """Test getting stats from empty database."""
    stats = await database.get_stats()
    assert stats["user_count"] == 0
    assert stats["product_count"] == 0
    assert stats["unique_product_count"] == 0


@pytest.mark.asyncio
async def test_get_stats_with_data(test_db):
    """Test getting stats with data."""
    from datetime import date

    # Add users
    await database.add_user(111, "it")
    await database.add_user(222, "en")

    # Add products (all different ASINs)
    future_date = date.today() + timedelta(days=10)

    await database.add_product(111, "Product 1", "ASIN001", "it", 50.0, future_date)
    await database.add_product(111, "Product 2", "ASIN002", "it", 60.0, future_date)
    await database.add_product(222, "Product 3", "ASIN003", "it", 70.0, future_date)

    stats = await database.get_stats()
    assert stats["user_count"] == 2
    assert stats["product_count"] == 3
    assert stats["unique_product_count"] == 3  # All different ASINs


@pytest.mark.asyncio
async def test_get_stats_deduplication(test_db):
    """Test that unique_product_count correctly deduplicates by (asin, marketplace)."""
    from datetime import date

    # Add users
    await database.add_user(111, "it")
    await database.add_user(222, "it")
    await database.add_user(333, "en")

    future_date = date.today() + timedelta(days=10)

    # Add products with duplicates
    # Same ASIN, same marketplace (should count as 1 unique)
    await database.add_product(111, "iPhone 15 User1", "ASIN001", "it", 50.0, future_date)
    await database.add_product(222, "iPhone 15 User2", "ASIN001", "it", 55.0, future_date)
    await database.add_product(333, "iPhone 15 User3", "ASIN001", "it", 60.0, future_date)

    # Same ASIN, different marketplace (should count as separate unique)
    await database.add_product(111, "iPhone 15 DE", "ASIN001", "de", 65.0, future_date)

    # Different ASIN (should count as separate unique)
    await database.add_product(222, "MacBook", "ASIN002", "it", 1000.0, future_date)

    stats = await database.get_stats()
    assert stats["user_count"] == 3
    assert stats["product_count"] == 5  # Total 5 products
    assert stats["unique_product_count"] == 3  # Only 3 unique (asin, marketplace) pairs:
    # 1. (ASIN001, it)
    # 2. (ASIN001, de)
    # 3. (ASIN002, it)


# ============================================================================
# Health check logic tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_status_all_tasks_healthy(test_db):
    """Test health status when all tasks recently ran."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Set all tasks as recently run
    await database.update_system_status("last_scraper_run", one_day_ago)
    await database.update_system_status("last_checker_run", one_day_ago)
    await database.update_system_status("last_cleanup_run", one_day_ago)

    health = await health_handler.get_health_status()

    assert health["status"] == "healthy"
    assert health["tasks"]["scraper"]["status"] == "ok"
    assert health["tasks"]["checker"]["status"] == "ok"
    assert health["tasks"]["cleanup"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_status_stale_task(test_db):
    """Test health status when one task is stale."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()
    three_days_ago = (now - timedelta(days=3)).isoformat()

    # Scraper is stale (> 2 days)
    await database.update_system_status("last_scraper_run", three_days_ago)
    await database.update_system_status("last_checker_run", one_day_ago)
    await database.update_system_status("last_cleanup_run", one_day_ago)

    health = await health_handler.get_health_status()

    assert health["status"] == "unhealthy"
    assert health["tasks"]["scraper"]["status"] == "stale"
    assert health["tasks"]["checker"]["status"] == "ok"
    assert health["tasks"]["cleanup"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_status_never_run_no_startup_time(test_db):
    """Test health status when task has never run and no bot startup time recorded."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Only some tasks have run
    await database.update_system_status("last_scraper_run", one_day_ago)
    # checker and cleanup have never run
    # No bot_startup_time set

    health = await health_handler.get_health_status()

    assert health["status"] == "unhealthy"
    assert health["tasks"]["scraper"]["status"] == "ok"
    assert health["tasks"]["checker"]["status"] == "never_run"
    assert health["tasks"]["cleanup"]["status"] == "never_run"


@pytest.mark.asyncio
async def test_health_status_never_run_with_recent_startup(test_db):
    """Test health status when task has never run but bot started recently (grace period)."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Bot started 1 day ago (within grace period)
    await database.update_system_status("bot_startup_time", one_day_ago)

    # Only some tasks have run
    await database.update_system_status("last_scraper_run", one_day_ago)
    # checker and cleanup have never run, but within grace period

    health = await health_handler.get_health_status()

    # Should be healthy because bot started recently
    assert health["status"] == "healthy"
    assert health["tasks"]["scraper"]["status"] == "ok"
    assert health["tasks"]["checker"]["status"] == "never_run"
    assert health["tasks"]["cleanup"]["status"] == "never_run"
    assert "bot_startup_time" in health


@pytest.mark.asyncio
async def test_health_status_never_run_with_old_startup(test_db):
    """Test health status when task has never run and bot started >2 days ago."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()
    three_days_ago = (now - timedelta(days=3)).isoformat()

    # Bot started 3 days ago (beyond grace period)
    await database.update_system_status("bot_startup_time", three_days_ago)

    # Only some tasks have run
    await database.update_system_status("last_scraper_run", one_day_ago)
    # checker and cleanup have never run, beyond grace period

    health = await health_handler.get_health_status()

    # Should be unhealthy because bot started >2 days ago
    assert health["status"] == "unhealthy"
    assert health["tasks"]["scraper"]["status"] == "ok"
    assert health["tasks"]["checker"]["status"] == "never_run"
    assert health["tasks"]["cleanup"]["status"] == "never_run"
    assert "bot_startup_time" in health


@pytest.mark.asyncio
async def test_health_status_includes_stats(test_db):
    """Test that health status includes database stats."""
    from datetime import date

    # Add some data
    await database.add_user(111, "it")
    await database.add_user(222, "en")

    future_date = date.today() + timedelta(days=10)
    await database.add_product(111, "Active Product", "ACTIVE01", "it", 50.0, future_date)

    # Add promotional metrics
    await database.increment_metric("products_total_count", 10.0)
    await database.increment_metric("total_savings_generated", 125.50)

    health = await health_handler.get_health_status()

    assert "stats" in health
    assert health["stats"]["users"] == 2
    assert health["stats"]["products_total"] == 1
    assert health["stats"]["products_unique"] == 1
    # Check promotional metrics
    assert health["stats"]["products_total_count"] == 10
    assert health["stats"]["total_savings_generated"] == 125.50


@pytest.mark.asyncio
async def test_health_status_exactly_at_threshold(test_db):
    """Test health status when task ran just within the 2-day threshold."""
    now = datetime.now()
    # Use 1 day 23 hours to ensure we're within threshold even with timing differences
    within_threshold = (now - timedelta(days=1, hours=23)).isoformat()

    await database.update_system_status("last_scraper_run", within_threshold)
    await database.update_system_status("last_checker_run", within_threshold)
    await database.update_system_status("last_cleanup_run", within_threshold)

    health = await health_handler.get_health_status()

    # Within 2 days should be healthy
    assert health["status"] == "healthy"
    assert health["tasks"]["scraper"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_status_just_over_threshold(test_db):
    """Test health status when task ran just over 2 days ago."""
    now = datetime.now()
    just_over_two_days = (now - timedelta(days=2, hours=1)).isoformat()

    await database.update_system_status("last_scraper_run", just_over_two_days)
    await database.update_system_status("last_checker_run", just_over_two_days)
    await database.update_system_status("last_cleanup_run", just_over_two_days)

    health = await health_handler.get_health_status()

    # Just over 2 days should be unhealthy
    assert health["status"] == "unhealthy"
    assert health["tasks"]["scraper"]["status"] == "stale"


@pytest.mark.asyncio
async def test_health_status_includes_timestamp(test_db):
    """Test that health status includes current timestamp in yyyy-mm-dd hh:mm:ss format."""
    health = await health_handler.get_health_status()

    assert "timestamp" in health
    # Verify it's in the format yyyy-mm-dd hh:mm:ss
    timestamp = datetime.strptime(health["timestamp"], "%Y-%m-%d %H:%M:%S")
    assert isinstance(timestamp, datetime)


@pytest.mark.asyncio
async def test_health_status_task_timestamps_formatted(test_db):
    """Test that task timestamps are formatted as yyyy-mm-dd hh:mm:ss."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Set all tasks as recently run
    await database.update_system_status("last_scraper_run", one_day_ago)
    await database.update_system_status("last_checker_run", one_day_ago)
    await database.update_system_status("last_cleanup_run", one_day_ago)

    health = await health_handler.get_health_status()

    # Verify each task's last_run timestamp is in the correct format
    for task_name in ["scraper", "checker", "cleanup"]:
        last_run = health["tasks"][task_name]["last_run"]
        # This will raise ValueError if format is wrong
        timestamp = datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
        assert isinstance(timestamp, datetime)


@pytest.mark.asyncio
async def test_check_task_health_invalid_timestamp(test_db):
    """Test _check_task_health with invalid timestamp format."""
    # Add invalid timestamp
    await database.update_system_status("last_scraper_run", "invalid-timestamp")

    # Get system status
    system_status = await database.get_all_system_status()
    threshold = datetime.now()

    # Call _check_task_health (bot_startup_time not relevant for error case)
    task_status, is_healthy = health_handler._check_task_health(
        "scraper", system_status, threshold, bot_startup_time=None
    )

    # Verify error status
    assert task_status["status"] == "error"
    assert is_healthy is False
    assert task_status["last_run"] == "invalid-timestamp"


# ============================================================================
# Server configuration and startup tests
# ============================================================================


def test_health_bind_address_default():
    """Test that HEALTH_BIND_ADDRESS defaults to 0.0.0.0."""
    # Reload module to get fresh environment variable
    import importlib

    # Save current value
    original_value = os.environ.get("HEALTH_BIND_ADDRESS")

    try:
        # Remove env var if it exists
        if "HEALTH_BIND_ADDRESS" in os.environ:
            del os.environ["HEALTH_BIND_ADDRESS"]

        # Reload module to get default value
        importlib.reload(health_handler)

        assert health_handler.HEALTH_BIND_ADDRESS == "0.0.0.0"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["HEALTH_BIND_ADDRESS"] = original_value
        importlib.reload(health_handler)


def test_health_bind_address_from_env():
    """Test that HEALTH_BIND_ADDRESS can be set from environment."""
    import importlib

    # Save current value
    original_value = os.environ.get("HEALTH_BIND_ADDRESS")

    try:
        # Set custom value
        os.environ["HEALTH_BIND_ADDRESS"] = "127.0.0.1"

        # Reset config and reload module to pick up new value
        from config import reset_config

        reset_config()
        importlib.reload(health_handler)

        assert health_handler.HEALTH_BIND_ADDRESS == "127.0.0.1"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["HEALTH_BIND_ADDRESS"] = original_value
        else:
            if "HEALTH_BIND_ADDRESS" in os.environ:
                del os.environ["HEALTH_BIND_ADDRESS"]
        from config import reset_config

        reset_config()
        importlib.reload(health_handler)


# ============================================================================
# aiohttp handler tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_handler_success(test_db):
    """Test health_check_handler returns valid JSON on success."""
    # Add some test data
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()
    await database.update_system_status("last_scraper_run", one_day_ago)
    await database.update_system_status("last_checker_run", one_day_ago)
    await database.update_system_status("last_cleanup_run", one_day_ago)

    # Create mock aiohttp request
    app = web.Application()
    app.router.add_get("/health", health_handler.health_check_handler)

    # Create test client
    from aiohttp.test_utils import TestClient, TestServer

    server = TestServer(app)
    client = TestClient(server)

    await client.start_server()

    try:
        # Make request to /health
        resp = await client.get("/health")

        # Verify response
        assert resp.status == 200
        data = await resp.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "tasks" in data
        assert "stats" in data
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_health_check_handler_error(test_db):
    """Test health_check_handler returns 500 on error."""
    # Mock get_health_status to raise an error
    with patch("health_handler.get_health_status", side_effect=Exception("Database error")):
        # Create mock aiohttp request
        app = web.Application()
        app.router.add_get("/health", health_handler.health_check_handler)

        # Create test client
        from aiohttp.test_utils import TestClient, TestServer

        server = TestServer(app)
        client = TestClient(server)

        await client.start_server()

        try:
            # Make request to /health
            resp = await client.get("/health")

            # Verify error response
            assert resp.status == 500
            data = await resp.json()
            assert "status" in data
            assert data["status"] == "error"
            assert "message" in data
            assert "Database error" in data["message"]
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_start_health_server(test_db):
    """Test that start_health_server initializes aiohttp app correctly."""
    # We can't easily test the full server startup without blocking,
    # but we can test the app creation and routing

    # Create a task that will be cancelled quickly
    server_task = asyncio.create_task(health_handler.start_health_server())

    # Give it a moment to start
    await asyncio.sleep(0.1)

    # Cancel the server
    server_task.cancel()

    # Suppress expected CancelledError
    with contextlib.suppress(asyncio.CancelledError):
        await server_task
