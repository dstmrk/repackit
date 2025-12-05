"""Tests for handlers/list.py."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.list import list_handler


@pytest.mark.asyncio
async def test_list_handler_no_products(test_db):
    """Test /list handler with no products."""
    # Create user with no products
    await database.add_user(user_id=123, language_code="it")

    # Create mock update and context
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Call handler
    await list_handler(update, context)

    # Verify empty message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Nessun prodotto" in message
    assert "/add" in message
    assert call_args[1]["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_list_handler_single_product(test_db):
    """Test /list handler with single product."""
    # Create user and product
    await database.add_user(user_id=123, language_code="it")

    tomorrow = date.today() + timedelta(days=5)
    await database.add_product(
        user_id=123,
        product_name="Test Product",
        asin="B08N5WRWNW",
        marketplace="it",
        price_paid=59.90,
        return_deadline=tomorrow,
        min_savings_threshold=5.0,
    )

    # Create mock update and context
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Call handler
    await list_handler(update, context)

    # Verify product list was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "1." in message
    assert "€59.90" in message
    assert "€5.00" in message
    assert "tra 5 giorni" in message
    assert "B08N5WRWNW" in message
    assert call_args[1]["parse_mode"] == "HTML"
    assert call_args[1]["disable_web_page_preview"] is True


@pytest.mark.asyncio
async def test_list_handler_multiple_products(test_db):
    """Test /list handler with multiple products."""
    # Create user and products
    await database.add_user(user_id=123, language_code="it")

    tomorrow = date.today() + timedelta(days=1)
    next_week = date.today() + timedelta(days=7)

    await database.add_product(
        user_id=123,
        product_name="Product 1",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=tomorrow,
    )
    await database.add_product(
        user_id=123,
        product_name="Product 2",
        asin="ASIN00002",
        marketplace="it",
        price_paid=75.0,
        return_deadline=next_week,
        min_savings_threshold=10.0,
    )

    # Create mock update and context
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Call handler
    await list_handler(update, context)

    # Verify both products are listed
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "1." in message
    assert "2." in message
    assert "€50.00" in message
    assert "€75.00" in message
    assert "€10.00" in message
    # User has no max_products set (NULL), so gets DEFAULT_MAX_PRODUCTS (21)
    assert "2/21 prodotti" in message


@pytest.mark.asyncio
async def test_list_handler_deadline_today(test_db):
    """Test /list handler with deadline today."""
    await database.add_user(user_id=123, language_code="it")

    today = date.today()
    await database.add_product(
        user_id=123,
        product_name="Test Product",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=today,
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await list_handler(update, context)

    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "oggi!" in message


@pytest.mark.asyncio
async def test_list_handler_deadline_expired(test_db):
    """Test /list handler with expired deadline."""
    await database.add_user(user_id=123, language_code="it")

    yesterday = date.today() - timedelta(days=1)
    await database.add_product(
        user_id=123,
        product_name="Test Product",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=yesterday,
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await list_handler(update, context)

    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "scaduto" in message


@pytest.mark.asyncio
async def test_list_handler_no_threshold(test_db):
    """Test /list handler with product without threshold."""
    await database.add_user(user_id=123, language_code="it")

    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123,
        product_name="Test Product",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=tomorrow,
        min_savings_threshold=None,
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await list_handler(update, context)

    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    # Should not show threshold if it's None or 0
    assert "Soglia" not in message


@pytest.mark.asyncio
async def test_list_handler_database_error(test_db):
    """Test /list handler handles database errors gracefully."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Mock database.get_user_products to raise an exception
    with patch("handlers.list.database.get_user_products", side_effect=Exception("DB Error")):
        await list_handler(update, context)

        # Verify error message was sent
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message


@pytest.mark.asyncio
async def test_list_handler_shows_share_hint_when_low_on_slots(test_db):
    """Test /list shows /share hint when user has <3 slots available and <21 total."""
    # Create user with 6 slots
    await database.add_user(user_id=123, language_code="it")
    await database.set_user_max_products(user_id=123, limit=6)

    # Add 5 products (only 1 slot remaining)
    tomorrow = date.today() + timedelta(days=1)
    for i in range(5):
        await database.add_product(
            user_id=123,
            product_name=f"Product {i+1}",
            asin=f"ASIN0000{i+1}",
            marketplace="it",
            price_paid=50.0,
            return_deadline=tomorrow,
        )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await list_handler(update, context)

    # Verify hint is shown
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "5/6 prodotti" in message
    assert "/share" in message
    assert "Stai esaurendo gli slot" in message


@pytest.mark.asyncio
async def test_list_handler_no_share_hint_when_enough_slots(test_db):
    """Test /list doesn't show /share hint when user has ≥3 slots available."""
    # Create user with 6 slots
    await database.add_user(user_id=123, language_code="it")
    await database.set_user_max_products(user_id=123, limit=6)

    # Add 2 products (4 slots remaining)
    tomorrow = date.today() + timedelta(days=1)
    for i in range(2):
        await database.add_product(
            user_id=123,
            product_name=f"Product {i+1}",
            asin=f"ASIN0000{i+1}",
            marketplace="it",
            price_paid=50.0,
            return_deadline=tomorrow,
        )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await list_handler(update, context)

    # Verify hint is NOT shown
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "2/6 prodotti" in message
    assert "/share" not in message
    assert "Stai esaurendo" not in message


@pytest.mark.asyncio
async def test_list_handler_no_share_hint_when_at_max_slots(test_db):
    """Test /list doesn't show /share hint when user is already at max (21 slots)."""
    # Create user at max slots (21)
    await database.add_user(user_id=123, language_code="it")
    await database.set_user_max_products(user_id=123, limit=21)

    # Add 20 products (only 1 slot remaining, but at max)
    tomorrow = date.today() + timedelta(days=1)
    for i in range(20):
        await database.add_product(
            user_id=123,
            product_name=f"Product {i+1}",
            asin=f"ASIN000{i+1:02d}",
            marketplace="it",
            price_paid=50.0,
            return_deadline=tomorrow,
        )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await list_handler(update, context)

    # Verify hint is NOT shown (user is already at max)
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "20/21 prodotti" in message
    assert "/share" not in message
    assert "Stai esaurendo" not in message


@pytest.mark.asyncio
async def test_list_handler_escapes_html_characters(test_db):
    """Test that product names with HTML characters are properly escaped."""
    await database.add_user(user_id=123, language_code="it")

    # Add product with HTML special characters in name
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123,
        product_name="Test <script>alert('xss')</script> & Co.",
        asin="B08N5WRWNW",
        marketplace="it",
        price_paid=59.90,
        return_deadline=tomorrow,
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await list_handler(update, context)

    # Verify HTML characters are escaped
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]

    # Should contain escaped version
    assert "&lt;script&gt;" in message
    assert "&amp;" in message

    # Should NOT contain unescaped version (potential XSS)
    assert "<script>" not in message
    assert (
        "alert('xss')" not in message
        or "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in message
    )
