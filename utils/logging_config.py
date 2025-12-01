"""Shared logging configuration utilities."""

import logging
import os
from logging.handlers import TimedRotatingFileHandler


def setup_rotating_file_handler(
    log_file: str,
    format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
) -> TimedRotatingFileHandler:
    """
    Create a TimedRotatingFileHandler with standardized configuration.

    Args:
        log_file: Path to log file (relative to project root)
        format_string: Log format string (default includes name, level, message)

    Returns:
        Configured TimedRotatingFileHandler

    Configuration:
        - Rotates at midnight
        - Keeps 2 backups + today = 3 days total
        - Creates data/ directory if it doesn't exist
    """
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    # Create handler with daily rotation
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=2,  # Keep today + 2 previous days
    )

    # Set formatter
    handler.setFormatter(logging.Formatter(format_string))

    return handler
