"""Tests for shared logging configuration utilities."""

import logging
import os
import tempfile
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytest

from utils.logging_config import setup_rotating_file_handler


def test_setup_rotating_file_handler_creates_data_directory():
    """Test that setup_rotating_file_handler creates data directory if needed."""
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            # Change to temp directory
            os.chdir(tmpdir)

            # Ensure data directory doesn't exist
            data_dir = Path("data")
            assert not data_dir.exists()

            # Call function
            handler = setup_rotating_file_handler("data/test.log")

            # Verify data directory was created
            assert data_dir.exists()
            assert data_dir.is_dir()

            # Clean up handler
            handler.close()
        finally:
            os.chdir(original_cwd)


def test_setup_rotating_file_handler_returns_correct_type():
    """Test that setup_rotating_file_handler returns TimedRotatingFileHandler."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            handler = setup_rotating_file_handler("data/test.log")

            assert isinstance(handler, TimedRotatingFileHandler)

            handler.close()
        finally:
            os.chdir(original_cwd)


def test_setup_rotating_file_handler_default_format():
    """Test that setup_rotating_file_handler uses default format string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            handler = setup_rotating_file_handler("data/test.log")

            # Check formatter format string
            assert handler.formatter is not None
            assert "%(asctime)s" in handler.formatter._fmt
            assert "%(name)s" in handler.formatter._fmt
            assert "%(levelname)s" in handler.formatter._fmt
            assert "%(message)s" in handler.formatter._fmt

            handler.close()
        finally:
            os.chdir(original_cwd)


def test_setup_rotating_file_handler_custom_format():
    """Test that setup_rotating_file_handler accepts custom format string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            custom_format = "%(asctime)s - %(levelname)s - %(message)s"
            handler = setup_rotating_file_handler("data/test.log", format_string=custom_format)

            # Check formatter uses custom format
            assert handler.formatter is not None
            assert handler.formatter._fmt == custom_format

            handler.close()
        finally:
            os.chdir(original_cwd)


def test_setup_rotating_file_handler_rotation_config():
    """Test that setup_rotating_file_handler configures rotation correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            handler = setup_rotating_file_handler("data/test.log")

            # Verify rotation configuration
            # Note: TimedRotatingFileHandler normalizes 'midnight' to 'MIDNIGHT'
            assert handler.when == "MIDNIGHT"
            # interval is stored in seconds (1 day = 86400 seconds)
            assert handler.interval == 86400
            assert handler.backupCount == 2  # Keep today + 2 previous days

            handler.close()
        finally:
            os.chdir(original_cwd)


def test_setup_rotating_file_handler_creates_log_file():
    """Test that setup_rotating_file_handler creates the log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            log_file = "data/test.log"
            handler = setup_rotating_file_handler(log_file)

            # Write a test log
            logger = logging.getLogger("test_logger")
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.info("Test message")

            # Verify log file exists
            assert Path(log_file).exists()

            handler.close()
            logger.removeHandler(handler)
        finally:
            os.chdir(original_cwd)


def test_setup_rotating_file_handler_with_existing_data_dir():
    """Test that setup_rotating_file_handler works when data directory already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Pre-create data directory
            data_dir = Path("data")
            data_dir.mkdir()
            assert data_dir.exists()

            # Call function (should not raise error)
            handler = setup_rotating_file_handler("data/test.log")

            # Verify still works
            assert isinstance(handler, TimedRotatingFileHandler)

            handler.close()
        finally:
            os.chdir(original_cwd)
