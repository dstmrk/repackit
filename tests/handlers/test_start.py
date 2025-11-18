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
    assert call_args[1]["parse_mode"] == "Markdown"


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
