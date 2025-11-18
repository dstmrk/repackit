"""Tests for bot.py."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot


def test_calculate_next_run_future():
    """Test calculate_next_run when scheduled hour is in the future today."""
    now = datetime.now()
    future_hour = (now.hour + 2) % 24

    # If future_hour wrapped around, we need to handle it
    if future_hour < now.hour:
        # Hour wrapped around midnight, so next run should be tomorrow
        expected = (now + timedelta(days=1)).replace(
            hour=future_hour, minute=0, second=0, microsecond=0
        )
    else:
        # Hour is later today
        expected = now.replace(hour=future_hour, minute=0, second=0, microsecond=0)

    result = bot.calculate_next_run(future_hour)

    # Allow 1 second tolerance for test execution time
    assert abs((result - expected).total_seconds()) < 1


def test_calculate_next_run_past():
    """Test calculate_next_run when scheduled hour has already passed today."""
    now = datetime.now()
    past_hour = (now.hour - 1) % 24

    if past_hour > now.hour:
        # Hour wrapped around, schedule for later today
        expected = now.replace(hour=past_hour, minute=0, second=0, microsecond=0)
    else:
        # Hour has passed, schedule for tomorrow
        expected = (now + timedelta(days=1)).replace(
            hour=past_hour, minute=0, second=0, microsecond=0
        )

    result = bot.calculate_next_run(past_hour)

    # Allow 1 second tolerance
    assert abs((result - expected).total_seconds()) < 1


def test_calculate_next_run_midnight():
    """Test calculate_next_run for midnight (hour=0)."""
    result = bot.calculate_next_run(0)
    assert result.hour == 0
    assert result.minute == 0
    assert result.second == 0


def test_calculate_next_run_23():
    """Test calculate_next_run for 23:00."""
    result = bot.calculate_next_run(23)
    assert result.hour == 23
    assert result.minute == 0
    assert result.second == 0


@pytest.mark.asyncio
async def test_run_scraper_with_products():
    """Test run_scraper with active products."""
    mock_products = [
        {"id": 1, "asin": "ASIN00001", "marketplace": "it"},
        {"id": 2, "asin": "ASIN00002", "marketplace": "it"},
    ]

    with patch("bot.database.get_all_active_products", return_value=mock_products):
        with patch("bot.scrape_prices", return_value={1: 50.0, 2: 60.0}) as mock_scrape:
            with patch("bot.database.update_system_status") as mock_status:
                await bot.run_scraper()

                # Verify scrape_prices was called with products
                mock_scrape.assert_called_once_with(mock_products)

                # Verify system status was updated
                mock_status.assert_called_once()
                call_args = mock_status.call_args[0]
                assert call_args[0] == "last_scraper_run"


@pytest.mark.asyncio
async def test_run_scraper_no_products():
    """Test run_scraper with no active products."""
    with patch("bot.database.get_all_active_products", return_value=[]):
        with patch("bot.scrape_prices") as mock_scrape:
            with patch("bot.database.update_system_status") as mock_status:
                await bot.run_scraper()

                # Verify scrape_prices was NOT called
                mock_scrape.assert_not_called()

                # Verify system status was NOT updated
                mock_status.assert_not_called()


@pytest.mark.asyncio
async def test_run_scraper_error_handling():
    """Test run_scraper handles errors gracefully."""
    with patch("bot.database.get_all_active_products", side_effect=Exception("Database error")):
        # Should not raise exception
        await bot.run_scraper()


@pytest.mark.asyncio
async def test_run_checker():
    """Test run_checker executes checker."""
    mock_stats = {"total_products": 5, "notifications_sent": 2, "errors": 0}

    with patch("bot.checker.check_and_notify", return_value=mock_stats) as mock_checker:
        await bot.run_checker()

        # Verify checker was called
        mock_checker.assert_called_once()


@pytest.mark.asyncio
async def test_run_checker_error_handling():
    """Test run_checker handles errors gracefully."""
    with patch("bot.checker.check_and_notify", side_effect=Exception("Checker error")):
        # Should not raise exception
        await bot.run_checker()


@pytest.mark.asyncio
async def test_run_cleanup():
    """Test run_cleanup executes cleanup."""
    mock_result = {"deleted": 3, "timestamp": datetime.now().isoformat()}

    with patch(
        "bot.product_cleanup.cleanup_expired_products", return_value=mock_result
    ) as mock_cleanup:
        await bot.run_cleanup()

        # Verify cleanup was called
        mock_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_run_cleanup_error_handling():
    """Test run_cleanup handles errors gracefully."""
    with patch(
        "bot.product_cleanup.cleanup_expired_products", side_effect=Exception("Cleanup error")
    ):
        # Should not raise exception
        await bot.run_cleanup()


@pytest.mark.asyncio
async def test_start_handler():
    """Test /start command handler."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await bot.start_handler(update, context)

    # Verify welcome message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0]
    assert "Benvenuto" in call_args[0]
    assert "/add" in call_args[0]


@pytest.mark.asyncio
async def test_schedule_scraper_shutdown():
    """Test schedule_scraper respects shutdown event."""
    # Set shutdown event to stop immediately
    bot.shutdown_event.set()

    # Create task
    task = asyncio.create_task(bot.schedule_scraper())

    # Wait briefly to ensure it checks the event
    await asyncio.sleep(0.1)

    # Task should complete quickly due to shutdown event
    assert task.done() or task.cancelled()

    # Reset shutdown event
    bot.shutdown_event.clear()


@pytest.mark.asyncio
async def test_schedule_checker_shutdown():
    """Test schedule_checker respects shutdown event."""
    bot.shutdown_event.set()

    task = asyncio.create_task(bot.schedule_checker())
    await asyncio.sleep(0.1)

    assert task.done() or task.cancelled()
    bot.shutdown_event.clear()


@pytest.mark.asyncio
async def test_schedule_cleanup_shutdown():
    """Test schedule_cleanup respects shutdown event."""
    bot.shutdown_event.set()

    task = asyncio.create_task(bot.schedule_cleanup())
    await asyncio.sleep(0.1)

    assert task.done() or task.cancelled()
    bot.shutdown_event.clear()
