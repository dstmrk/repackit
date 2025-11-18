"""Tests for handlers/delete.py."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.delete import delete_handler


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
async def test_delete_handler_no_args(test_db):
    """Test /delete handler with no arguments."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []

    await delete_handler(update, context)

    # Verify usage message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Utilizzo" in message
    assert "/delete" in message


@pytest.mark.asyncio
async def test_delete_handler_invalid_number(test_db):
    """Test /delete handler with invalid number."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["invalid"]

    await delete_handler(update, context)

    # Verify error message was sent
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Numero non valido" in message


@pytest.mark.asyncio
async def test_delete_handler_zero_number(test_db):
    """Test /delete handler with zero."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["0"]

    await delete_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Numero non valido" in message


@pytest.mark.asyncio
async def test_delete_handler_negative_number(test_db):
    """Test /delete handler with negative number."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["-5"]

    await delete_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Numero non valido" in message


@pytest.mark.asyncio
async def test_delete_handler_no_products(test_db):
    """Test /delete handler with no products."""
    # Create user with no products
    await database.add_user(user_id=123, language_code="it")

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1"]

    await delete_handler(update, context)

    # Verify empty message was sent
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Non hai prodotti" in message


@pytest.mark.asyncio
async def test_delete_handler_number_too_high(test_db):
    """Test /delete handler with number exceeding product count."""
    # Create user and product
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["5"]  # User only has 1 product

    await delete_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Numero prodotto non valido" in message
    assert "solo 1 prodotto" in message


@pytest.mark.asyncio
async def test_delete_handler_success(test_db):
    """Test /delete handler with valid deletion."""
    # Create user and products
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )
    await database.add_product(
        user_id=123, asin="ASIN00002", marketplace="it", price_paid=75.0, return_deadline=tomorrow
    )

    # Verify 2 products exist
    products_before = await database.get_user_products(123)
    assert len(products_before) == 2

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["2"]  # Delete second product

    await delete_handler(update, context)

    # Verify success message was sent
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "rimosso con successo" in message
    assert "ASIN00002" in message

    # Verify product was deleted
    products_after = await database.get_user_products(123)
    assert len(products_after) == 1
    assert products_after[0]["asin"] == "ASIN00001"


@pytest.mark.asyncio
async def test_delete_handler_database_error(test_db):
    """Test /delete handler handles database errors gracefully."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1"]

    # Mock database.delete_product to raise an exception
    with patch("handlers.delete.database.delete_product", side_effect=Exception("DB Error")):
        await delete_handler(update, context)

        # Verify error message was sent
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message
