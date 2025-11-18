"""Tests for handlers/feedback.py."""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
from handlers.feedback import feedback_handler


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
async def test_feedback_handler_no_args(test_db):
    """Test /feedback handler with no arguments."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []

    await feedback_handler(update, context)

    # Verify usage message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Utilizzo" in message
    assert "/feedback" in message


@pytest.mark.asyncio
async def test_feedback_handler_success(test_db):
    """Test /feedback handler with valid feedback."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["Il", "bot", "funziona", "benissimo!"]

    await feedback_handler(update, context)

    # Verify success message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Feedback ricevuto" in message
    assert "Grazie" in message

    # Verify feedback was saved to database
    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 1
    assert all_feedback[0]["user_id"] == 123
    assert all_feedback[0]["message"] == "Il bot funziona benissimo!"


@pytest.mark.asyncio
async def test_feedback_handler_single_word(test_db):
    """Test /feedback handler with single word feedback."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["Ottimo!"]

    await feedback_handler(update, context)

    # Verify feedback was saved
    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 1
    assert all_feedback[0]["message"] == "Ottimo!"


@pytest.mark.asyncio
async def test_feedback_handler_long_message(test_db):
    """Test /feedback handler with long feedback message."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    long_message = [
        "Questo",
        "bot",
        "è",
        "veramente",
        "utile",
        "e",
        "mi",
        "sta",
        "aiutando",
        "a",
        "risparmiare",
        "molti",
        "soldi",
        "sugli",
        "acquisti",
        "Amazon!",
    ]
    context.args = long_message

    await feedback_handler(update, context)

    # Verify feedback was saved with correct content
    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 1
    assert all_feedback[0]["message"] == " ".join(long_message)


@pytest.mark.asyncio
async def test_feedback_handler_multiple_users(test_db):
    """Test /feedback handler with multiple users."""
    # User 1 feedback
    update1 = MagicMock()
    update1.effective_user.id = 123
    update1.message.reply_text = AsyncMock()
    context1 = MagicMock()
    context1.args = ["Ottimo", "bot!"]

    await feedback_handler(update1, context1)

    # User 2 feedback
    update2 = MagicMock()
    update2.effective_user.id = 456
    update2.message.reply_text = AsyncMock()
    context2 = MagicMock()
    context2.args = ["Funziona", "bene"]

    await feedback_handler(update2, context2)

    # Verify both feedbacks were saved
    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 2

    # Check user IDs
    user_ids = {fb["user_id"] for fb in all_feedback}
    assert user_ids == {123, 456}


@pytest.mark.asyncio
async def test_feedback_handler_special_characters(test_db):
    """Test /feedback handler with special characters."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["Bot", "eccezionale!", "💯", "👍"]

    await feedback_handler(update, context)

    # Verify feedback with special characters was saved
    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 1
    assert "💯" in all_feedback[0]["message"]
    assert "👍" in all_feedback[0]["message"]


@pytest.mark.asyncio
async def test_feedback_handler_database_error(test_db):
    """Test /feedback handler handles database errors gracefully."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["Test", "feedback"]

    # Mock database.add_feedback to raise an exception
    with patch("handlers.feedback.database.add_feedback", side_effect=Exception("DB Error")):
        await feedback_handler(update, context)

        # Verify error message was sent
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Errore" in message
