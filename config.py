"""Centralized configuration management for RepackIt bot."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """
    Application configuration loaded from environment variables.

    All configuration is centralized here for:
    - Type safety
    - Validation
    - Easy testing
    - Single source of truth
    """

    # Telegram Bot
    telegram_token: str
    webhook_url: str | None
    webhook_secret: str | None
    bot_port: int
    telegram_channel: str

    # Database
    database_path: str

    # Scheduler (hours in 24h format)
    scraper_hour: int
    checker_hour: int
    cleanup_hour: int

    # Admin
    admin_user_id: str | None

    # Amazon Affiliate
    amazon_affiliate_tag: str

    # Amazon Creator API
    amazon_client_id: str
    amazon_client_secret: str
    amazon_credential_version: str

    # Product Limits & Referral System
    default_max_products: int
    initial_max_products: int
    products_per_referral: int
    invited_user_bonus: int

    # Health Check
    health_port: int
    health_bind_address: str
    health_check_max_days: int  # Max days since last task run before considered stale

    # Feedback
    feedback_min_length: int  # Minimum feedback message length
    feedback_max_length: int  # Maximum feedback message length
    feedback_rate_limit_hours: int  # Hours between feedback submissions

    # Scraper
    scraper_rate_limit_seconds: float  # Delay between Amazon requests

    # Logging
    log_level: str

    # Telegram Rate Limiting
    telegram_messages_per_second: int  # Telegram API hard limit (30 msg/sec)
    batch_size: int  # Batch size for notifications and broadcasts
    delay_between_batches: float  # Delay in seconds between batches
    max_concurrent_telegram_calls: int  # Max concurrent Telegram API calls per batch

    # Retry Settings
    telegram_max_retries: int  # Max retry attempts for transient errors
    telegram_retry_base_delay: float  # Base delay in seconds (doubles each retry)

    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables.

        Returns:
            Config instance with all settings loaded from environment

        Note:
            TELEGRAM_TOKEN defaults to empty string for testing purposes.
            Production code should validate it's set before using the bot.
        """
        return cls(
            # Telegram Bot
            telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
            webhook_url=os.getenv("WEBHOOK_URL"),
            webhook_secret=os.getenv("WEBHOOK_SECRET"),
            bot_port=int(os.getenv("BOT_PORT", "8443")),
            telegram_channel=os.getenv("TELEGRAM_CHANNEL", "").strip(),
            # Database
            database_path=os.getenv("DATABASE_PATH", "./data/repackit.db"),
            # Scheduler
            scraper_hour=int(os.getenv("SCRAPER_HOUR", "9")),
            checker_hour=int(os.getenv("CHECKER_HOUR", "10")),
            cleanup_hour=int(os.getenv("CLEANUP_HOUR", "2")),
            # Admin
            admin_user_id=os.getenv("ADMIN_USER_ID"),
            # Amazon Affiliate
            amazon_affiliate_tag=os.getenv("AMAZON_AFFILIATE_TAG", ""),
            # Amazon Creator API
            amazon_client_id=os.getenv("AMAZON_CLIENT_ID", ""),
            amazon_client_secret=os.getenv("AMAZON_CLIENT_SECRET", ""),
            amazon_credential_version=os.getenv("AMAZON_CREDENTIAL_VERSION", "2.2"),
            # Product Limits & Referral
            default_max_products=int(os.getenv("DEFAULT_MAX_PRODUCTS", "21")),
            initial_max_products=int(os.getenv("INITIAL_MAX_PRODUCTS", "3")),
            products_per_referral=int(os.getenv("PRODUCTS_PER_REFERRAL", "3")),
            invited_user_bonus=int(os.getenv("INVITED_USER_BONUS", "3")),
            # Health Check
            health_port=int(os.getenv("HEALTH_PORT", "8444")),
            health_bind_address=os.getenv("HEALTH_BIND_ADDRESS", "0.0.0.0"),
            health_check_max_days=int(os.getenv("HEALTH_CHECK_MAX_DAYS", "2")),
            # Feedback
            feedback_min_length=int(os.getenv("FEEDBACK_MIN_LENGTH", "10")),
            feedback_max_length=int(os.getenv("FEEDBACK_MAX_LENGTH", "1000")),
            feedback_rate_limit_hours=int(os.getenv("FEEDBACK_RATE_LIMIT_HOURS", "24")),
            # Scraper
            scraper_rate_limit_seconds=float(os.getenv("SCRAPER_RATE_LIMIT_SECONDS", "1.5")),
            # Logging
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            # Telegram Rate Limiting
            telegram_messages_per_second=int(os.getenv("TELEGRAM_MESSAGES_PER_SECOND", "30")),
            batch_size=int(os.getenv("BATCH_SIZE", "10")),
            delay_between_batches=float(os.getenv("DELAY_BETWEEN_BATCHES", "1.0")),
            max_concurrent_telegram_calls=int(os.getenv("MAX_CONCURRENT_TELEGRAM_CALLS", "5")),
            # Retry Settings
            telegram_max_retries=int(os.getenv("TELEGRAM_MAX_RETRIES", "3")),
            telegram_retry_base_delay=float(os.getenv("TELEGRAM_RETRY_BASE_DELAY", "1.0")),
        )


# Global singleton instance
_config: Config | None = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Returns:
        Config singleton instance

    Note:
        Configuration is loaded once on first call and cached.
        For testing, use reset_config() to reload from environment.
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """
    Reset the global configuration instance.

    Useful for testing to reload configuration from environment.
    """
    global _config
    _config = None
