"""Retry utilities with exponential backoff for transient errors."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from telegram.error import NetworkError, RetryAfter, TimedOut

from config import get_config

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Errors that should trigger a retry (transient/network errors)
RETRYABLE_TELEGRAM_ERRORS = (NetworkError, TimedOut, RetryAfter)
RETRYABLE_HTTPX_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
)


async def retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    max_retries: int | None = None,
    base_delay: float | None = None,
    retryable_exceptions: tuple = RETRYABLE_TELEGRAM_ERRORS,
) -> T:
    """
    Execute an async function with exponential backoff retry on transient errors.

    Args:
        func: Async function to execute (no arguments, use lambda/partial for args)
        max_retries: Maximum retry attempts (default from config)
        base_delay: Base delay in seconds, doubles each retry (default from config)
        retryable_exceptions: Tuple of exception types to retry on

    Returns:
        Result from the function

    Raises:
        The last exception if all retries fail, or non-retryable exceptions immediately

    Example:
        result = await retry_with_backoff(
            lambda: bot.send_message(chat_id=123, text="Hello")
        )
    """
    cfg = get_config()
    max_retries = max_retries if max_retries is not None else cfg.telegram_max_retries
    base_delay = base_delay if base_delay is not None else cfg.telegram_retry_base_delay

    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_exception = e

            # Handle RetryAfter specially - use the suggested delay
            if isinstance(e, RetryAfter):
                delay = e.retry_after
                logger.warning(
                    f"Rate limited by Telegram, waiting {delay}s (attempt {attempt + 1}/{max_retries + 1})"
                )
            else:
                # Exponential backoff: base_delay * 2^attempt
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Transient error: {type(e).__name__}: {e}. "
                    f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                )

            # Don't sleep after last attempt
            if attempt < max_retries:
                await asyncio.sleep(delay)

    # All retries exhausted
    logger.error(f"All {max_retries + 1} attempts failed. Last error: {last_exception}")
    raise last_exception  # type: ignore[misc]


async def send_telegram_message_with_retry(
    send_func: Callable[[], Awaitable[T]],
    user_id: int,
    max_retries: int | None = None,
    base_delay: float | None = None,
) -> T | None:
    """
    Send a Telegram message with retry logic, returning None on permanent failure.

    This is a convenience wrapper for retry_with_backoff that:
    - Catches and logs non-retryable errors (user blocked bot, etc.)
    - Returns None instead of raising on permanent failures
    - Includes user_id in log messages for debugging

    Args:
        send_func: Async function that sends the message
        user_id: User ID for logging purposes
        max_retries: Maximum retry attempts (default from config)
        base_delay: Base delay in seconds (default from config)

    Returns:
        Result from send_func, or None if sending failed permanently
    """
    try:
        return await retry_with_backoff(
            send_func,
            max_retries=max_retries,
            base_delay=base_delay,
        )
    except RETRYABLE_TELEGRAM_ERRORS as e:
        # All retries exhausted
        logger.error(f"Failed to send message to user {user_id} after retries: {e}")
        return None
    except Exception as e:
        # Non-retryable error (user blocked bot, chat not found, etc.)
        logger.warning(f"Permanent error sending to user {user_id}: {type(e).__name__}: {e}")
        return None


async def httpx_post_with_retry(
    url: str,
    payload: dict,
    timeout: float = 10.0,
    max_retries: int | None = None,
    base_delay: float | None = None,
) -> httpx.Response | None:
    """
    Make an HTTP POST request with retry logic for transient errors.

    Args:
        url: URL to POST to
        payload: JSON payload
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts (default from config)
        base_delay: Base delay in seconds (default from config)

    Returns:
        httpx.Response on success, None on failure
    """

    async def do_request() -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(url, json=payload)

    try:
        return await retry_with_backoff(
            do_request,
            max_retries=max_retries,
            base_delay=base_delay,
            retryable_exceptions=RETRYABLE_HTTPX_ERRORS,
        )
    except RETRYABLE_HTTPX_ERRORS as e:
        logger.error(f"HTTP request failed after retries: {e}")
        return None
    except Exception as e:
        logger.error(f"HTTP request failed with non-retryable error: {e}")
        return None
