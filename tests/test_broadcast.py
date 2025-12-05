"""Tests for broadcast.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import broadcast
import database


@pytest.mark.asyncio
async def test_send_message_to_user_success():
    """Test sending message to user successfully."""
    with patch("httpx.AsyncClient") as mock_client:
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = await broadcast.send_message_to_user(123, "Test message")
        assert result is True


@pytest.mark.asyncio
async def test_send_message_to_user_http_error():
    """Test sending message with HTTP error."""
    with patch("httpx.AsyncClient") as mock_client:
        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = await broadcast.send_message_to_user(123, "Test message")
        assert result is False


@pytest.mark.asyncio
async def test_send_message_to_user_exception():
    """Test sending message with network exception."""
    with patch("httpx.AsyncClient") as mock_client:
        # Mock exception
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=Exception("Network error")
        )

        result = await broadcast.send_message_to_user(123, "Test message")
        assert result is False


@pytest.mark.asyncio
async def test_broadcast_message_no_users(test_db):
    """Test broadcast with no users in database."""
    sent, failed = await broadcast.broadcast_message("Test message")
    assert sent == 0
    assert failed == 0


@pytest.mark.asyncio
async def test_broadcast_message_success(test_db):
    """Test successful broadcast to multiple users."""
    # Add test users
    await database.add_user(user_id=123, language_code="it")
    await database.add_user(user_id=456, language_code="it")
    await database.add_user(user_id=789, language_code="it")

    with patch("broadcast.send_message_to_user", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        sent, failed = await broadcast.broadcast_message("Test message")

        assert sent == 3
        assert failed == 0
        assert mock_send.call_count == 3


@pytest.mark.asyncio
async def test_broadcast_message_partial_failure(test_db):
    """Test broadcast with some failures."""
    # Add test users
    await database.add_user(user_id=123, language_code="it")
    await database.add_user(user_id=456, language_code="it")
    await database.add_user(user_id=789, language_code="it")

    async def mock_send_side_effect(user_id, message):
        # Fail for user 456
        return user_id != 456

    with patch(
        "broadcast.send_message_to_user",
        new_callable=AsyncMock,
        side_effect=mock_send_side_effect,
    ):
        sent, failed = await broadcast.broadcast_message("Test message")

        assert sent == 2
        assert failed == 1


@pytest.mark.asyncio
async def test_broadcast_message_all_failures(test_db):
    """Test broadcast with all messages failing."""
    # Add test users
    await database.add_user(user_id=123, language_code="it")
    await database.add_user(user_id=456, language_code="it")

    with patch("broadcast.send_message_to_user", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = False

        sent, failed = await broadcast.broadcast_message("Test message")

        assert sent == 0
        assert failed == 2


@pytest.mark.asyncio
async def test_broadcast_message_exception_handling(test_db):
    """Test broadcast handles exceptions in send_message_to_user."""
    # Add test users
    await database.add_user(user_id=123, language_code="it")
    await database.add_user(user_id=456, language_code="it")

    with patch("broadcast.send_message_to_user", new_callable=AsyncMock) as mock_send:
        # First call raises exception, second succeeds
        mock_send.side_effect = [Exception("Network error"), True]

        sent, failed = await broadcast.broadcast_message("Test message")

        # Exception should be counted as failure
        assert sent == 1
        assert failed == 1


@pytest.mark.asyncio
async def test_broadcast_message_batching(test_db):
    """Test that broadcast processes users in batches."""
    # Add more users than batch size
    for i in range(30):  # More than BATCH_SIZE (10)
        await database.add_user(user_id=100 + i, language_code="it")

    with patch("broadcast.send_message_to_user", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            sent, failed = await broadcast.broadcast_message("Test message")

            assert sent == 30
            assert failed == 0
            # Should have called sleep 2 times (30 users / 10 per batch = 3 batches, 2 sleeps)
            assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_broadcast_message_long_message(test_db):
    """Test broadcast with a long message."""
    await database.add_user(user_id=123, language_code="it")

    long_message = "A" * 500  # Long message

    with patch("broadcast.send_message_to_user", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        sent, failed = await broadcast.broadcast_message(long_message)

        assert sent == 1
        assert failed == 0
        # Verify the full message was sent
        mock_send.assert_called_once_with(123, long_message)


@pytest.mark.asyncio
async def test_broadcast_message_html_formatting(test_db):
    """Test broadcast preserves HTML formatting."""
    await database.add_user(user_id=123, language_code="it")

    html_message = "<b>Bold</b> <i>italic</i> <code>code</code>"

    with patch("broadcast.send_message_to_user", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        sent, failed = await broadcast.broadcast_message(html_message)

        assert sent == 1
        mock_send.assert_called_once_with(123, html_message)
