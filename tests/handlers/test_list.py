"""Tests for handlers/list.py."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.list import list_handler


@pytest.fixture
async def test_db():
    """Create a temporary test database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    original_path = database.DATABASE_PATH
    database.DATABASE_PATH = db_path

    await database.init_db()

    yield db_path

    database.DATABASE_PATH = original_path
    Path(db_path).unlink(missing_ok=True)
    Path(f"{db_path}-wal").unlink(missing_ok=True)
    Path(f"{db_path}-shm").unlink(missing_ok=True)


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
    assert call_args[1]["parse_mode"] == "Markdown"


@pytest.mark.asyncio
async def test_list_handler_single_product(test_db):
    """Test /list handler with single product."""
    # Create user and product
    await database.add_user(user_id=123, language_code="it")

    tomorrow = date.today() + timedelta(days=5)
    await database.add_product(
        user_id=123,
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
    assert call_args[1]["parse_mode"] == "Markdown"
    assert call_args[1]["disable_web_page_preview"] is True


@pytest.mark.asyncio
async def test_list_handler_multiple_products(test_db):
    """Test /list handler with multiple products."""
    # Create user and products
    await database.add_user(user_id=123, language_code="it")

    tomorrow = date.today() + timedelta(days=1)
    next_week = date.today() + timedelta(days=7)

    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )
    await database.add_product(
        user_id=123,
        asin="ASIN00002",
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
    assert "2 prodotto/i" in message


@pytest.mark.asyncio
async def test_list_handler_deadline_today(test_db):
    """Test /list handler with deadline today."""
    await database.add_user(user_id=123, language_code="it")

    today = date.today()
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=today
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
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=yesterday
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
        asin="ASIN00001",
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
