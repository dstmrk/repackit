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
                        with patch("checker.database.update_system_status"):
                            stats = await checker.check_and_notify()

    assert stats["notifications_sent"] == 1
    assert stats["errors"] == 0
    mock_bot.send_message.assert_called_once()
    mock_update_price.assert_called_once_with(1, 35.00)


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
    assert call_args.kwargs["parse_mode"] == "Markdown"
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
    assert "*oggi*" in message


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
    assert "*scaduto*" in message


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
async def test_check_and_notify_with_unavailable_products():
    """Test check_and_notify with products that become unavailable after 3 failures."""
    today = date.today()
    future_date = today + timedelta(days=10)

    # Product with 2 consecutive failures (will become 3 after this check)
    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "UNAVAILABLE1",
            "marketplace": "it",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": None,
            "consecutive_failures": 2,  # Will hit 3 on this run
        }
    ]

    # Mock scraper returns None (scraping failed)
    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value={}):  # Empty = failed
            with patch("checker.database.increment_consecutive_failures", return_value=3):
                with patch("checker.database.update_system_status"):
                    with patch("checker.TELEGRAM_TOKEN", "test_token"):
                        with patch("checker.Bot") as mock_bot:
                            mock_bot_instance = AsyncMock()
                            mock_bot.return_value = mock_bot_instance

                            await checker.check_and_notify()

                            # Verify unavailable notification was sent
                            assert mock_bot_instance.send_message.called
                            call_kwargs = mock_bot_instance.send_message.call_args.kwargs
                            message = call_kwargs["text"]
                            assert "Prodotto non disponibile" in message


@pytest.mark.asyncio
async def test_check_and_notify_reset_failures_on_success():
    """Test that consecutive failures are reset when scraping succeeds."""
    today = date.today()
    future_date = today + timedelta(days=10)

    # Product with 2 consecutive failures, but scraping will succeed
    products = [
        {
            "id": 1,
            "user_id": 123,
            "asin": "RECOVERED1",
            "marketplace": "it",
            "price_paid": 50.00,
            "return_deadline": future_date.isoformat(),
            "min_savings_threshold": 0,
            "last_notified_price": None,
            "consecutive_failures": 2,
        }
    ]

    # Mock scraper returns price (scraping succeeded)
    prices = {1: 60.00}  # Price higher, no notification

    with patch("checker.database.get_all_active_products", return_value=products):
        with patch("checker.scrape_prices", return_value=prices):
            with patch("checker.database.reset_consecutive_failures") as mock_reset:
                with patch("checker.database.update_system_status"):
                    with patch("checker.TELEGRAM_TOKEN", "test_token"):
                        stats = await checker.check_and_notify()

                        # Verify failures were reset
                        mock_reset.assert_called_once_with(1)
                        assert stats["scraped"] == 1


# ============================================================================
# Unavailable notification tests
# ============================================================================


@pytest.mark.asyncio
async def test_send_unavailable_notification():
    """Test sending unavailable product notification."""
    mock_bot = AsyncMock()

    future_date = date.today() + timedelta(days=10)

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST"):
        await checker.send_unavailable_notification(
            bot=mock_bot,
            user_id=123,
            product_name="Test Product",
            asin="TEST",
            marketplace="it",
            return_deadline=future_date,
        )

    # Verify message was sent
    assert mock_bot.send_message.called
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 123
    assert call_kwargs["parse_mode"] == "Markdown"

    # Verify message content
    message = call_kwargs["text"]
    assert "Prodotto non disponibile" in message
    assert "3 volte consecutive" in message
    assert "tra 10 giorni" in message


@pytest.mark.asyncio
async def test_send_unavailable_notification_today():
    """Test unavailable notification for deadline today."""
    mock_bot = AsyncMock()

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST"):
        await checker.send_unavailable_notification(
            bot=mock_bot,
            user_id=123,
            product_name="Test Product",
            asin="TEST",
            marketplace="it",
            return_deadline=date.today(),
        )

    message = mock_bot.send_message.call_args.kwargs["text"]
    assert "*oggi*" in message


@pytest.mark.asyncio
async def test_send_unavailable_notification_expired():
    """Test unavailable notification for expired deadline."""
    mock_bot = AsyncMock()
    past_date = date.today() - timedelta(days=1)

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST"):
        await checker.send_unavailable_notification(
            bot=mock_bot,
            user_id=123,
            product_name="Test Product",
            asin="TEST",
            marketplace="it",
            return_deadline=past_date,
        )

    message = mock_bot.send_message.call_args.kwargs["text"]
    assert "*scaduto*" in message


@pytest.mark.asyncio
async def test_send_unavailable_notification_telegram_error():
    """Test unavailable notification error handling."""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(side_effect=TelegramError("Failed"))

    with patch("checker.build_affiliate_url", return_value="https://amazon.it/dp/TEST"):
        with pytest.raises(TelegramError):
            await checker.send_unavailable_notification(
                bot=mock_bot,
                user_id=123,
                product_name="Test Product",
                asin="TEST",
                marketplace="it",
                return_deadline=date.today(),
            )
