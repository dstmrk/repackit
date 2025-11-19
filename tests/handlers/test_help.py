"""Tests for handlers/help.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers.help import help_handler


@pytest.mark.asyncio
async def test_help_handler():
    """Test /help handler returns help message."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await help_handler(update, context)

    # Verify help message was sent
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args
    message = call_args[0][0]

    # Check message contains key sections
    assert "Comandi disponibili" in message
    assert "/add" in message
    assert "/list" in message
    assert "/delete" in message
    assert "/update" in message
    assert "/start" in message
    assert "/help" in message
    assert "/feedback" in message

    # Check it explains how the bot works
    assert "Come funziona" in message
    assert "monitoraggio" in message.lower()

    # Verify Markdown formatting
    assert call_args[1]["parse_mode"] == "Markdown"


@pytest.mark.asyncio
async def test_help_handler_multiple_users():
    """Test /help handler works for different users."""
    for user_id in [123, 456, 789]:
        update = MagicMock()
        update.effective_user.id = user_id
        update.message.reply_text = AsyncMock()
        context = MagicMock()

        await help_handler(update, context)

        # Verify message was sent for each user
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Comandi disponibili" in message
