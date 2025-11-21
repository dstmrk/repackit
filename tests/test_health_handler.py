"""Tests for health check handler."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import database
import health_handler


@pytest.fixture
async def test_db():
    """Create a temporary test database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Override DATABASE_PATH for testing
    original_path = database.DATABASE_PATH
    database.DATABASE_PATH = db_path

    # Initialize database
    await database.init_db()

    yield db_path

    # Cleanup
    database.DATABASE_PATH = original_path
    Path(db_path).unlink(missing_ok=True)
    Path(f"{db_path}-wal").unlink(missing_ok=True)
    Path(f"{db_path}-shm").unlink(missing_ok=True)


# ============================================================================
# Database system_status tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_system_status(test_db):
    """Test updating system status."""
    await database.update_system_status("last_scraper_run", "2024-01-15T10:00:00")

    status = await database.get_system_status("last_scraper_run")
    assert status is not None
    assert status["key"] == "last_scraper_run"
    assert status["value"] == "2024-01-15T10:00:00"


@pytest.mark.asyncio
async def test_update_system_status_overwrite(test_db):
    """Test that updating same key overwrites value."""
    await database.update_system_status("last_scraper_run", "2024-01-15T10:00:00")
    await database.update_system_status("last_scraper_run", "2024-01-15T11:00:00")

    status = await database.get_system_status("last_scraper_run")
    assert status["value"] == "2024-01-15T11:00:00"


@pytest.mark.asyncio
async def test_get_system_status_nonexistent(test_db):
    """Test getting status that doesn't exist."""
    status = await database.get_system_status("nonexistent_key")
    assert status is None


@pytest.mark.asyncio
async def test_get_all_system_status(test_db):
    """Test getting all system status entries."""
    await database.update_system_status("last_scraper_run", "2024-01-15T10:00:00")
    await database.update_system_status("last_checker_run", "2024-01-15T11:00:00")
    await database.update_system_status("last_cleanup_run", "2024-01-15T02:00:00")

    all_status = await database.get_all_system_status()
    assert len(all_status) == 3
    assert "last_scraper_run" in all_status
    assert "last_checker_run" in all_status
    assert "last_cleanup_run" in all_status


@pytest.mark.asyncio
async def test_get_stats_empty(test_db):
    """Test getting stats from empty database."""
    stats = await database.get_stats()
    assert stats["user_count"] == 0
    assert stats["product_count"] == 0
    assert stats["active_product_count"] == 0


@pytest.mark.asyncio
async def test_get_stats_with_data(test_db):
    """Test getting stats with data."""
    from datetime import date

    # Add users
    await database.add_user(111, "it")
    await database.add_user(222, "en")

    # Add products
    future_date = date.today() + timedelta(days=10)
    past_date = date.today() - timedelta(days=1)

    await database.add_product(111, "Active 1", "ACTIVE01", "it", 50.0, future_date)
    await database.add_product(111, "Active 2", "ACTIVE02", "it", 60.0, future_date)
    await database.add_product(222, "Expired", "EXPIRED1", "it", 70.0, past_date)

    stats = await database.get_stats()
    assert stats["user_count"] == 2
    assert stats["product_count"] == 3
    assert stats["active_product_count"] == 2  # Only non-expired


# ============================================================================
# Health check logic tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_status_all_tasks_healthy(test_db):
    """Test health status when all tasks recently ran."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Set all tasks as recently run
    await database.update_system_status("last_scraper_run", one_day_ago)
    await database.update_system_status("last_checker_run", one_day_ago)
    await database.update_system_status("last_cleanup_run", one_day_ago)

    health = await health_handler.get_health_status()

    assert health["status"] == "healthy"
    assert health["tasks"]["scraper"]["status"] == "ok"
    assert health["tasks"]["checker"]["status"] == "ok"
    assert health["tasks"]["cleanup"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_status_stale_task(test_db):
    """Test health status when one task is stale."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()
    three_days_ago = (now - timedelta(days=3)).isoformat()

    # Scraper is stale (> 2 days)
    await database.update_system_status("last_scraper_run", three_days_ago)
    await database.update_system_status("last_checker_run", one_day_ago)
    await database.update_system_status("last_cleanup_run", one_day_ago)

    health = await health_handler.get_health_status()

    assert health["status"] == "unhealthy"
    assert health["tasks"]["scraper"]["status"] == "stale"
    assert health["tasks"]["checker"]["status"] == "ok"
    assert health["tasks"]["cleanup"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_status_never_run(test_db):
    """Test health status when task has never run."""
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()

    # Only some tasks have run
    await database.update_system_status("last_scraper_run", one_day_ago)
    # checker and cleanup have never run

    health = await health_handler.get_health_status()

    assert health["status"] == "unhealthy"
    assert health["tasks"]["scraper"]["status"] == "ok"
    assert health["tasks"]["checker"]["status"] == "never_run"
    assert health["tasks"]["cleanup"]["status"] == "never_run"


@pytest.mark.asyncio
async def test_health_status_includes_stats(test_db):
    """Test that health status includes database stats."""
    from datetime import date

    # Add some data
    await database.add_user(111, "it")
    await database.add_user(222, "en")

    future_date = date.today() + timedelta(days=10)
    await database.add_product(111, "Active Product", "ACTIVE01", "it", 50.0, future_date)

    health = await health_handler.get_health_status()

    assert "stats" in health
    assert health["stats"]["users"] == 2
    assert health["stats"]["products_total"] == 1
    assert health["stats"]["products_active"] == 1


@pytest.mark.asyncio
async def test_health_status_exactly_at_threshold(test_db):
    """Test health status when task ran just within the 2-day threshold."""
    now = datetime.now()
    # Use 1 day 23 hours to ensure we're within threshold even with timing differences
    within_threshold = (now - timedelta(days=1, hours=23)).isoformat()

    await database.update_system_status("last_scraper_run", within_threshold)
    await database.update_system_status("last_checker_run", within_threshold)
    await database.update_system_status("last_cleanup_run", within_threshold)

    health = await health_handler.get_health_status()

    # Within 2 days should be healthy
    assert health["status"] == "healthy"
    assert health["tasks"]["scraper"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_status_just_over_threshold(test_db):
    """Test health status when task ran just over 2 days ago."""
    now = datetime.now()
    just_over_two_days = (now - timedelta(days=2, hours=1)).isoformat()

    await database.update_system_status("last_scraper_run", just_over_two_days)
    await database.update_system_status("last_checker_run", just_over_two_days)
    await database.update_system_status("last_cleanup_run", just_over_two_days)

    health = await health_handler.get_health_status()

    # Just over 2 days should be unhealthy
    assert health["status"] == "unhealthy"
    assert health["tasks"]["scraper"]["status"] == "stale"


@pytest.mark.asyncio
async def test_health_status_includes_timestamp(test_db):
    """Test that health status includes current timestamp."""
    health = await health_handler.get_health_status()

    assert "timestamp" in health
    # Verify it's a valid ISO timestamp
    timestamp = datetime.fromisoformat(health["timestamp"])
    assert isinstance(timestamp, datetime)


@pytest.mark.asyncio
async def test_health_status_includes_thresholds(test_db):
    """Test that health status includes threshold information."""
    health = await health_handler.get_health_status()

    assert "thresholds" in health
    assert health["thresholds"]["max_days_since_last_run"] == 2


# ============================================================================
# HTTP Handler tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_handler_get_health(test_db):
    """Test HealthCheckHandler responds to /health endpoint."""
    from io import BytesIO
    import asyncio

    # Add some test data
    now = datetime.now()
    one_day_ago = (now - timedelta(days=1)).isoformat()
    await database.update_system_status("last_scraper_run", one_day_ago)
    await database.update_system_status("last_checker_run", one_day_ago)
    await database.update_system_status("last_cleanup_run", one_day_ago)

    # Get expected health data
    expected_health_data = await health_handler.get_health_status()

    # Create handler without calling __init__ (which would try to handle request)
    handler = health_handler.HealthCheckHandler.__new__(health_handler.HealthCheckHandler)

    # Mock the necessary attributes
    handler.path = "/health"
    response_buffer = BytesIO()
    handler.wfile = response_buffer
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()

    # Mock asyncio.new_event_loop and loop.run_until_complete to avoid nested loop issue
    mock_loop = MagicMock()
    mock_loop.run_until_complete.return_value = expected_health_data
    mock_loop.close = MagicMock()

    with patch("asyncio.new_event_loop", return_value=mock_loop):
        with patch("asyncio.set_event_loop"):
            # Call do_GET
            handler.do_GET()

    # Verify response was sent
    handler.send_response.assert_called_once_with(200)
    handler.send_header.assert_called_with("Content-type", "application/json")
    handler.end_headers.assert_called_once()

    # Verify response contains valid JSON
    response_data = response_buffer.getvalue()
    response_json = json.loads(response_data.decode())

    assert "status" in response_json
    assert response_json["status"] == "healthy"
    assert "tasks" in response_json


@pytest.mark.asyncio
async def test_health_check_handler_404(test_db):
    """Test HealthCheckHandler returns 404 for unknown paths."""
    # Create handler without calling __init__
    handler = health_handler.HealthCheckHandler.__new__(health_handler.HealthCheckHandler)

    # Mock the necessary attributes
    handler.path = "/unknown"
    handler.send_error = MagicMock()

    # Call do_GET
    handler.do_GET()

    # Verify 404 was sent
    handler.send_error.assert_called_once_with(404, "Not Found")


@pytest.mark.asyncio
async def test_health_check_handler_error_handling(test_db):
    """Test HealthCheckHandler error handling when database fails."""
    from io import BytesIO

    # Create handler without calling __init__
    handler = health_handler.HealthCheckHandler.__new__(health_handler.HealthCheckHandler)

    # Mock the necessary attributes
    handler.path = "/health"
    handler.wfile = BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()

    # Mock get_health_status to raise an error
    with patch("health_handler.get_health_status", side_effect=Exception("DB Error")):
        # Call do_GET
        handler.do_GET()

        # Verify error response was sent
        handler.send_error.assert_called_once()
        call_args = handler.send_error.call_args[0]
        assert call_args[0] == 500
        assert "Internal Server Error" in call_args[1]


def test_health_check_handler_log_message():
    """Test HealthCheckHandler custom log_message method."""
    # Create handler without calling __init__
    handler = health_handler.HealthCheckHandler.__new__(health_handler.HealthCheckHandler)

    # Mock address_string
    handler.address_string = MagicMock(return_value="127.0.0.1")

    # Capture log messages
    with patch.object(health_handler.logger, "info") as mock_log:
        # Call log_message
        handler.log_message("GET %s %s", "/health", "200")

        # Verify logger.info was called
        mock_log.assert_called_once()
        log_message = mock_log.call_args[0][0]
        assert "127.0.0.1" in log_message
        assert "/health" in log_message
        assert "200" in log_message


@pytest.mark.asyncio
async def test_check_task_health_invalid_timestamp(test_db):
    """Test _check_task_health with invalid timestamp format."""
    # Add invalid timestamp
    await database.update_system_status("last_scraper_run", "invalid-timestamp")

    # Get system status
    system_status = await database.get_all_system_status()
    threshold = datetime.now()

    # Call _check_task_health
    task_status, is_healthy = health_handler._check_task_health("scraper", system_status, threshold)

    # Verify error status
    assert task_status["status"] == "error"
    assert is_healthy is False
    assert task_status["last_run"] == "invalid-timestamp"


# ============================================================================
# Server configuration and startup tests
# ============================================================================


def test_health_bind_address_default():
    """Test that HEALTH_BIND_ADDRESS defaults to 0.0.0.0."""
    # Reload module to get fresh environment variable
    import importlib

    # Save current value
    original_value = os.environ.get("HEALTH_BIND_ADDRESS")

    try:
        # Remove env var if it exists
        if "HEALTH_BIND_ADDRESS" in os.environ:
            del os.environ["HEALTH_BIND_ADDRESS"]

        # Reload module to get default value
        importlib.reload(health_handler)

        assert health_handler.HEALTH_BIND_ADDRESS == "0.0.0.0"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["HEALTH_BIND_ADDRESS"] = original_value
        importlib.reload(health_handler)


def test_health_bind_address_from_env():
    """Test that HEALTH_BIND_ADDRESS can be set from environment."""
    import importlib

    # Save current value
    original_value = os.environ.get("HEALTH_BIND_ADDRESS")

    try:
        # Set custom value
        os.environ["HEALTH_BIND_ADDRESS"] = "127.0.0.1"

        # Reload module to pick up new value
        importlib.reload(health_handler)

        assert health_handler.HEALTH_BIND_ADDRESS == "127.0.0.1"
    finally:
        # Restore original value
        if original_value is not None:
            os.environ["HEALTH_BIND_ADDRESS"] = original_value
        else:
            if "HEALTH_BIND_ADDRESS" in os.environ:
                del os.environ["HEALTH_BIND_ADDRESS"]
        importlib.reload(health_handler)


def test_run_server_uses_bind_address():
    """Test that run_server uses the configured bind address."""
    with patch("health_handler.HTTPServer") as mock_http_server:
        # Mock HTTPServer to prevent actual server startup
        mock_server_instance = MagicMock()
        mock_http_server.return_value = mock_server_instance

        # Mock serve_forever to return immediately instead of blocking
        mock_server_instance.serve_forever = MagicMock(return_value=None)

        # Call run_server (it should return immediately thanks to the mock)
        # We need to call it in a way that doesn't block, so we'll patch first
        try:
            # This would normally block, but our mock prevents it
            import threading

            def run_with_timeout():
                health_handler.run_server()

            thread = threading.Thread(target=run_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=1)  # Wait max 1 second

            # Verify HTTPServer was called with correct bind address
            mock_http_server.assert_called_once()
            call_args = mock_http_server.call_args[0]
            bind_address, port = call_args[0]

            assert bind_address == health_handler.HEALTH_BIND_ADDRESS
            assert port == health_handler.HEALTH_PORT
        finally:
            # Make sure we don't leave any hanging threads
            pass


def test_run_server_with_custom_bind_address():
    """Test that run_server respects HEALTH_BIND_ADDRESS environment variable."""
    import importlib

    # Save original value
    original_value = os.environ.get("HEALTH_BIND_ADDRESS")
    original_bind_address = health_handler.HEALTH_BIND_ADDRESS

    try:
        # Set custom bind address
        os.environ["HEALTH_BIND_ADDRESS"] = "127.0.0.1"

        # Reload module to pick up new value
        importlib.reload(health_handler)

        with patch("health_handler.HTTPServer") as mock_http_server:
            # Mock HTTPServer
            mock_server_instance = MagicMock()
            mock_http_server.return_value = mock_server_instance
            mock_server_instance.serve_forever = MagicMock(return_value=None)

            # Call run_server in a thread with timeout
            import threading

            def run_with_timeout():
                health_handler.run_server()

            thread = threading.Thread(target=run_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=1)

            # Verify HTTPServer was called with 127.0.0.1
            mock_http_server.assert_called_once()
            call_args = mock_http_server.call_args[0]
            bind_address, port = call_args[0]

            assert bind_address == "127.0.0.1"
            assert port == health_handler.HEALTH_PORT

    finally:
        # Restore original value
        if original_value is not None:
            os.environ["HEALTH_BIND_ADDRESS"] = original_value
        else:
            if "HEALTH_BIND_ADDRESS" in os.environ:
                del os.environ["HEALTH_BIND_ADDRESS"]

        # Restore module state
        health_handler.HEALTH_BIND_ADDRESS = original_bind_address
        importlib.reload(health_handler)


@patch("health_handler.Thread")
@patch("health_handler.run_server")
def test_start_health_server(mock_run_server, mock_thread):
    """Test that start_health_server starts server in daemon thread."""
    # Mock Thread instance
    mock_thread_instance = MagicMock()
    mock_thread.return_value = mock_thread_instance

    # Call start_health_server
    health_handler.start_health_server()

    # Verify Thread was created with correct parameters
    mock_thread.assert_called_once_with(target=health_handler.run_server, daemon=True)

    # Verify thread.start() was called
    mock_thread_instance.start.assert_called_once()


def test_run_server_logs_configuration(caplog):
    """Test that run_server logs the bind address and port configuration."""
    import logging
    import threading

    with patch("health_handler.HTTPServer") as mock_http_server:
        # Mock HTTPServer to prevent actual server startup
        mock_server_instance = MagicMock()
        mock_http_server.return_value = mock_server_instance
        mock_server_instance.serve_forever = MagicMock(return_value=None)

        # Set log level to capture INFO logs
        with caplog.at_level(logging.INFO):

            # Call run_server in a thread with timeout
            def run_with_timeout():
                health_handler.run_server()

            thread = threading.Thread(target=run_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=1)

        # Verify log message includes bind address and port
        assert any(
            str(health_handler.HEALTH_BIND_ADDRESS) in record.message
            and str(health_handler.HEALTH_PORT) in record.message
            and "reverse proxy" in record.message.lower()
            for record in caplog.records
        )
