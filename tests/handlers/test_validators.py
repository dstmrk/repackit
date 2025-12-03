"""Tests for validators module."""

from datetime import date, timedelta

import pytest

from handlers import validators

# =================================================================================================
# validate_product_name tests
# =================================================================================================


def test_validate_product_name_valid():
    """Test valid product names."""
    # Minimum length (3 chars)
    is_valid, name, error = validators.validate_product_name("ABC")
    assert is_valid is True
    assert name == "ABC"
    assert error is None

    # Medium length
    is_valid, name, error = validators.validate_product_name("iPhone 15 Pro")
    assert is_valid is True
    assert name == "iPhone 15 Pro"
    assert error is None

    # Maximum length (100 chars)
    long_name = "A" * 100
    is_valid, name, error = validators.validate_product_name(long_name)
    assert is_valid is True
    assert name == long_name
    assert error is None

    # With whitespace (should be stripped)
    is_valid, name, error = validators.validate_product_name("  Product  ")
    assert is_valid is True
    assert name == "Product"
    assert error is None


def test_validate_product_name_too_short():
    """Test product name too short (< 3 chars)."""
    # Empty string
    is_valid, name, error = validators.validate_product_name("")
    assert is_valid is False
    assert name is None
    assert "troppo corto" in error.lower()

    # 1 char
    is_valid, name, error = validators.validate_product_name("A")
    assert is_valid is False
    assert name is None
    assert "troppo corto" in error.lower()

    # 2 chars
    is_valid, name, error = validators.validate_product_name("AB")
    assert is_valid is False
    assert name is None
    assert "troppo corto" in error.lower()

    # Whitespace only (stripped to empty)
    is_valid, name, error = validators.validate_product_name("   ")
    assert is_valid is False
    assert name is None
    assert "troppo corto" in error.lower()


def test_validate_product_name_too_long():
    """Test product name too long (> 100 chars)."""
    long_name = "A" * 101
    is_valid, name, error = validators.validate_product_name(long_name)
    assert is_valid is False
    assert name is None
    assert "troppo lungo" in error.lower()


# =================================================================================================
# validate_price tests
# =================================================================================================


def test_validate_price_valid():
    """Test valid price inputs."""
    # Standard price with dot
    is_valid, price, error = validators.validate_price("59.90")
    assert is_valid is True
    assert price == 59.90
    assert error is None

    # Price with comma (Italian format)
    is_valid, price, error = validators.validate_price("59,90")
    assert is_valid is True
    assert price == 59.90
    assert error is None

    # Integer price
    is_valid, price, error = validators.validate_price("50")
    assert is_valid is True
    assert price == 50.0
    assert error is None

    # Small price
    is_valid, price, error = validators.validate_price("0.01")
    assert is_valid is True
    assert price == 0.01
    assert error is None

    # Large price (15 digits)
    is_valid, price, error = validators.validate_price("999999999.99999")
    assert is_valid is True
    assert price == 999999999.99999
    assert error is None

    # With whitespace
    is_valid, price, error = validators.validate_price("  59.90  ")
    assert is_valid is True
    assert price == 59.90
    assert error is None


def test_validate_price_invalid_format():
    """Test invalid price formats."""
    # Not a number
    is_valid, price, error = validators.validate_price("abc")
    assert is_valid is False
    assert price is None
    assert "non valido" in error.lower()

    # Multiple dots
    is_valid, price, error = validators.validate_price("59.90.50")
    assert is_valid is False
    assert price is None
    assert "non valido" in error.lower()

    # Empty string
    is_valid, price, error = validators.validate_price("")
    assert is_valid is False
    assert price is None
    assert "non valido" in error.lower()


def test_validate_price_non_positive():
    """Test non-positive prices."""
    # Zero
    is_valid, price, error = validators.validate_price("0")
    assert is_valid is False
    assert price is None
    assert "positivo" in error.lower()

    # Negative
    is_valid, price, error = validators.validate_price("-10.50")
    assert is_valid is False
    assert price is None
    assert "positivo" in error.lower()


def test_validate_price_too_many_digits():
    """Test prices with too many digits."""
    # 17 digits (exceeds default max_digits=16)
    is_valid, price, error = validators.validate_price("99999999999999999")
    assert is_valid is False
    assert price is None
    assert "troppo lungo" in error.lower()

    # Custom max_digits
    is_valid, price, error = validators.validate_price("123456", max_digits=5)
    assert is_valid is False
    assert price is None
    assert "troppo lungo" in error.lower()


# =================================================================================================
# validate_threshold tests
# =================================================================================================


def test_validate_threshold_valid():
    """Test valid threshold inputs."""
    # Zero threshold (notify for any savings)
    is_valid, threshold, error = validators.validate_threshold("0", max_value=50.0)
    assert is_valid is True
    assert threshold == 0.0
    assert error is None

    # Standard threshold
    is_valid, threshold, error = validators.validate_threshold("5", max_value=50.0)
    assert is_valid is True
    assert threshold == 5.0
    assert error is None

    # Decimal threshold with comma
    is_valid, threshold, error = validators.validate_threshold("5,50", max_value=50.0)
    assert is_valid is True
    assert threshold == 5.50
    assert error is None

    # Threshold just below max
    is_valid, threshold, error = validators.validate_threshold("49.99", max_value=50.0)
    assert is_valid is True
    assert threshold == 49.99
    assert error is None


def test_validate_threshold_invalid_format():
    """Test invalid threshold formats."""
    # Not a number
    is_valid, threshold, error = validators.validate_threshold("abc", max_value=50.0)
    assert is_valid is False
    assert threshold is None
    assert "non valido" in error.lower()

    # Empty string
    is_valid, threshold, error = validators.validate_threshold("", max_value=50.0)
    assert is_valid is False
    assert threshold is None
    assert "non valido" in error.lower()


def test_validate_threshold_negative():
    """Test negative threshold."""
    is_valid, threshold, error = validators.validate_threshold("-5", max_value=50.0)
    assert is_valid is False
    assert threshold is None
    assert "non negativo" in error.lower()


def test_validate_threshold_too_high():
    """Test threshold >= max_value."""
    # Equal to max_value
    is_valid, threshold, error = validators.validate_threshold("50", max_value=50.0)
    assert is_valid is False
    assert threshold is None
    assert "troppo alto" in error.lower()

    # Greater than max_value
    is_valid, threshold, error = validators.validate_threshold("55", max_value=50.0)
    assert is_valid is False
    assert threshold is None
    assert "troppo alto" in error.lower()


# =================================================================================================
# parse_deadline tests
# =================================================================================================


def test_parse_deadline_from_days():
    """Test parsing deadline from number of days."""
    # 1 day
    deadline = validators.parse_deadline("1")
    assert deadline == date.today() + timedelta(days=1)

    # 30 days
    deadline = validators.parse_deadline("30")
    assert deadline == date.today() + timedelta(days=30)

    # 365 days (max)
    deadline = validators.parse_deadline("365")
    assert deadline == date.today() + timedelta(days=365)


def test_parse_deadline_from_date_gg_mm_aaaa():
    """Test parsing deadline from date format gg-mm-aaaa."""
    # Future date with dash
    deadline = validators.parse_deadline("15-12-2025")
    assert deadline == date(2025, 12, 15)

    # Future date with slash
    deadline = validators.parse_deadline("15/12/2025")
    assert deadline == date(2025, 12, 15)


def test_parse_deadline_from_date_aaaa_mm_gg():
    """Test parsing deadline from ISO date format aaaa-mm-gg."""
    deadline = validators.parse_deadline("2025-12-15")
    assert deadline == date(2025, 12, 15)


def test_parse_deadline_invalid_days():
    """Test invalid number of days."""
    # Zero days
    with pytest.raises(ValueError, match="tra 1 e 365"):
        validators.parse_deadline("0")

    # Negative days
    with pytest.raises(ValueError, match="tra 1 e 365"):
        validators.parse_deadline("-10")

    # Too many days
    with pytest.raises(ValueError, match="tra 1 e 365"):
        validators.parse_deadline("366")


def test_parse_deadline_invalid_date_format():
    """Test invalid date formats."""
    # Wrong number of parts
    with pytest.raises(ValueError, match="Formato non valido"):
        validators.parse_deadline("15-12")

    with pytest.raises(ValueError, match="Formato non valido"):
        validators.parse_deadline("15-12-2025-extra")

    # Invalid date (month 13)
    with pytest.raises(ValueError, match="Data non valida"):
        validators.parse_deadline("15-13-2025")

    # Invalid date (day 32)
    with pytest.raises(ValueError, match="Data non valida"):
        validators.parse_deadline("32-12-2025")

    # Two-digit year
    with pytest.raises(ValueError, match="Anno deve essere"):
        validators.parse_deadline("15-12-25")


def test_parse_deadline_past_date():
    """Test date in the past."""
    # Yesterday
    yesterday = date.today() - timedelta(days=1)
    date_str = yesterday.strftime("%d-%m-%Y")

    with pytest.raises(ValueError, match="nel passato"):
        validators.parse_deadline(date_str)

    # Far in the past
    with pytest.raises(ValueError, match="nel passato"):
        validators.parse_deadline("01-01-2020")


def test_parse_deadline_today():
    """Test today's date (should fail - bot needs at least 1 day to monitor)."""
    today_str = date.today().strftime("%d-%m-%Y")

    with pytest.raises(ValueError, match="La scadenza è oggi"):
        validators.parse_deadline(today_str)


def test_parse_deadline_with_whitespace():
    """Test deadline parsing with extra whitespace."""
    deadline = validators.parse_deadline("  30  ")
    assert deadline == date.today() + timedelta(days=30)

    deadline = validators.parse_deadline("  15-12-2025  ")
    assert deadline == date(2025, 12, 15)
