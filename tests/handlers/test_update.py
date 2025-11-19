"""Tests for handlers/update.py with conversational flow."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import ConversationHandler

import database
from handlers.update import (
    WAITING_FIELD_SELECTION,
    WAITING_PRODUCT_SELECTION,
    WAITING_VALUE_INPUT,
    cancel,
    handle_field_selection,
    handle_product_selection,
    handle_value_input,
    start_update,
)


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


# =================================================================================================
# start_update tests (Step 1: Show product list)
# =================================================================================================


@pytest.mark.asyncio
async def test_start_update_no_products(test_db):
    """Test /update with no products."""
    await database.add_user(user_id=123, language_code="it")

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await start_update(update, context)

    # Verify empty message was sent
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Non hai prodotti" in message

    # Verify conversation ended
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_start_update_shows_product_list(test_db):
    """Test /update shows product list with inline buttons."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, product_name="Product 1", asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )
    await database.add_product(
        user_id=123, product_name="Product 2", asin="ASIN00002", marketplace="it", price_paid=75.0, return_deadline=tomorrow
    )

    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await start_update(update, context)

    # Verify message with product list was sent
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Seleziona il prodotto" in message

    # Verify inline keyboard was provided
    assert "reply_markup" in call_args[1]

    # Verify state transition
    assert result == WAITING_PRODUCT_SELECTION


# =================================================================================================
# handle_product_selection tests (Step 2: Select field to update)
# =================================================================================================


@pytest.mark.asyncio
async def test_handle_product_selection_cancel(test_db):
    """Test canceling product selection."""
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "update_cancel"

    context = MagicMock()

    result = await handle_product_selection(update, context)

    # Verify cancellation message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "annullata" in message.lower()

    # Verify conversation ended
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_product_selection_shows_fields(test_db):
    """Test product selection shows field options."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, product_name="Test Product", asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    products = await database.get_user_products(123)
    product_id = products[0]["id"]

    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = f"update_product_{product_id}"

    context = MagicMock()
    context.user_data = {}

    result = await handle_product_selection(update, context)

    # Verify field selection message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "Cosa vuoi modificare" in message
    assert "Test Product" in message

    # Verify product data was stored in context
    assert context.user_data["update_product_id"] == product_id
    assert context.user_data["update_product_asin"] == "ASIN00001"

    # Verify state transition
    assert result == WAITING_FIELD_SELECTION


# =================================================================================================
# handle_field_selection tests (Step 3: Ask for new value)
# =================================================================================================


@pytest.mark.asyncio
async def test_handle_field_selection_price(test_db):
    """Test selecting price field."""
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "update_field_prezzo"

    context = MagicMock()
    context.user_data = {}

    result = await handle_field_selection(update, context)

    # Verify price input message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "prezzo" in message.lower()
    assert "59.90" in message

    # Verify field was stored
    assert context.user_data["update_field"] == "prezzo"

    # Verify state transition
    assert result == WAITING_VALUE_INPUT


@pytest.mark.asyncio
async def test_handle_field_selection_deadline(test_db):
    """Test selecting deadline field."""
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "update_field_scadenza"

    context = MagicMock()
    context.user_data = {}

    result = await handle_field_selection(update, context)

    # Verify deadline input message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "scadenza" in message.lower()
    assert "gg-mm-aaaa" in message

    # Verify field was stored
    assert context.user_data["update_field"] == "scadenza"

    # Verify state transition
    assert result == WAITING_VALUE_INPUT


@pytest.mark.asyncio
async def test_handle_field_selection_threshold(test_db):
    """Test selecting threshold field."""
    update = MagicMock()
    update.effective_user.id = 123
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "update_field_soglia"

    context = MagicMock()
    context.user_data = {"update_product_price_paid": 59.90}

    result = await handle_field_selection(update, context)

    # Verify threshold input message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "soglia" in message.lower()
    assert "€59.90" in message

    # Verify field was stored
    assert context.user_data["update_field"] == "soglia"

    # Verify state transition
    assert result == WAITING_VALUE_INPUT


# =================================================================================================
# handle_value_input tests (Step 4: Update the product)
# =================================================================================================


@pytest.mark.asyncio
async def test_handle_value_input_price_success(test_db):
    """Test successful price update."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, product_name="Test Product", asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    products = await database.get_user_products(123)
    product_id = products[0]["id"]

    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "55.00"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "update_product_id": product_id,
        "update_product_asin": "ASIN00001",
        "update_field": "prezzo",
    }

    result = await handle_value_input(update, context)

    # Verify success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "con successo" in message.lower()
    assert "€55.00" in message

    # Verify product was updated
    updated_products = await database.get_user_products(123)
    assert updated_products[0]["price_paid"] == 55.00

    # Verify conversation ended
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_value_input_price_invalid(test_db):
    """Test price update with invalid value."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, product_name="Test Product", asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    products = await database.get_user_products(123)
    product_id = products[0]["id"]

    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "invalid"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "update_product_id": product_id,
        "update_product_asin": "ASIN00001",
        "update_field": "prezzo",
    }

    result = await handle_value_input(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "non valido" in message.lower()

    # Verify product was NOT updated
    updated_products = await database.get_user_products(123)
    assert updated_products[0]["price_paid"] == 50.00

    # Verify stays in same state to retry
    assert result == WAITING_VALUE_INPUT


@pytest.mark.asyncio
async def test_handle_value_input_deadline_success(test_db):
    """Test successful deadline update."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, product_name="Test Product", asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    products = await database.get_user_products(123)
    product_id = products[0]["id"]

    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "60"  # 60 days from now
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "update_product_id": product_id,
        "update_product_asin": "ASIN00001",
        "update_field": "scadenza",
    }

    result = await handle_value_input(update, context)

    # Verify success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "con successo" in message.lower()

    # Verify deadline was updated
    updated_products = await database.get_user_products(123)
    expected_deadline = (date.today() + timedelta(days=60)).isoformat()
    assert updated_products[0]["return_deadline"] == expected_deadline

    # Verify conversation ended
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_value_input_threshold_success(test_db):
    """Test successful threshold update."""
    await database.add_user(user_id=123, language_code="it")
    tomorrow = date.today() + timedelta(days=1)
    await database.add_product(
        user_id=123, product_name="Test Product", asin="ASIN00001", marketplace="it", price_paid=50.0, return_deadline=tomorrow
    )

    products = await database.get_user_products(123)
    product_id = products[0]["id"]

    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "10.00"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "update_product_id": product_id,
        "update_product_asin": "ASIN00001",
        "update_product_price_paid": 50.0,
        "update_field": "soglia",
    }

    result = await handle_value_input(update, context)

    # Verify success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "con successo" in message.lower()
    assert "€10.00" in message

    # Verify threshold was updated
    updated_products = await database.get_user_products(123)
    assert updated_products[0]["min_savings_threshold"] == 10.00

    # Verify conversation ended
    assert result == ConversationHandler.END


# =================================================================================================
# cancel tests
# =================================================================================================


@pytest.mark.asyncio
async def test_cancel():
    """Test /cancel command."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"update_product_id": 1, "update_field": "prezzo"}

    result = await cancel(update, context)

    # Verify cancellation message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "annullata" in message.lower()

    # Verify user_data was cleared
    assert context.user_data == {}

    # Verify conversation ended
    assert result == ConversationHandler.END
