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

    # Product Limits & Referral System
    default_max_products: int
    initial_max_products: int
    products_per_referral: int
    invited_user_bonus: int

    # Health Check
    health_port: int
    health_bind_address: str

    # Logging
    log_level: str

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
            # Product Limits & Referral
            default_max_products=int(os.getenv("DEFAULT_MAX_PRODUCTS", "21")),
            initial_max_products=int(os.getenv("INITIAL_MAX_PRODUCTS", "3")),
            products_per_referral=int(os.getenv("PRODUCTS_PER_REFERRAL", "3")),
            invited_user_bonus=int(os.getenv("INVITED_USER_BONUS", "3")),
            # Health Check
            health_port=int(os.getenv("HEALTH_PORT", "8444")),
            health_bind_address=os.getenv("HEALTH_BIND_ADDRESS", "0.0.0.0"),
            # Logging
            log_level=os.getenv("LOG_LEVEL", "INFO"),
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
