"""Tests for handlers/add.py."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.add import add_handler, parse_deadline


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
    result = parse_deadline("30", today)
    expected = today + timedelta(days=30)
    assert result == expected


def test_parse_deadline_iso_date():
    """Test parse_deadline with ISO date format."""
    result = parse_deadline("2024-12-25")
    assert result == date(2024, 12, 25)


def test_parse_deadline_invalid_days():
    """Test parse_deadline with invalid days (zero)."""
    with pytest.raises(ValueError, match="Days must be positive"):
        parse_deadline("0")


def test_parse_deadline_negative_days():
    """Test parse_deadline with negative days."""
    with pytest.raises(ValueError, match="Days must be positive"):
        parse_deadline("-5")


def test_parse_deadline_invalid_format():
    """Test parse_deadline with invalid format."""
    with pytest.raises(ValueError, match="Invalid deadline format"):
        parse_deadline("invalid")


# ============================================================================
# add_handler tests
# ============================================================================


@pytest.mark.asyncio
async def test_add_handler_no_args(test_db):
    """Test /add handler with no arguments."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []

    await add_handler(update, context)

    # Verify usage message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Utilizzo" in message
    assert "/add" in message


@pytest.mark.asyncio
async def test_add_handler_success_with_days(test_db):
    """Test /add handler with valid input (days format)."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "59.90", "30"]

    await add_handler(update, context)

    # Verify product was added to database
    products = await database.get_user_products(123)
    assert len(products) == 1
    assert products[0]["asin"] == "B08N5WRWNW"
    assert products[0]["price_paid"] == 59.90

    # Verify success message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "aggiunto con successo" in message
    assert "B08N5WRWNW" in message
    assert "€59.90" in message


@pytest.mark.asyncio
async def test_add_handler_success_with_iso_date(test_db):
    """Test /add handler with valid input (ISO date format)."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    future_date = (date.today() + timedelta(days=30)).isoformat()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "59.90", future_date]

    await add_handler(update, context)

    # Verify product was added
    products = await database.get_user_products(123)
    assert len(products) == 1
    assert products[0]["return_deadline"] == future_date


@pytest.mark.asyncio
async def test_add_handler_with_threshold(test_db):
    """Test /add handler with threshold parameter."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "59.90", "30", "5.00"]

    await add_handler(update, context)

    # Verify threshold was saved
    products = await database.get_user_products(123)
    assert len(products) == 1
    assert products[0]["min_savings_threshold"] == 5.00

    # Verify threshold is in message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "€5.00" in message


@pytest.mark.asyncio
async def test_add_handler_invalid_url(test_db):
    """Test /add handler with invalid Amazon URL."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://google.com", "59.90", "30"]

    await add_handler(update, context)

    # Verify error message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "URL Amazon non valido" in message

    # Verify no product was added
    products = await database.get_user_products(123)
    assert len(products) == 0


@pytest.mark.asyncio
async def test_add_handler_invalid_price(test_db):
    """Test /add handler with invalid price."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "invalid", "30"]

    await add_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo non valido" in message


@pytest.mark.asyncio
async def test_add_handler_negative_price(test_db):
    """Test /add handler with negative price."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "-10", "30"]

    await add_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prezzo non valido" in message


@pytest.mark.asyncio
async def test_add_handler_invalid_deadline(test_db):
    """Test /add handler with invalid deadline."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "59.90", "invalid"]

    await add_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Scadenza non valida" in message


@pytest.mark.asyncio
async def test_add_handler_past_deadline(test_db):
    """Test /add handler with deadline in the past."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "59.90", yesterday]

    await add_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "deve essere nel futuro" in message


@pytest.mark.asyncio
async def test_add_handler_threshold_exceeds_price(test_db):
    """Test /add handler with threshold greater than price."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "50.00", "30", "60.00"]

    await add_handler(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Soglia non valida" in message


@pytest.mark.asyncio
async def test_add_handler_comma_decimal_separator(test_db):
    """Test /add handler with comma as decimal separator."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "59,90", "30", "5,50"]

    await add_handler(update, context)

    # Verify product was added with correct values
    products = await database.get_user_products(123)
    assert len(products) == 1
    assert products[0]["price_paid"] == 59.90
    assert products[0]["min_savings_threshold"] == 5.50


@pytest.mark.asyncio
async def test_add_handler_database_error(test_db):
    """Test /add handler handles database errors gracefully."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["https://amazon.it/dp/B08N5WRWNW", "59.90", "30"]

    # Mock database.add_product to raise an exception
    with patch("handlers.add.database.add_product", side_effect=Exception("DB Error")):
        await add_handler(update, context)

        # Verify error message was sent
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message


@pytest.mark.asyncio
async def test_add_handler_multiple_marketplaces(test_db):
    """Test /add handler with products from different Amazon marketplaces."""
    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Test different marketplace URLs
    test_cases = [
        ("https://www.amazon.it/dp/B08N5WRWNW", "it", 59.90),
        ("https://www.amazon.com/dp/B08N5WRWNX", "com", 69.90),
        ("https://www.amazon.de/dp/B08N5WRWNY", "de", 79.90),
        ("https://www.amazon.fr/dp/B08N5WRWNZ", "fr", 89.90),
        ("https://www.amazon.co.uk/dp/B08N5WRNWA", "uk", 99.90),
    ]

    for url, expected_marketplace, price in test_cases:
        context.args = [url, str(price), "30"]
        await add_handler(update, context)

    # Verify all products were added with correct marketplace
    products = await database.get_user_products(123)
    assert len(products) == 5

    # Verify each product has correct marketplace (reverse order due to DESC sort)
    for i, (_, expected_marketplace, price) in enumerate(reversed(test_cases)):
        product = products[i]
        assert product["marketplace"] == expected_marketplace
        assert product["price_paid"] == price

    # Verify success message includes marketplace
    last_call_args = update.message.reply_text.call_args
    last_message = last_call_args[0][0]
    assert "amazon.uk" in last_message  # Last added was UK
