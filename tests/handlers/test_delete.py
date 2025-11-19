"""Tests for handlers/delete.py with button-based selection."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.delete import delete_callback_handler, start_delete


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
async def test_start_delete_no_products(test_db):
    """Test /delete handler with no products."""
    # Create user with no products
    await database.add_user(user_id=123, language_code="it")

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await start_delete(update, context)

    # Verify empty message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Non hai prodotti" in message
    assert "Usa /add" in message


@pytest.mark.asyncio
async def test_start_delete_shows_product_list(test_db):
    """Test /delete handler shows product list with buttons."""
    # Create user and products
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123,
        product_name="Test Product 1",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=tomorrow,
    )
    await database.add_product(
        user_id=123,
        product_name="Test Product 2",
        asin="ASIN00002",
        marketplace="it",
        price_paid=75.0,
        return_deadline=tomorrow,
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await start_delete(update, context)

    # Verify message was sent with keyboard
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]

    # Check message content
    assert "Elimina un prodotto" in message
    assert "Seleziona il prodotto" in message

    # Check inline keyboard was provided
    assert "reply_markup" in call_args[1]
    reply_markup = call_args[1]["reply_markup"]
    assert reply_markup is not None

    # Verify products were NOT deleted
    products = await database.get_user_products(123)
    assert len(products) == 2


@pytest.mark.asyncio
async def test_delete_callback_select_product(test_db):
    """Test selecting a product shows confirmation dialog."""
    # Create user and product
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123,
        product_name="Test Product",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=tomorrow,
        min_savings_threshold=5.0,
    )

    products = await database.get_user_products(123)
    product_id = products[0]["id"]

    # Mock callback query
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = f"delete_select_{product_id}"

    context = MagicMock()

    await delete_callback_handler(update, context)

    # Verify callback was answered
    update.callback_query.answer.assert_called_once()

    # Verify confirmation message was shown
    update.callback_query.edit_message_text.assert_called_once()
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]

    # Check confirmation message content
    assert "Sei sicuro" in message
    assert "Test Product" in message
    assert "ASIN00001" in message
    assert "€50.00" in message
    assert "€5.00" in message  # min savings

    # Check inline keyboard was provided with confirmation buttons
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
        return_deadline=tomorrow,
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
    assert "Product 2" in message

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
        user_id=123,
        product_name="Test Product",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=tomorrow,
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
    assert "Nessun prodotto è stato eliminato" in message

    # Verify product was NOT deleted
    products_after = await database.get_user_products(123)
    assert len(products_after) == 1
    assert products_after[0]["asin"] == "ASIN00001"


@pytest.mark.asyncio
async def test_delete_callback_cancel_main(test_db):
    """Test cancel from main product list."""
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "delete_cancel_main"

    context = MagicMock()

    await delete_callback_handler(update, context)

    # Verify callback was answered
    update.callback_query.answer.assert_called_once()

    # Verify cancellation message was shown
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "annullata" in message


@pytest.mark.asyncio
async def test_delete_callback_product_not_found_on_select(test_db):
    """Test product selection with non-existent product."""
    # Create user with no products
    await database.add_user(user_id=123, language_code="it")

    # Mock callback query with non-existent product_id
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "delete_select_99999"  # Non-existent ID

    context = MagicMock()

    await delete_callback_handler(update, context)

    # Verify error message was shown
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "Prodotto non trovato" in message


@pytest.mark.asyncio
async def test_delete_callback_product_not_found_on_confirm(test_db):
    """Test delete confirmation with non-existent product."""
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
async def test_start_delete_database_error(test_db):
    """Test /delete handler handles database errors gracefully."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Mock database.get_user_products to raise an exception
    with patch("handlers.delete.database.get_user_products", side_effect=Exception("DB Error")):
        await start_delete(update, context)

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


@pytest.mark.asyncio
async def test_delete_product_without_name(test_db):
    """Test deleting product without name (legacy product)."""
    # Create user and product without name
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123,
        product_name=None,  # No name
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=tomorrow,
    )

    products = await database.get_user_products(123)
    product_id = products[0]["id"]

    # Mock callback query for selection
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = f"delete_select_{product_id}"

    context = MagicMock()

    await delete_callback_handler(update, context)

    # Verify confirmation shows fallback name
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "Prodotto senza nome" in message
