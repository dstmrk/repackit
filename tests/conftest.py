"""Shared test fixtures for RepackIt tests."""

import os
import tempfile
from pathlib import Path

import pytest

import database


@pytest.fixture
async def test_db():
    """
    Create a temporary test database with proper connection management.

    This fixture:
    1. Creates a temporary database file
    2. Resets the database connection manager singleton
    3. Updates DATABASE_PATH to point to the temp file
    4. Initializes the database schema
    5. After test: closes connection, resets singleton, cleans up files
    """
    # Create temporary database file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Store original path
    original_path = database.DATABASE_PATH

    # Close any existing connection before resetting (important for test isolation)
    await database.close_db()

    # Reset connection manager and update path BEFORE init
    database.DatabaseConnection.reset()
    database.DATABASE_PATH = db_path

    # Initialize database with new path
    await database.init_db()

    yield db_path

    # Cleanup: close connection and reset singleton
    await database.close_db()
    database.DatabaseConnection.reset()

    # Restore original path
    database.DATABASE_PATH = original_path

    # Remove temp files
    Path(db_path).unlink(missing_ok=True)
    Path(f"{db_path}-wal").unlink(missing_ok=True)
    Path(f"{db_path}-shm").unlink(missing_ok=True)
