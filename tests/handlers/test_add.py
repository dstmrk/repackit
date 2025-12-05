"""Tests for handlers/add.py."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from telegram.ext import ConversationHandler

import database
from handlers.add import (
    WAITING_DEADLINE,
    WAITING_MIN_SAVINGS,
    WAITING_PRICE,
    WAITING_PRODUCT_NAME,
    WAITING_URL,
    cancel,
    handle_deadline,
    handle_min_savings,
    handle_price,
    handle_product_name,
    handle_url,
    start_add,
)
from handlers.validators import parse_deadline

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
    result = parse_deadline("25-12-2025")
    assert result == date(2025, 12, 25)


def test_parse_deadline_gg_mm_aaaa_format_leap_year():
    """Test parse_deadline with date format within 365 days limit."""
    # Use a date within 365 days (e.g., 200 days from today)
    future_date = date.today() + timedelta(days=200)
    date_str = future_date.strftime("%d-%m-%Y")
    result = parse_deadline(date_str)
    assert result == future_date


def test_parse_deadline_invalid_format():
    """Test parse_deadline with invalid format."""
    with pytest.raises(ValueError, match="Formato non valido"):
        parse_deadline("invalid")


def test_parse_deadline_iso_format():
    """Test parse_deadline with ISO format (yyyy-mm-dd) for /update compatibility."""
    result = parse_deadline("2025-12-25")
    assert result == date(2025, 12, 25)


def test_parse_deadline_invalid_date():
    """Test parse_deadline with invalid date (e.g., 32nd day)."""
    with pytest.raises(ValueError, match="Data non valida"):
        parse_deadline("32-13-2025")


# ============================================================================
# Conversational flow tests
# ============================================================================


@pytest.mark.asyncio
@patch("handlers.add.database.get_user_product_limit", new_callable=AsyncMock)
@patch("handlers.add.database.get_user_products", new_callable=AsyncMock)
@patch("handlers.add.database.add_user", new_callable=AsyncMock)
async def test_start_add(mock_add_user, mock_get_products, mock_get_limit):
    """Test /add command initiates conversation when user has space."""
    # Mock database responses (user has 0/3 products - has space)
    mock_get_products.return_value = []
    mock_get_limit.return_value = 3

    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await start_add(update, context)

    # Verify database calls were made
    mock_add_user.assert_called_once_with(user_id=123, language_code="it")
    mock_get_products.assert_called_once_with(123)
    mock_get_limit.assert_called_once_with(123)

    # Verify it asks for product name (first step in new flow)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Come vuoi chiamare questo prodotto" in message
    assert "Esempio" in message

    # Verify it returns the correct state
    assert result == WAITING_PRODUCT_NAME


@pytest.mark.asyncio
@patch("handlers.add.database.get_user_product_limit", new_callable=AsyncMock)
@patch("handlers.add.database.get_user_products", new_callable=AsyncMock)
@patch("handlers.add.database.add_user", new_callable=AsyncMock)
async def test_start_add_limit_reached(mock_add_user, mock_get_products, mock_get_limit):
    """Test /add command blocks when user has reached product limit."""
    # Mock database responses (user has 3/3 products - limit reached)
    mock_get_products.return_value = [
        {"id": 1, "product_name": "Product 1"},
        {"id": 2, "product_name": "Product 2"},
        {"id": 3, "product_name": "Product 3"},
    ]
    mock_get_limit.return_value = 3

    update = MagicMock()
    update.effective_user.id = 123
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await start_add(update, context)

    # Verify database calls were made
    mock_add_user.assert_called_once_with(user_id=123, language_code="it")
    mock_get_products.assert_called_once_with(123)
    mock_get_limit.assert_called_once_with(123)

    # Verify it shows limit reached error
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Limite raggiunto" in message
    assert "3/3 prodotti" in message

    # Verify it ends conversation
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_product_name_valid():
    """Test handling valid product name."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "iPhone 15 Pro"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_product_name(update, context)

    # Verify product name was stored
    assert context.user_data["product_name"] == "iPhone 15 Pro"

    # Verify it asks for URL
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Nome salvato" in message
    assert "iPhone 15 Pro" in message
    assert "link del prodotto Amazon.it" in message

    # Verify it returns the correct state
    assert result == WAITING_URL


@pytest.mark.asyncio
async def test_handle_product_name_too_short():
    """Test handling product name that's too short."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "ab"  # Only 2 characters
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_product_name(update, context)

    # Verify error message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Nome troppo corto" in message
    assert "almeno 3 caratteri" in message

    # Verify it stays in same state
    assert result == WAITING_PRODUCT_NAME


@pytest.mark.asyncio
async def test_handle_product_name_too_long():
    """Test handling product name that's too long."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "a" * 101  # 101 characters
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_product_name(update, context)

    # Verify error message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Nome troppo lungo" in message
    assert "massimo 100 caratteri" in message

    # Verify it stays in same state
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
    assert "nel passato" in message

    # Verify it stays in same state
    assert result == WAITING_DEADLINE


@pytest.mark.asyncio
async def test_handle_min_savings_valid(test_db):
    """Test handling valid min savings threshold."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    # Setup user and context with stored data
    await database.add_user(user_id=user_id, language_code="it")

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"  # Set to string, not MagicMock
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

    # Verify product was added
    products = await database.get_user_products(user_id)
    assert len(products) == 1
    assert products[0]["min_savings_threshold"] == 5.00

    # Verify success message
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Prodotto aggiunto con successo" in message
    assert "Test Product" in message
    assert "€5.00" in message

    # Verify conversation ended
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_min_savings_zero(test_db):
    """Test handling min savings of 0 (any price drop)."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    # Setup user and context with stored data
    await database.add_user(user_id=user_id, language_code="it")

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"  # Set to string, not MagicMock
    update.message.text = "0"
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

    # Verify product was added with 0 threshold
    products = await database.get_user_products(user_id)
    assert len(products) == 1
    assert products[0]["min_savings_threshold"] == 0.0

    # Verify success message mentions "qualsiasi risparmio"
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "qualsiasi risparmio" in message

    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_min_savings_negative(test_db):
    """Test handling negative min savings (invalid)."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    await database.add_user(user_id=user_id, language_code="it")

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"  # Set to string, not MagicMock
    update.message.text = "-5"
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
    assert "Valore non valido" in message
    assert "non negativo" in message

    # Verify product was NOT added
    products = await database.get_user_products(user_id)
    assert len(products) == 0

    # Verify it stays in same state
    assert result == WAITING_MIN_SAVINGS


@pytest.mark.asyncio
async def test_handle_min_savings_too_high(test_db):
    """Test handling min savings >= price paid (invalid)."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    await database.add_user(user_id=user_id, language_code="it")

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"  # Set to string, not MagicMock
    update.message.text = "60"  # Higher than price paid
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
    assert "Valore troppo alto" in message
    assert "inferiore al prezzo pagato" in message

    # Verify product was NOT added
    products = await database.get_user_products(user_id)
    assert len(products) == 0

    # Verify it stays in same state
    assert result == WAITING_MIN_SAVINGS


@pytest.mark.asyncio
async def test_handle_min_savings_invalid_format(test_db):
    """Test handling invalid min savings format."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    await database.add_user(user_id=user_id, language_code="it")

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"  # Set to string, not MagicMock
    update.message.text = "abc"  # Not a number
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
    assert "Valore non valido" in message
    assert "abc" in message

    # Verify product was NOT added
    products = await database.get_user_products(user_id)
    assert len(products) == 0

    # Verify it stays in same state
    assert result == WAITING_MIN_SAVINGS


@pytest.mark.asyncio
async def test_handle_min_savings_product_limit(test_db):
    """Test adding product when limit is reached."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    # Add user with initial limit (5 products)
    await database.add_user(user_id, "it")
    await database.set_user_max_products(user_id, database.INITIAL_MAX_PRODUCTS)

    # Add INITIAL_MAX_PRODUCTS products (reach the limit)
    for i in range(database.INITIAL_MAX_PRODUCTS):
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
    assert "Limite raggiunto" in message
    assert f"{database.INITIAL_MAX_PRODUCTS}/{database.INITIAL_MAX_PRODUCTS} prodotti" in message

    # Verify conversation ended
    assert result == ConversationHandler.END

    # Verify no additional product was added beyond limit
    products = await database.get_user_products(user_id)
    assert len(products) == database.INITIAL_MAX_PRODUCTS


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

    # Mock database.add_product_atomic to raise an exception
    with patch("handlers.add.database.add_product_atomic", side_effect=Exception("DB Error")):
        result = await handle_min_savings(update, context)

        # Verify error message was sent
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message

        # Verify conversation ended
        assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_min_savings_product_limit_trigger(test_db):
    """Test handling product limit exceeded error from database trigger."""
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

    # Mock database functions
    with patch("handlers.add.database.add_user", new_callable=AsyncMock):
        with patch("handlers.add.database.get_user_products", return_value=[]):
            with patch("handlers.add.database.get_user_product_limit", return_value=3):
                # Mock add_product_atomic to raise IntegrityError with trigger message
                with patch(
                    "handlers.add.database.add_product_atomic",
                    side_effect=aiosqlite.IntegrityError("Product limit exceeded"),
                ):
                    result = await handle_min_savings(update, context)

                    # Verify user-friendly error message was sent
                    call_args = update.message.reply_text.call_args
                    message = call_args[0][0]
                    assert "Limite prodotti raggiunto" in message
                    assert "parse_mode" in call_args[1]
                    assert call_args[1]["parse_mode"] == "HTML"

                    # Verify conversation ended
                    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_min_savings_other_integrity_error(test_db):
    """Test handling other IntegrityError (not product limit)."""
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

    # Mock database functions
    with patch("handlers.add.database.add_user", new_callable=AsyncMock):
        with patch("handlers.add.database.get_user_products", return_value=[]):
            with patch("handlers.add.database.get_user_product_limit", return_value=3):
                # Mock add_product_atomic to raise IntegrityError with different message
                with patch(
                    "handlers.add.database.add_product_atomic",
                    side_effect=aiosqlite.IntegrityError("FOREIGN KEY constraint failed"),
                ):
                    result = await handle_min_savings(update, context)

                    # Verify generic error message was sent
                    call_args = update.message.reply_text.call_args
                    message = call_args[0][0]
                    assert "Errore" in message
                    assert "Riprova più tardi" in message

                    # Verify conversation ended
                    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_min_savings_first_product_gives_referral_bonus(test_db):
    """Test that adding first product gives bonus to referrer."""
    user_id = 12345
    referrer_id = 99999

    # Add referrer and invitee
    await database.add_user(referrer_id, "it")
    await database.set_user_max_products(referrer_id, 6)  # Referrer has 6 slots
    await database.add_user(user_id, "it", referred_by=referrer_id)
    await database.set_user_max_products(user_id, 6)

    # Mock update and context
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
        "product_deadline": date.today() + timedelta(days=30),
    }
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    # Add product (first one)
    result = await handle_min_savings(update, context)

    # Verify product was added
    assert result == ConversationHandler.END
    products = await database.get_user_products(user_id)
    assert len(products) == 1

    # Verify referrer got +3 slots (6 → 9)
    referrer_limit = await database.get_user_product_limit(referrer_id)
    assert referrer_limit == 9

    # Verify bonus was marked as given
    user = await database.get_user(user_id)
    assert user["referral_bonus_given"] is True or user["referral_bonus_given"] == 1

    # Verify referrer was notified
    context.bot.send_message.assert_called_once()
    call_args = context.bot.send_message.call_args
    assert call_args[1]["chat_id"] == referrer_id
    notification = call_args[1]["text"]
    assert "primo prodotto" in notification
    assert "+3 slot" in notification
    assert "9/21" in notification


@pytest.mark.asyncio
async def test_handle_min_savings_referrer_at_cap_no_notification(test_db):
    """Test that referrer at 21 slots doesn't get notified."""
    user_id = 12345
    referrer_id = 99999

    # Add referrer at cap and invitee
    await database.add_user(referrer_id, "it")
    await database.set_user_max_products(referrer_id, 21)  # Already at cap
    await database.add_user(user_id, "it", referred_by=referrer_id)
    await database.set_user_max_products(user_id, 6)

    # Mock update and context
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "0"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 50.00,
        "product_deadline": date.today() + timedelta(days=20),
    }
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    # Add product
    result = await handle_min_savings(update, context)

    # Verify product was added
    assert result == ConversationHandler.END

    # Verify referrer stayed at 21
    referrer_limit = await database.get_user_product_limit(referrer_id)
    assert referrer_limit == 21

    # Verify bonus was marked as given anyway
    user = await database.get_user(user_id)
    assert user["referral_bonus_given"] is True or user["referral_bonus_given"] == 1

    # Verify NO notification was sent
    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_handle_min_savings_referrer_deleted_no_crash(test_db):
    """Test that deleted referrer doesn't crash product addition."""
    user_id = 12345
    referrer_id = 99999

    # Add invitee with non-existent referrer
    await database.add_user(user_id, "it", referred_by=referrer_id)  # referrer doesn't exist!
    await database.set_user_max_products(user_id, 6)

    # Mock update and context
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "0"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 50.00,
        "product_deadline": date.today() + timedelta(days=20),
    }
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    # Add product (should not crash)
    result = await handle_min_savings(update, context)

    # Verify product was added successfully despite missing referrer
    assert result == ConversationHandler.END
    products = await database.get_user_products(user_id)
    assert len(products) == 1


@pytest.mark.asyncio
async def test_handle_min_savings_notification_failure_doesnt_block(test_db):
    """Test that notification failure doesn't block product addition."""
    user_id = 12345
    referrer_id = 99999

    # Add referrer and invitee
    await database.add_user(referrer_id, "it")
    await database.set_user_max_products(referrer_id, 6)
    await database.add_user(user_id, "it", referred_by=referrer_id)
    await database.set_user_max_products(user_id, 6)

    # Mock update and context
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "0"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "product_name": "Test Product",
        "product_asin": "B08N5WRWNW",
        "product_marketplace": "it",
        "product_price": 50.00,
        "product_deadline": date.today() + timedelta(days=20),
    }
    context.bot = MagicMock()
    # Mock send_message to raise exception
    context.bot.send_message = AsyncMock(side_effect=Exception("Bot blocked"))

    # Add product (should not crash despite notification failure)
    result = await handle_min_savings(update, context)

    # Verify product was added
    assert result == ConversationHandler.END
    products = await database.get_user_products(user_id)
    assert len(products) == 1

    # Verify referrer got bonus despite notification failure
    referrer_limit = await database.get_user_product_limit(referrer_id)
    assert referrer_limit == 9

    # Verify bonus was marked as given
    user = await database.get_user(user_id)
    assert user["referral_bonus_given"] is True or user["referral_bonus_given"] == 1


@pytest.mark.asyncio
async def test_handle_min_savings_second_product_no_bonus(test_db):
    """Test that second product doesn't give bonus again."""
    user_id = 12345
    referrer_id = 99999

    # Add referrer and invitee
    await database.add_user(referrer_id, "it")
    await database.set_user_max_products(referrer_id, 6)
    await database.add_user(user_id, "it", referred_by=referrer_id)
    await database.set_user_max_products(user_id, 6)

    # Add first product
    await database.add_product(
        user_id=user_id,
        product_name="First Product",
        asin="B08N5WRWN1",
        marketplace="it",
        price_paid=50.00,
        return_deadline=date.today() + timedelta(days=30),
    )
    # Mark bonus as given
    await database.mark_referral_bonus_given(user_id)

    # Mock update and context for second product
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "0"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "product_name": "Second Product",
        "product_asin": "B08N5WRWN2",
        "product_marketplace": "it",
        "product_price": 40.00,
        "product_deadline": date.today() + timedelta(days=25),
    }
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    # Add second product
    result = await handle_min_savings(update, context)

    # Verify product was added
    assert result == ConversationHandler.END
    products = await database.get_user_products(user_id)
    assert len(products) == 2

    # Verify referrer did NOT get bonus again (still at 6)
    referrer_limit = await database.get_user_product_limit(referrer_id)
    assert referrer_limit == 6

    # Verify NO notification was sent
    context.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_handle_min_savings_shows_share_hint_when_low_on_slots(test_db):
    """Test /add shows /share hint when user has <3 slots available after adding."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    # Create user with 6 slots and 4 existing products
    await database.add_user(user_id, "it")
    await database.set_user_max_products(user_id, 6)

    # Add 4 products
    for i in range(4):
        await database.add_product(
            user_id=user_id,
            product_name=f"Product {i+1}",
            asin=f"ASIN0000{i+1}",
            marketplace="it",
            price_paid=50.0,
            return_deadline=tomorrow,
        )

    # Mock update and context for 5th product (will leave only 1 slot)
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "0"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "product_name": "Fifth Product",
        "product_asin": "B08N5WRWN5",
        "product_marketplace": "it",
        "product_price": 60.00,
        "product_deadline": tomorrow,
    }

    # Add 5th product
    result = await handle_min_savings(update, context)

    # Verify product was added
    assert result == ConversationHandler.END
    products = await database.get_user_products(user_id)
    assert len(products) == 5

    # Verify TWO messages were sent: success + hint
    assert update.message.reply_text.call_count == 2

    # Verify first message is success
    first_call = update.message.reply_text.call_args_list[0]
    first_message = first_call[0][0]
    assert "✅" in first_message
    assert "Fifth Product" in first_message

    # Verify second message is hint
    second_call = update.message.reply_text.call_args_list[1]
    second_message = second_call[0][0]
    assert "5/6 prodotti" in second_message
    assert "/share" in second_message
    assert "Stai esaurendo gli slot" in second_message


@pytest.mark.asyncio
async def test_handle_min_savings_no_share_hint_when_enough_slots(test_db):
    """Test /add doesn't show /share hint when user has ≥3 slots available."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    # Create user with 6 slots and 1 existing product
    await database.add_user(user_id, "it")
    await database.set_user_max_products(user_id, 6)

    # Add 1 product
    await database.add_product(
        user_id=user_id,
        product_name="Product 1",
        asin="ASIN00001",
        marketplace="it",
        price_paid=50.0,
        return_deadline=tomorrow,
    )

    # Mock update and context for 2nd product (will leave 4 slots)
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "0"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "product_name": "Second Product",
        "product_asin": "B08N5WRWN2",
        "product_marketplace": "it",
        "product_price": 60.00,
        "product_deadline": tomorrow,
    }

    # Add 2nd product
    result = await handle_min_savings(update, context)

    # Verify product was added
    assert result == ConversationHandler.END
    products = await database.get_user_products(user_id)
    assert len(products) == 2

    # Verify only ONE message was sent (success, no hint)
    assert update.message.reply_text.call_count == 1

    # Verify it's the success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "✅" in message
    assert "Second Product" in message
    assert "/share" not in message
    assert "Stai esaurendo" not in message


@pytest.mark.asyncio
async def test_handle_min_savings_no_share_hint_when_at_max_slots(test_db):
    """Test /add doesn't show /share hint when user is at max (21 slots)."""
    user_id = 123
    tomorrow = date.today() + timedelta(days=1)

    # Create user at max slots (21) with 19 existing products
    await database.add_user(user_id, "it")
    await database.set_user_max_products(user_id, 21)

    # Add 19 products
    for i in range(19):
        await database.add_product(
            user_id=user_id,
            product_name=f"Product {i+1}",
            asin=f"ASIN000{i+1:02d}",
            marketplace="it",
            price_paid=50.0,
            return_deadline=tomorrow,
        )

    # Mock update and context for 20th product (will leave only 1 slot, but at max)
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.language_code = "it"
    update.message.text = "0"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {
        "product_name": "Twentieth Product",
        "product_asin": "B08N5WRWN0",
        "product_marketplace": "it",
        "product_price": 60.00,
        "product_deadline": tomorrow,
    }

    # Add 20th product
    result = await handle_min_savings(update, context)

    # Verify product was added
    assert result == ConversationHandler.END
    products = await database.get_user_products(user_id)
    assert len(products) == 20

    # Verify only ONE message was sent (success, no hint because at max)
    assert update.message.reply_text.call_count == 1

    # Verify it's the success message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "✅" in message
    assert "Twentieth Product" in message
    assert "/share" not in message
    assert "Stai esaurendo" not in message
