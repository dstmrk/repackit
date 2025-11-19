"""Tests for handlers/add.py."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

import database
from handlers.add import (
    MAX_PRODUCTS_PER_USER,
    WAITING_DEADLINE,
    WAITING_MIN_SAVINGS,
    WAITING_PRICE,
    WAITING_PRODUCT_NAME,
    WAITING_URL,
    cancel,
    handle_deadline,
    handle_min_savings,
    handle_price,
    handle_url,
    parse_deadline,
    start_add,
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


# ============================================================================
# parse_deadline tests
# ============================================================================


def test_parse_deadline_days():
    """Test parse_deadline with days format."""
    today = date.today()
    result = parse_deadline("30")
    expected = today + timedelta(days=30)
    assert result == expected


def test_parse_deadline_days_min_boundary():
    """Test parse_deadline with minimum days (1)."""
    today = date.today()
    result = parse_deadline("1")
    expected = today + timedelta(days=1)
    assert result == expected


def test_parse_deadline_days_max_boundary():
    """Test parse_deadline with maximum days (365)."""
    today = date.today()
    result = parse_deadline("365")
    expected = today + timedelta(days=365)
    assert result == expected


def test_parse_deadline_days_below_range():
    """Test parse_deadline with days below valid range (0)."""
    with pytest.raises(ValueError, match="giorni deve essere tra 1 e 365"):
        parse_deadline("0")


def test_parse_deadline_days_above_range():
    """Test parse_deadline with days above valid range (366)."""
    with pytest.raises(ValueError, match="giorni deve essere tra 1 e 365"):
        parse_deadline("366")


def test_parse_deadline_gg_mm_aaaa_format():
    """Test parse_deadline with gg-mm-aaaa date format."""
    result = parse_deadline("25-12-2024")
    assert result == date(2024, 12, 25)


def test_parse_deadline_gg_mm_aaaa_format_leap_year():
    """Test parse_deadline with leap year date."""
    result = parse_deadline("29-02-2024")
    assert result == date(2024, 2, 29)


def test_parse_deadline_invalid_format():
    """Test parse_deadline with invalid format."""
    with pytest.raises(ValueError, match="Formato non valido"):
        parse_deadline("invalid")


def test_parse_deadline_iso_format():
    """Test parse_deadline with ISO format (yyyy-mm-dd) for /update compatibility."""
    result = parse_deadline("2024-12-25")
    assert result == date(2024, 12, 25)


def test_parse_deadline_invalid_date():
    """Test parse_deadline with invalid date (e.g., 32nd day)."""
    with pytest.raises(ValueError, match="Formato non valido"):
        parse_deadline("32-13-2024")


# ============================================================================
# Conversational flow tests
# ============================================================================


@pytest.mark.asyncio
async def test_start_add():
    """Test /add command initiates conversation."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await start_add(update, context)

    # Verify it asks for product name (first step in new flow)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Come vuoi chiamare questo prodotto" in message
    assert "Esempio" in message

    # Verify it returns the correct state
    assert result == WAITING_PRODUCT_NAME


@pytest.mark.asyncio
async def test_handle_url_valid():
    """Test handling valid Amazon.it URL."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "https://amazon.it/dp/B08N5WRWNW"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_url(update, context)

    # Verify ASIN was stored
    assert context.user_data["product_asin"] == "B08N5WRWNW"
    assert context.user_data["product_marketplace"] == "it"

    # Verify it asks for price
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "prezzo che hai pagato" in message
    assert "B08N5WRWNW" in message

    # Verify it returns the correct state
    assert result == WAITING_PRICE


@pytest.mark.asyncio
async def test_handle_url_invalid_marketplace():
    """Test handling URL from non-.it marketplace."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "https://amazon.com/dp/B08N5WRWNW"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_url(update, context)

    # Verify error message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "URL non valido" in message or "Marketplace non supportato" in message
    assert "Amazon.it" in message

    # Verify it stays in same state
    assert result == WAITING_URL


@pytest.mark.asyncio
async def test_handle_url_invalid():
    """Test handling invalid URL."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "https://google.com"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_url(update, context)

    # Verify error message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "URL non valido" in message

    # Verify it stays in same state
    assert result == WAITING_URL


@pytest.mark.asyncio
async def test_handle_price_valid():
    """Test handling valid price."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "59.90"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_price(update, context)

    # Verify price was stored
    assert context.user_data["product_price"] == 59.90

    # Verify it asks for deadline
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "scadenza del reso" in message
    assert "59.90" in message

    # Verify it returns the correct state
    assert result == WAITING_DEADLINE


@pytest.mark.asyncio
async def test_handle_price_comma_separator():
    """Test handling price with comma as decimal separator."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "59,90"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_price(update, context)

    # Verify price was stored correctly
    assert context.user_data["product_price"] == 59.90
    assert result == WAITING_DEADLINE


@pytest.mark.asyncio
async def test_handle_price_invalid():
    """Test handling invalid price."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "invalid"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_price(update, context)

    # Verify error message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo non valido" in message

    # Verify it stays in same state
    assert result == WAITING_PRICE


@pytest.mark.asyncio
async def test_handle_price_negative():
    """Test handling negative price."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "-10"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_price(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo non valido" in message

    # Verify it stays in same state
    assert result == WAITING_PRICE


@pytest.mark.asyncio
async def test_handle_price_too_many_digits():
    """Test handling price with more than 16 digits."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "12345678901234567.99"  # 19 digits total
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_price(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo troppo lungo" in message or "16 cifre" in message

    # Verify it stays in same state
    assert result == WAITING_PRICE


@pytest.mark.asyncio
async def test_handle_deadline_days(test_db):
    """Test handling deadline as number of days."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.text = "30"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 59.90,
    }

    result = await handle_deadline(update, context)

    # Verify deadline was stored
    expected_deadline = date.today() + timedelta(days=30)
    assert context.user_data["product_deadline"] == expected_deadline

    # Verify it asks for min savings (new step)
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "risparmio minimo" in message

    # Verify conversation continues to min savings step
    assert result == WAITING_MIN_SAVINGS


@pytest.mark.asyncio
async def test_handle_deadline_date_format(test_db):
    """Test handling deadline as gg-mm-aaaa date."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    # Use a future date
    future_date = date.today() + timedelta(days=60)
    update.message.text = future_date.strftime("%d-%m-%Y")
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 59.90,
    }

    result = await handle_deadline(update, context)

    # Verify deadline was stored
    assert context.user_data["product_deadline"] == future_date

    # Verify it asks for min savings
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "risparmio minimo" in message

    # Verify conversation continues to min savings step
    assert result == WAITING_MIN_SAVINGS


@pytest.mark.asyncio
async def test_handle_deadline_invalid(test_db):
    """Test handling invalid deadline."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "invalid"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 59.90,
    }

    result = await handle_deadline(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Scadenza non valida" in message

    # Verify it stays in same state
    assert result == WAITING_DEADLINE


@pytest.mark.asyncio
async def test_handle_deadline_past_date(test_db):
    """Test handling deadline in the past."""
    update = MagicMock()
    update.effective_user.id = 123
    yesterday = date.today() - timedelta(days=1)
    update.message.text = yesterday.strftime("%d-%m-%Y")
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 59.90,
    }

    result = await handle_deadline(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "deve essere nel futuro" in message

    # Verify it stays in same state
    assert result == WAITING_DEADLINE


@pytest.mark.asyncio
async def test_handle_min_savings_product_limit(test_db):
    """Test adding product when limit is reached."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    # Add MAX_PRODUCTS_PER_USER products (reach the limit)
    for i in range(MAX_PRODUCTS_PER_USER):
        await database.add_product(
            user_id=user_id,
            product_name=f"Product {i}",
            asin=f"B08N5WRWN{i}",
            marketplace="it",
            price_paid=50.00 + i,
            return_deadline=tomorrow,
        )

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "5.00"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 59.90,
        "product_deadline": tomorrow,
    }

    result = await handle_min_savings(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Limite prodotti raggiunto" in message
    assert f"{MAX_PRODUCTS_PER_USER} prodotti" in message

    # Verify conversation ended
    assert result == ConversationHandler.END

    # Verify no additional product was added beyond limit
    products = await database.get_user_products(user_id)
    assert len(products) == MAX_PRODUCTS_PER_USER


@pytest.mark.asyncio
async def test_cancel():
    """Test /cancel command."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 59.90,
    }

    result = await cancel(update, context)

    # Verify cancel message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "annullata" in message

    # Verify conversation ended
    assert result == ConversationHandler.END

    # Verify user_data was cleared
    assert context.user_data == {}


@pytest.mark.asyncio
async def test_handle_min_savings_database_error(test_db):
    """Test handling database error gracefully."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.text = "5.00"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 59.90,
        "product_deadline": date.today() + timedelta(days=30),
    }

    # Mock database.add_product to raise an exception
    with patch("handlers.add.database.add_product", side_effect=Exception("DB Error")):
        result = await handle_min_savings(update, context)

        # Verify error message was sent
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message

        # Verify conversation ended
        assert result == ConversationHandler.END
