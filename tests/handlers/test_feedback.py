"""Tests for handlers/feedback.py."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

import database
from handlers.feedback import (
    MAX_FEEDBACK_LENGTH,
    MIN_FEEDBACK_LENGTH,
    WAITING_FEEDBACK_MESSAGE,
    cancel,
    handle_feedback_confirmation,
    handle_feedback_message,
    start_feedback,
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


@pytest.mark.asyncio
async def test_start_feedback(test_db):
    """Test start_feedback shows initial message."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Add user to database
    await database.add_user(123)

    result = await start_feedback(update, context)

    # Verify message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Invia il tuo feedback" in message
    assert f"{MIN_FEEDBACK_LENGTH}" in message
    assert f"{MAX_FEEDBACK_LENGTH}" in message

    # Verify state transition
    assert result == WAITING_FEEDBACK_MESSAGE


@pytest.mark.asyncio
async def test_handle_feedback_message_too_short():
    """Test handle_feedback_message rejects too short feedback."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "Short"  # 5 characters < MIN_FEEDBACK_LENGTH (10)
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await handle_feedback_message(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "troppo breve" in message
    assert f"{MIN_FEEDBACK_LENGTH}" in message

    # Verify stays in same state
    assert result == WAITING_FEEDBACK_MESSAGE


@pytest.mark.asyncio
async def test_handle_feedback_message_too_long():
    """Test handle_feedback_message rejects too long feedback."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "A" * (MAX_FEEDBACK_LENGTH + 1)  # 1001 characters
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await handle_feedback_message(update, context)

    # Verify error message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "troppo lungo" in message
    assert f"{MAX_FEEDBACK_LENGTH}" in message

    # Verify stays in same state
    assert result == WAITING_FEEDBACK_MESSAGE


@pytest.mark.asyncio
async def test_handle_feedback_message_valid():
    """Test handle_feedback_message shows preview for valid feedback."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "Questo è un feedback valido con più di 10 caratteri"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_feedback_message(update, context)

    # Verify feedback stored in context
    assert "feedback_message" in context.user_data
    assert context.user_data["feedback_message"] == update.message.text

    # Verify preview message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Anteprima" in message
    assert "feedback valido" in message
    assert "Vuoi inviare" in message

    # Verify inline keyboard
    reply_markup = call_args[1]["reply_markup"]
    assert reply_markup is not None

    # Verify conversation ends (waits for callback)
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_feedback_message_long_preview_truncation():
    """Test handle_feedback_message truncates long preview."""
    update = MagicMock()
    update.effective_user.id = 123
    # Create feedback > 200 chars for preview truncation
    update.message.text = "A" * 250
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    await handle_feedback_message(update, context)

    # Verify preview is truncated
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "..." in message  # Truncation indicator

    # Verify full message stored in context
    assert len(context.user_data["feedback_message"]) == 250


@pytest.mark.asyncio
async def test_handle_feedback_confirmation_send_success(test_db):
    """Test handle_feedback_confirmation sends feedback successfully."""
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "feedback_send"
    update.effective_user.id = 123

    context = MagicMock()
    feedback_msg = "Questo è un feedback di test molto utile"
    context.user_data = {"feedback_message": feedback_msg}

    await handle_feedback_confirmation(update, context)

    # Verify success message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "inviato con successo" in message
    assert "Grazie" in message

    # Verify feedback saved to database
    all_feedback = await database.get_all_feedback()
    assert len(all_feedback) == 1
    assert all_feedback[0]["user_id"] == 123
    assert all_feedback[0]["message"] == feedback_msg

    # Verify context cleared
    assert len(context.user_data) == 0


@pytest.mark.asyncio
async def test_handle_feedback_confirmation_cancel():
    """Test handle_feedback_confirmation cancels feedback."""
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "feedback_cancel"
    update.effective_user.id = 123

    context = MagicMock()
    context.user_data = {"feedback_message": "Test feedback"}

    await handle_feedback_confirmation(update, context)

    # Verify cancel message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "annullato" in message

    # Verify context cleared
    assert len(context.user_data) == 0


@pytest.mark.asyncio
async def test_handle_feedback_confirmation_missing_message():
    """Test handle_feedback_confirmation handles missing feedback_message."""
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "feedback_send"
    update.effective_user.id = 123

    context = MagicMock()
    context.user_data = {}  # No feedback_message

    await handle_feedback_confirmation(update, context)

    # Verify error message
    call_args = update.callback_query.edit_message_text.call_args
    message = call_args[0][0]
    assert "Errore" in message
    assert "non trovato" in message


@pytest.mark.asyncio
async def test_handle_feedback_confirmation_database_error(test_db):
    """Test handle_feedback_confirmation handles database errors."""
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = "feedback_send"
    update.effective_user.id = 123

    context = MagicMock()
    context.user_data = {"feedback_message": "Test feedback"}

    # Mock database error
    with patch("handlers.feedback.database.add_feedback", side_effect=Exception("DB Error")):
        await handle_feedback_confirmation(update, context)

        # Verify error message
        call_args = update.callback_query.edit_message_text.call_args
        message = call_args[0][0]
        assert "Errore" in message


@pytest.mark.asyncio
async def test_handle_feedback_message_with_special_characters():
    """Test handle_feedback_message accepts special characters."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "Bot eccezionale! 💯👍 Funziona benissimo 🚀"
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    result = await handle_feedback_message(update, context)

    # Verify feedback stored correctly
    assert context.user_data["feedback_message"] == update.message.text
    assert "💯" in context.user_data["feedback_message"]
    assert "🚀" in context.user_data["feedback_message"]

    # Verify preview shown
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Anteprima" in message

    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_cancel():
    """Test cancel command."""
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {"feedback_message": "Test"}

    result = await cancel(update, context)

    # Verify cancel message
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "annullato" in message

    # Verify context cleared
    assert len(context.user_data) == 0

    # Verify conversation ended
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_handle_feedback_message_strips_whitespace():
    """Test handle_feedback_message strips leading/trailing whitespace."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.text = "   Feedback con spazi   "
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    await handle_feedback_message(update, context)

    # Verify whitespace stripped
    assert context.user_data["feedback_message"] == "Feedback con spazi"


@pytest.mark.asyncio
async def test_start_feedback_first_time_no_rate_limit(test_db):
    """Test start_feedback allows first feedback (no rate limiting)."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Add user to database
    await database.add_user(123)

    result = await start_feedback(update, context)

    # Verify message was sent (not rate limited)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Invia il tuo feedback" in message
    assert "Limite raggiunto" not in message

    # Verify state transition to waiting for message
    assert result == WAITING_FEEDBACK_MESSAGE


@pytest.mark.asyncio
async def test_start_feedback_rate_limited_within_24_hours(test_db):
    """Test start_feedback blocks second feedback within 24 hours."""
    update = MagicMock()
    update.effective_user.id = 456
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Add user and first feedback
    await database.add_user(456)
    await database.add_feedback(456, "First feedback message with enough characters")

    result = await start_feedback(update, context)

    # Verify rate limit message shown
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Limite raggiunto" in message
    assert "Puoi inviare un nuovo feedback tra circa" in message

    # Verify conversation ended (blocked)
    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_start_feedback_rate_limit_expired_after_24_hours(test_db):
    """Test start_feedback allows feedback after 24 hours."""
    update = MagicMock()
    update.effective_user.id = 789
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Add user
    await database.add_user(789)

    # Mock old feedback timestamp (25 hours ago)
    old_timestamp = datetime.now() - timedelta(hours=25)
    mock_time = old_timestamp.isoformat()

    with patch("handlers.feedback.database.get_last_feedback_time", return_value=mock_time):
        result = await start_feedback(update, context)

    # Verify message was sent (not rate limited)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Invia il tuo feedback" in message
    assert "Limite raggiunto" not in message

    # Verify state transition to waiting for message
    assert result == WAITING_FEEDBACK_MESSAGE


@pytest.mark.asyncio
async def test_start_feedback_rate_limit_shows_hours_remaining(test_db):
    """Test start_feedback shows hours when >1 hour remaining."""
    update = MagicMock()
    update.effective_user.id = 111
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Add user
    await database.add_user(111)

    # Mock recent feedback (2 hours ago, 22 hours remaining)
    recent_timestamp = datetime.now() - timedelta(hours=2)
    mock_time = recent_timestamp.isoformat()

    with patch("handlers.feedback.database.get_last_feedback_time", return_value=mock_time):
        result = await start_feedback(update, context)

    # Verify rate limit message with hours
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Limite raggiunto" in message
    assert "22 ore" in message or "21 ore" in message  # Allow rounding

    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_start_feedback_rate_limit_shows_minutes_remaining(test_db):
    """Test start_feedback shows minutes when <1 hour remaining."""
    update = MagicMock()
    update.effective_user.id = 222
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Add user
    await database.add_user(222)

    # Mock recent feedback (23 hours 40 minutes ago, 20 minutes remaining)
    recent_timestamp = datetime.now() - timedelta(hours=23, minutes=40)
    mock_time = recent_timestamp.isoformat()

    with patch("handlers.feedback.database.get_last_feedback_time", return_value=mock_time):
        result = await start_feedback(update, context)

    # Verify rate limit message with minutes
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Limite raggiunto" in message
    assert "minut" in message  # "minuto" or "minuti"

    assert result == ConversationHandler.END


@pytest.mark.asyncio
async def test_start_feedback_rate_limit_invalid_timestamp_allows_feedback(test_db):
    """Test start_feedback allows feedback if timestamp parsing fails (fail open)."""
    update = MagicMock()
    update.effective_user.id = 333
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    # Add user
    await database.add_user(333)

    # Mock invalid timestamp that will fail to parse
    with patch("handlers.feedback.database.get_last_feedback_time", return_value="invalid"):
        result = await start_feedback(update, context)

    # Verify message was sent (not rate limited, fail open)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]
    assert "Invia il tuo feedback" in message
    assert "Limite raggiunto" not in message

    # Verify state transition to waiting for message
    assert result == WAITING_FEEDBACK_MESSAGE
