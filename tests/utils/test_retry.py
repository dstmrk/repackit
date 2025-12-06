"""Tests for retry utilities."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from telegram.error import NetworkError, RetryAfter, TimedOut

from utils.retry import (
    httpx_post_with_retry,
    retry_with_backoff,
    send_telegram_message_with_retry,
)


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """Test successful execution on first attempt."""
        func = AsyncMock(return_value="success")

        result = await retry_with_backoff(func, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """Test successful execution after transient failure."""
        func = AsyncMock(side_effect=[NetworkError("connection failed"), "success"])

        result = await retry_with_backoff(func, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """Test that exception is raised after all retries fail."""
        error = NetworkError("persistent failure")
        func = AsyncMock(side_effect=error)

        with pytest.raises(NetworkError):
            await retry_with_backoff(func, max_retries=2, base_delay=0.01)

        # Initial attempt + 2 retries = 3 calls
        assert func.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_not_retried(self):
        """Test that non-retryable errors are raised immediately."""
        func = AsyncMock(side_effect=ValueError("not retryable"))

        with pytest.raises(ValueError):
            await retry_with_backoff(func, max_retries=3, base_delay=0.01)

        # Should not retry
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_timed_out_is_retryable(self):
        """Test that TimedOut errors are retried."""
        func = AsyncMock(side_effect=[TimedOut(), "success"])

        result = await retry_with_backoff(func, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_after_uses_suggested_delay(self):
        """Test that RetryAfter uses the suggested delay."""
        retry_error = RetryAfter(retry_after=0.01)
        func = AsyncMock(side_effect=[retry_error, "success"])

        result = await retry_with_backoff(func, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert func.call_count == 2

    @pytest.mark.asyncio
    async def test_custom_retryable_exceptions(self):
        """Test with custom retryable exceptions."""
        func = AsyncMock(side_effect=[ValueError("transient"), "success"])

        result = await retry_with_backoff(
            func,
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )

        assert result == "success"
        assert func.call_count == 2


class TestSendTelegramMessageWithRetry:
    """Tests for send_telegram_message_with_retry function."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Test successful message sending."""
        send_func = AsyncMock(return_value="message_sent")

        result = await send_telegram_message_with_retry(
            send_func, user_id=123, max_retries=1, base_delay=0.01
        )

        assert result == "message_sent"

    @pytest.mark.asyncio
    async def test_returns_none_on_permanent_failure(self):
        """Test that None is returned on permanent (non-retryable) failure."""
        send_func = AsyncMock(side_effect=ValueError("user blocked bot"))

        result = await send_telegram_message_with_retry(
            send_func, user_id=123, max_retries=1, base_delay=0.01
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_after_retries_exhausted(self):
        """Test that None is returned after all retries fail."""
        send_func = AsyncMock(side_effect=NetworkError("network down"))

        result = await send_telegram_message_with_retry(
            send_func, user_id=123, max_retries=1, base_delay=0.01
        )

        assert result is None


class TestHttpxPostWithRetry:
    """Tests for httpx_post_with_retry function."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Test successful HTTP POST."""
        mock_response = httpx.Response(200, json={"ok": True})

        with patch("utils.retry.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await httpx_post_with_retry(
                "https://api.example.com/endpoint",
                {"key": "value"},
                max_retries=1,
                base_delay=0.01,
            )

        assert result is not None
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self):
        """Test that None is returned on persistent connection error."""
        with patch("utils.retry.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await httpx_post_with_retry(
                "https://api.example.com/endpoint",
                {"key": "value"},
                max_retries=1,
                base_delay=0.01,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self):
        """Test that timeouts are retried."""
        mock_response = httpx.Response(200, json={"ok": True})

        with patch("utils.retry.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[httpx.ReadTimeout("timeout"), mock_response])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await httpx_post_with_retry(
                "https://api.example.com/endpoint",
                {"key": "value"},
                max_retries=2,
                base_delay=0.01,
            )

        assert result is not None
        assert result.status_code == 200
        assert mock_client.post.call_count == 2
