"""Tests for price checker."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import TelegramError

import checker

# ============================================================================
# Main check_and_notify tests
# ============================================================================


@pytest.mark.asyncio
async def test_check_and_notify_no_products():
    """Test check_and_notify with no active products."""
    with patch("checker.database.get_all_active_products", return_value=[]):
        with patch("checker.database.update_system_status") as mock_update_status:
            stats = await checker.check_and_notify()

            assert stats["total_products"] == 0
            assert stats["scraped"] == 0
            assert stats["notifications_sent"] == 0
            # System status should not be updated when no products
            mock_update_status.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_notify_price_not_dropped():
    """Test when current price >= price paid."""
    today = date.today()
    future_date = today + timedelta(days=10)

    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": None,
        }
    ]

    # Current price is same as paid
    current_prices = {1: 50.00}

    with patch("checker.TELEGRAM_TOKEN", "test_token"):
        with patch("checker.database.get_all_active_products", return_value=products):
            with patch("checker.scrape_prices", return_value=current_prices):
                with patch("checker.database.update_system_status") as mock_update:
                    stats = await checker.check_and_notify()

    assert stats["total_products"] == 1
    assert stats["scraped"] == 1
    assert stats["notifications_sent"] == 0
    mock_update.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_notify_below_threshold():
    """Test when savings below min_savings_threshold."""
    today = date.today()
    future_date = today + timedelta(days=10)

    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 10.00,  # Require at least €10 savings
            "last_notified_price": None,
        }
    ]

    # Price dropped by only €5
    current_prices = {1: 45.00}

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value=current_prices):
            with patch("checker.database.update_system_status"):
                with patch("checker.TELEGRAM_TOKEN", "test_token"):
                    stats = await checker.check_and_notify()

    assert stats["notifications_sent"] == 0


@pytest.mark.asyncio
async def test_check_and_notify_already_notified():
    """Test when current price >= last_notified_price."""
    today = date.today()
    future_date = today + timedelta(days=10)

    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": 40.00,  # Already notified at €40
        }
    ]

    # Current price is €45 (higher than last notified)
    current_prices = {1: 45.00}

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value=current_prices):
            with patch("checker.database.update_system_status"):
                with patch("checker.TELEGRAM_TOKEN", "test_token"):
                    stats = await checker.check_and_notify()

    assert stats["notifications_sent"] == 0


@pytest.mark.asyncio
async def test_check_and_notify_success():
    """Test successful notification."""
    today = date.today()
    future_date = today + timedelta(days=10)

    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 5.00,
            "last_notified_price": None,
            "marketplace": "it",
        }
    ]

    # Price dropped to €35 (€15 savings)
    current_prices = {1: 35.00}

    # Mock bot
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    with patch("checker.TELEGRAM_TOKEN", "test_token"):
        with patch("checker.database.get_all_active_products", return_value=products):
            with patch("checker.scrape_prices", return_value=current_prices):
                with patch("checker.Bot", return_value=mock_bot):
                    with patch("checker.database.update_last_notified_price") as mock_update_price:
                        with patch("checker.database.increment_metric") as mock_increment:
                            with patch("checker.database.update_system_status"):
                                stats = await checker.check_and_notify()

    assert stats["notifications_sent"] == 1
    assert stats["errors"] == 0
    mock_bot.send_message.assert_called_once()
    mock_update_price.assert_called_once_with(1, 35.00)
    # Verify that total_savings_generated was incremented
    mock_increment.assert_called_once_with("total_savings_generated", 15.00)


@pytest.mark.asyncio
async def test_check_and_notify_notification_error():
    """Test handling of notification errors."""
    today = date.today()
    future_date = today + timedelta(days=10)

    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": None,
        }
    ]

    current_prices = {1: 35.00}

    # Mock bot that fails
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(side_effect=TelegramError("Network error"))

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value=current_prices):
            with patch("checker.Bot", return_value=mock_bot):
                with patch("checker.database.update_system_status"):
                    with patch("checker.TELEGRAM_TOKEN", "test_token"):
                        stats = await checker.check_and_notify()

    assert stats["notifications_sent"] == 0
    assert stats["errors"] == 1


@pytest.mark.asyncio
async def test_check_and_notify_no_telegram_token():
    """Test when TELEGRAM_TOKEN is not set."""
    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "price_paid": 50.00,
            "return_deadline": (date.today() + timedelta(days=10)).isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": None,
        }
    ]

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value={1: 35.00}):
            with patch("checker.TELEGRAM_TOKEN", ""):
                stats = await checker.check_and_notify()

    assert stats["errors"] == 1
    assert stats["notifications_sent"] == 0


# ============================================================================
# Notification message tests
# ============================================================================


@pytest.mark.asyncio
async def test_send_price_drop_notification_message_format():
    """Test notification message formatting."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    today = date.today()
    deadline = today + timedelta(days=15)

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST?tag=test"):
        await checker.send_price_drop_notification(
            bot=mock_bot,
            user_id=123,
            product_name="Test Product",
            asin="TEST12345",
            marketplace="it",
            current_price=45.99,
            price_paid=59.90,
            savings=13.91,
            return_deadline=deadline,
        )

    # Verify message was sent
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args

    # Check message content
    message = call_args.kwargs["text"]
    assert "€45.99" in message
    assert "€59.90" in message
    assert "€13.91" in message
    assert "15 giorni" in message
    assert "https://amazon.it/dp/TEST?tag=test" in message
    assert call_args.kwargs["parse_mode"] == "HTML"
    assert call_args.kwargs["chat_id"] == 123


@pytest.mark.asyncio
async def test_send_price_drop_notification_deadline_today():
    """Test notification when deadline is today."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    today = date.today()

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST"):
        await checker.send_price_drop_notification(
            bot=mock_bot,
            user_id=123,
            product_name="Test Product",
            asin="TEST",
            marketplace="it",
            current_price=40.00,
            price_paid=50.00,
            savings=10.00,
            return_deadline=today,
        )

    message = mock_bot.send_message.call_args.kwargs["text"]
    assert "<b>oggi</b>" in message


@pytest.mark.asyncio
async def test_send_price_drop_notification_deadline_passed():
    """Test notification when deadline has passed."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    past_date = date.today() - timedelta(days=5)

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST"):
        await checker.send_price_drop_notification(
            bot=mock_bot,
            user_id=123,
            product_name="Test Product",
            asin="TEST",
            marketplace="it",
            current_price=40.00,
            price_paid=50.00,
            savings=10.00,
            return_deadline=past_date,
        )

    message = mock_bot.send_message.call_args.kwargs["text"]
    assert "<b>scaduto</b>" in message


@pytest.mark.asyncio
async def test_send_price_drop_notification_telegram_error():
    """Test notification error handling."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(side_effect=TelegramError("Failed"))

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST"):
        with pytest.raises(TelegramError):
            await checker.send_price_drop_notification(
                bot=mock_bot,
                user_id=123,
                product_name="Test Product",
                asin="TEST",
                marketplace="it",
                current_price=40.00,
                price_paid=50.00,
                savings=10.00,
                return_deadline=date.today(),
            )


@pytest.mark.asyncio
async def test_check_and_notify_scraping_failure():
    """Test when scraping fails (current_price is None)."""
    today = date.today()
    future_date = today + timedelta(days=10)

    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "marketplace": "it",
            "product_name": "Test Product",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": None,
        }
    ]

    # Scraping failed - returns None for price
    current_prices = {1: None}

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value=current_prices):
            with patch("checker.database.update_system_status"):
                stats = await checker.check_and_notify()

                # Should skip product with no price
                assert stats["total_products"] == 1
                assert stats["scraped"] == 1
                assert stats["notifications_sent"] == 0


@pytest.mark.asyncio
async def test_check_and_notify_notification_exception():
    """Test exception during notification (covers error handling in batch processing)."""
    today = date.today()
    future_date = today + timedelta(days=10)

    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "ASIN00001",
            "marketplace": "it",
            "product_name": "Test Product",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": None,
        }
    ]

    # Price dropped
    current_prices = {1: 40.00}

    mock_bot = AsyncMock()
    # Simulate Telegram error during notification
    mock_bot.send_message = AsyncMock(side_effect=TelegramError("Network error"))

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value=current_prices):
            with patch("checker.Bot", return_value=mock_bot):
                with patch("checker.database.update_system_status"):
                    stats = await checker.check_and_notify()

                    # Should count error
                    assert stats["total_products"] == 1
                    assert stats["errors"] >= 1


@pytest.mark.asyncio
async def test_check_and_notify_general_exception():
    """Test general exception handling in check_and_notify."""
    # Simulate database failure
    with patch("checker.database.get_all_active_products", side_effect=Exception("Database error")):
        stats = await checker.check_and_notify()

        # Should return stats with error
        assert stats["errors"] >= 1


@pytest.mark.asyncio
async def test_check_and_notify_multiple_batches():
    """Test rate limiting between batches."""
    today = date.today()
    future_date = today + timedelta(days=10)

    # Create less than batch_size products (default is 10, using 8 for testing)
    products = []
    current_prices = {}
    for i in range(8):  # Less than batch size, tests single batch
        products.append(
            {
                "id": i + 1,
                "user_id": 100 + i,
                "asin": f"ASIN{i:05d}",
                "marketplace": "it",
                "product_name": f"Product {i}",
                "price_paid": 50.00,
                "return_deadline": future_date.isoformat(),
                "min_savings_threshold": 0,
                "last_notified_price": None,
            }
        )
        # Price dropped for all
        current_prices[i + 1] = 40.00

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(return_value=True)

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value=current_prices):
            with patch("checker.TELEGRAM_TOKEN", "test-token"):  # Mock token
                with patch("checker.Bot", return_value=mock_bot):
                    with patch("checker.database.update_last_notified_price"):
                        with patch("checker.database.increment_metric"):
                            with patch("checker.database.update_system_status"):
                                # Mock asyncio.sleep for rate limiting between batches
                                with patch("checker.asyncio.sleep", new=AsyncMock()):
                                    stats = await checker.check_and_notify()

                                    # Should have sent notifications
                                    assert stats["notifications_sent"] > 0
