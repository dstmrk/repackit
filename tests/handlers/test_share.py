"""Tests for handlers/share.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from handlers.share import share_handler


@pytest.mark.asyncio
async def test_share_handler_success():
    """Test /share handler shows referral link and slot count."""
    update = MagicMock()
    update.effective_user.id = 123456
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.username = "repackit_bot"

    with patch("handlers.share.database") as mock_db:
        mock_db.get_user_product_limit = AsyncMock(return_value=9)
        mock_db.DEFAULT_MAX_PRODUCTS = 21

        await share_handler(update, context)

        # Verify message was sent
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args

        message = call_args[0][0]
        kwargs = call_args[1]

        # Check message contains key information
        assert "Invita i tuoi amici" in message
        assert "9/21" in message  # Current slots
        assert "https://t.me/repackit_bot?start=123456" in message  # Referral link
        assert "Come funziona" in message
        assert "+3 slot" in message

        # Verify HTML formatting
        assert kwargs["parse_mode"] == "HTML"
        assert kwargs["disable_web_page_preview"] is True

        # Verify inline keyboard
        assert "reply_markup" in kwargs
        keyboard = kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].text == "📤 Condividi con un amico"
        assert "https://t.me/share/url" in keyboard.inline_keyboard[0][0].url


@pytest.mark.asyncio
async def test_share_handler_different_slot_counts():
    """Test /share handler with different slot counts."""
    test_cases = [
        (3, 21),  # New user
        (6, 21),  # Invited user
        (12, 21),  # User with some referrals
        (21, 21),  # User at max
    ]

    for current_slots, max_slots in test_cases:
        update = MagicMock()
        update.effective_user.id = 123
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.bot.username = "test_bot"

        with patch("handlers.share.database") as mock_db:
            mock_db.get_user_product_limit = AsyncMock(return_value=current_slots)
            mock_db.DEFAULT_MAX_PRODUCTS = max_slots

            await share_handler(update, context)

            # Verify message contains correct slot count
            update.message.reply_text.assert_called_once()
            call_args = update.message.reply_text.call_args
            message = call_args[0][0]

            assert f"{current_slots}/{max_slots}" in message


@pytest.mark.asyncio
async def test_share_handler_database_error():
    """Test /share handler handles database errors gracefully."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.username = "test_bot"

    with patch("handlers.share.database") as mock_db:
        # Simulate database error
        mock_db.get_user_product_limit = AsyncMock(side_effect=Exception("DB error"))

        await share_handler(update, context)

        # Verify error message was sent
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        message = call_args[0][0]

        assert "Errore" in message
        assert "Riprova più tardi" in message


@pytest.mark.asyncio
async def test_share_handler_referral_link_format():
    """Test /share handler generates correct referral link format."""
    user_ids = [123, 456789, 999999999]

    for user_id in user_ids:
        update = MagicMock()
        update.effective_user.id = user_id
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.bot.username = "my_bot"

        with patch("handlers.share.database") as mock_db:
            mock_db.get_user_product_limit = AsyncMock(return_value=6)
            mock_db.DEFAULT_MAX_PRODUCTS = 21

            await share_handler(update, context)

            # Verify referral link contains user ID
            call_args = update.message.reply_text.call_args
            message = call_args[0][0]

            expected_link = f"https://t.me/my_bot?start={user_id}"
            assert expected_link in message


@pytest.mark.asyncio
async def test_share_handler_share_button_url():
    """Test /share handler share button URL is properly formatted."""
    update = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.username = "test_bot"

    with patch("handlers.share.database") as mock_db:
        mock_db.get_user_product_limit = AsyncMock(return_value=6)
        mock_db.DEFAULT_MAX_PRODUCTS = 21

        await share_handler(update, context)

        # Verify share button URL
        call_args = update.message.reply_text.call_args
        keyboard = call_args[1]["reply_markup"]
        share_url = keyboard.inline_keyboard[0][0].url

        # URL should contain share endpoint and referral link
        assert "https://t.me/share/url" in share_url
        assert "https://t.me/test_bot?start=123" in share_url
        # Pre-filled text should be URL-encoded
        assert "text=" in share_url
