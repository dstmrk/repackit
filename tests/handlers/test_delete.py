"""Tests for handlers/delete.py."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.delete import delete_callback_handler, delete_handler


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
async def test_delete_handler_shows_confirmation(test_db):
    """Test /delete handler shows confirmation with inline buttons."""
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
    context.args = ["1"]

    await delete_handler(update, context)

    # Verify confirmation message was sent with buttons
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]

    # Check message content
    assert "Sei sicuro" in message
    assert "ASIN00001" in message
    assert "€50.00" in message

    # Check inline keyboard was provided
    assert "reply_markup" in call_args[1]
    reply_markup = call_args[1]["reply_markup"]
    assert reply_markup is not None

    # Verify product was NOT deleted yet
    products = await database.get_user_products(123)
    assert len(products) == 1


@pytest.mark.asyncio
async def test_delete_callback_confirm(test_db):
    """Test delete confirmation callback deletes the product."""
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
    product_id = products_before[1]["id"]  # Second product

    # Mock callback query
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = f"delete_confirm_{product_id}"

    context = MagicMock()

    await delete_callback_handler(update, context)

    # Verify callback was answered
    update.callback_query.answer.assert_called_once()

    # Verify success message was shown
    update.callback_query.edit_message_text.assert_called_once()
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "eliminato con successo" in message
    assert "ASIN00002" in message

    # Verify product was actually deleted
    products_after = await database.get_user_products(123)
    assert len(products_after) == 1
    assert products_after[0]["asin"] == "ASIN00001"


@pytest.mark.asyncio
async def test_delete_callback_cancel(test_db):
    """Test delete cancellation callback does not delete the product."""
    # Create user and product
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    products_before = await database.get_user_products(123)
    assert len(products_before) == 1
    product_id = products_before[0]["id"]

    # Mock callback query
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = f"delete_cancel_{product_id}"

    context = MagicMock()

    await delete_callback_handler(update, context)

    # Verify callback was answered
    update.callback_query.answer.assert_called_once()

    # Verify cancellation message was shown
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "annullata" in message
    assert "non è stato eliminato" in message

    # Verify product was NOT deleted
    products_after = await database.get_user_products(123)
    assert len(products_after) == 1
    assert products_after[0]["asin"] == "ASIN00001"


@pytest.mark.asyncio
async def test_delete_callback_product_not_found(test_db):
    """Test delete callback with non-existent product."""
    # Create user with no products
    await database.add_user(user_id=123, language_code="it")

    # Mock callback query with non-existent product_id
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "delete_confirm_99999"  # Non-existent ID

    context = MagicMock()

    await delete_callback_handler(update, context)

    # Verify error message was shown
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "Prodotto non trovato" in message


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

    # Mock database.get_user_products to raise an exception
    with patch("handlers.delete.database.get_user_products", side_effect=Exception("DB Error")):
        await delete_handler(update, context)

        # Verify error message was sent
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message


@pytest.mark.asyncio
async def test_delete_callback_database_error(test_db):
    """Test delete callback handles database errors gracefully."""
    # Mock callback query
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "delete_confirm_1"

    context = MagicMock()

    # Mock database.get_user_products to raise an exception
    with patch("handlers.delete.database.get_user_products", side_effect=Exception("DB Error")):
        await delete_callback_handler(update, context)

        # Verify error message was shown
        call_args = update.callback_query.edit_message_text.call_args
        message = call_args[0][0]
        assert "Errore" in message
