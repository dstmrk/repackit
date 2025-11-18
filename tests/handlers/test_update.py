"""Tests for handlers/update.py."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.update import update_handler


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
async def test_update_handler_no_args(test_db):
    """Test /update handler with no arguments."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []

    await update_handler(update, context)

    # Verify usage message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Utilizzo" in message
    assert "/update" in message


@pytest.mark.asyncio
async def test_update_handler_invalid_number(test_db):
    """Test /update handler with invalid product number."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["invalid", "prezzo", "50.00"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Numero prodotto non valido" in message


@pytest.mark.asyncio
async def test_update_handler_negative_number(test_db):
    """Test /update handler with negative product number."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["-1", "prezzo", "50.00"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Numero prodotto non valido" in message


@pytest.mark.asyncio
async def test_update_handler_invalid_field(test_db):
    """Test /update handler with invalid field name."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "invalid", "50.00"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Campo non valido" in message


@pytest.mark.asyncio
async def test_update_handler_no_products(test_db):
    """Test /update handler with no products."""
    await database.add_user(user_id=123, language_code="it")

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "prezzo", "50.00"]

    await update_handler(update, context)

    # Verify empty message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Non hai prodotti" in message


@pytest.mark.asyncio
async def test_update_handler_number_too_high(test_db):
    """Test /update handler with number exceeding product count."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["5", "prezzo", "50.00"]  # User only has 1 product

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Numero prodotto non valido" in message


@pytest.mark.asyncio
async def test_update_handler_price_success(test_db):
    """Test /update handler with valid price update."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "prezzo", "55.00"]

    await update_handler(update, context)

    # Verify success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo aggiornato" in message
    assert "€55.00" in message

    # Verify price was updated in database
    products = await database.get_user_products(123)
    assert products[0]["price_paid"] == 55.0


@pytest.mark.asyncio
async def test_update_handler_price_invalid(test_db):
    """Test /update handler with invalid price."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "prezzo", "invalid"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo non valido" in message


@pytest.mark.asyncio
async def test_update_handler_price_negative(test_db):
    """Test /update handler with negative price."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "prezzo", "-10"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo non valido" in message


@pytest.mark.asyncio
async def test_update_handler_price_comma_separator(test_db):
    """Test /update handler with comma decimal separator for price."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "prezzo", "55,50"]

    await update_handler(update, context)

    # Verify success and correct price
    products = await database.get_user_products(123)
    assert products[0]["price_paid"] == 55.5


@pytest.mark.asyncio
async def test_update_handler_deadline_success_days(test_db):
    """Test /update handler with valid deadline update (days format)."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "scadenza", "15"]

    await update_handler(update, context)

    # Verify success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Scadenza aggiornata" in message
    assert "tra 15 giorni" in message

    # Verify deadline was updated
    products = await database.get_user_products(123)
    expected_deadline = (date.today() + timedelta(days=15)).isoformat()
    assert products[0]["return_deadline"] == expected_deadline


@pytest.mark.asyncio
async def test_update_handler_deadline_success_iso(test_db):
    """Test /update handler with valid deadline update (ISO date format)."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    future_date = (date.today() + timedelta(days=30)).isoformat()
    context.args = ["1", "scadenza", future_date]

    await update_handler(update, context)

    # Verify success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Scadenza aggiornata" in message


@pytest.mark.asyncio
async def test_update_handler_deadline_invalid(test_db):
    """Test /update handler with invalid deadline."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "scadenza", "invalid"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Scadenza non valida" in message


@pytest.mark.asyncio
async def test_update_handler_deadline_past(test_db):
    """Test /update handler with deadline in the past."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    context.args = ["1", "scadenza", yesterday]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "deve essere nel futuro" in message


@pytest.mark.asyncio
async def test_update_handler_threshold_success(test_db):
    """Test /update handler with valid threshold update."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "soglia", "10.00"]

    await update_handler(update, context)

    # Verify success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Soglia aggiornata" in message
    assert "€10.00" in message

    # Verify threshold was updated
    products = await database.get_user_products(123)
    assert products[0]["min_savings_threshold"] == 10.0


@pytest.mark.asyncio
async def test_update_handler_threshold_invalid(test_db):
    """Test /update handler with invalid threshold."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "soglia", "invalid"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Soglia non valida" in message


@pytest.mark.asyncio
async def test_update_handler_threshold_negative(test_db):
    """Test /update handler with negative threshold."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "soglia", "-5"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Soglia non valida" in message


@pytest.mark.asyncio
async def test_update_handler_threshold_exceeds_price(test_db):
    """Test /update handler with threshold greater than price."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "soglia", "60.00"]

    await update_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Soglia non valida" in message


@pytest.mark.asyncio
async def test_update_handler_threshold_comma_separator(test_db):
    """Test /update handler with comma decimal separator for threshold."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "soglia", "10,50"]

    await update_handler(update, context)

    # Verify success and correct threshold
    products = await database.get_user_products(123)
    assert products[0]["min_savings_threshold"] == 10.5


@pytest.mark.asyncio
async def test_update_handler_database_error(test_db):
    """Test /update handler handles database errors gracefully."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, asin="ASIN00001", price_paid=50.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1", "prezzo", "55.00"]

    # Mock database.update_product to raise an exception
    with patch("handlers.update.database.update_product", side_effect=Exception("DB Error")):
        await update_handler(update, context)

        # Verify error message was sent
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message
