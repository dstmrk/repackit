"""Tests for handlers/start.py."""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.start import start_handler


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
async def test_start_handler_new_user(test_db):
    """Test /start handler with new user."""
    # Create mock update and context
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Call handler
    await start_handler(update, context)

    # Verify user was registered
    user = await database.get_user(12345)
    assert user is not None
    assert user["user_id"] == 12345
    assert user["language_code"] == "it"

    # Verify welcome message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Benvenuto" in message
    assert "/add" in message
    assert "/list" in message
    assert call_args[1]["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_start_handler_existing_user(test_db):
    """Test /start handler with existing user."""
    # Register user first
    await database.add_user(user_id=12345, language_code="en")

    # Create mock update and context
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "en"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Call handler (should not fail with existing user)
    await start_handler(update, context)

    # Verify welcome message was sent
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_start_handler_database_error(test_db):
    """Test /start handler handles database errors gracefully."""
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Mock database.add_user to raise an exception
    with patch("handlers.start.database.add_user", side_effect=Exception("DB Error")):
        # Should not raise exception
        await start_handler(update, context)

        # Verify welcome message was still sent
        update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_start_handler_no_language_code(test_db):
    """Test /start handler when user has no language code."""
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = None
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await start_handler(update, context)

    # Verify user was registered with None language
    user = await database.get_user(12345)
    assert user is not None
    assert user["language_code"] is None

    # Verify welcome message was sent
    update.message.reply_text.assert_called_once()



@pytest.mark.asyncio
async def test_start_handler_with_valid_referral(test_db):
    """Test /start handler with valid referral code."""
    # Add referrer first
    await database.add_user(user_id=99999, language_code="it")

    # Create mock update and context with referral code
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["99999"]  # Referral code

    # Call handler
    await start_handler(update, context)

    # Verify user was registered with referral
    user = await database.get_user(12345)
    assert user is not None
    assert user["referred_by"] == 99999
    assert user["referral_bonus_given"] is False or user["referral_bonus_given"] == 0

    # Verify user got 6 slots (3 base + 3 bonus)
    limit = await database.get_user_product_limit(12345)
    assert limit == 6

    # Verify welcome message includes bonus message
    update.message.reply_text.assert_called_once()
    message = update.message.reply_text.call_args[0][0]
    assert "🎁" in message
    assert "slot bonus" in message
    assert "6 slot disponibili" in message


@pytest.mark.asyncio
async def test_start_handler_with_invalid_referral_code(test_db):
    """Test /start handler with non-existent referrer."""
    # Create mock update and context with invalid referral code
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["99999"]  # Non-existent referrer

    # Call handler
    await start_handler(update, context)

    # Verify user was registered without referral
    user = await database.get_user(12345)
    assert user is not None
    assert user["referred_by"] is None

    # Verify user got normal 3 slots
    limit = await database.get_user_product_limit(12345)
    assert limit == 3

    # Verify welcome message includes invalid code message
    update.message.reply_text.assert_called_once()
    message = update.message.reply_text.call_args[0][0]
    assert "non è valido" in message or "non risulta esistente" in message


@pytest.mark.asyncio
async def test_start_handler_with_self_referral(test_db):
    """Test /start handler with self-referral attempt."""
    # Create mock update and context with self-referral
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["12345"]  # Same as user_id (self-referral)

    # Call handler
    await start_handler(update, context)

    # Verify user was registered without referral
    user = await database.get_user(12345)
    assert user is not None
    assert user["referred_by"] is None

    # Verify user got normal 3 slots (no bonus)
    limit = await database.get_user_product_limit(12345)
    assert limit == 3

    # Verify no invalid code message (silently ignored)
    update.message.reply_text.assert_called_once()
    message = update.message.reply_text.call_args[0][0]
    assert "non è valido" not in message


@pytest.mark.asyncio
async def test_start_handler_with_malformed_referral_code(test_db):
    """Test /start handler with malformed referral code."""
    # Create mock update and context with non-numeric referral code
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["abc123"]  # Invalid format

    # Call handler
    await start_handler(update, context)

    # Verify user was registered without referral
    user = await database.get_user(12345)
    assert user is not None
    assert user["referred_by"] is None

    # Verify user got normal 3 slots
    limit = await database.get_user_product_limit(12345)
    assert limit == 3

    # Verify no error message (silently ignored)
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_start_handler_existing_user_ignores_referral(test_db):
    """Test that existing users don't get referral applied."""
    # Register user first
    await database.add_user(user_id=12345, language_code="it")
    await database.set_user_max_products(12345, 10)

    # Add a potential referrer
    await database.add_user(user_id=99999, language_code="it")

    # Try to use referral code as existing user
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.language_code = "it"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["99999"]

    await start_handler(update, context)

    # Verify referral wasn't applied
    user = await database.get_user(12345)
    assert user["referred_by"] is None

    # Verify slots weren't changed
    limit = await database.get_user_product_limit(12345)
    assert limit == 10

