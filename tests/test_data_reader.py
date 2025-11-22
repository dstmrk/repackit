"""Tests for Amazon data reader."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import data_reader

# ============================================================================
# ASIN extraction tests
# ============================================================================


def test_extract_asin_dp_format():
    """Test ASIN extraction from /dp/ URL format."""
    url = "https://www.amazon.it/dp/B08N5WRWNW"
    asin, marketplace = data_reader.extract_asin(url)
    assert asin == "B08N5WRWNW"
    assert marketplace == "it"


def test_extract_asin_gp_product_format():
    """Test ASIN extraction from /gp/product/ URL format."""
    url = "https://amazon.it/gp/product/B08N5WRWNW/ref=something"
    asin, marketplace = data_reader.extract_asin(url)
    assert asin == "B08N5WRWNW"
    assert marketplace == "it"


def test_extract_asin_with_product_name():
    """Test ASIN extraction from URL with product name."""
    url = "https://www.amazon.it/Some-Product-Name/dp/B08N5WRWNW/ref=sr_1_1"
    asin, marketplace = data_reader.extract_asin(url)
    assert asin == "B08N5WRWNW"
    assert marketplace == "it"


def test_extract_asin_different_marketplaces():
    """Test ASIN extraction from different marketplaces."""
    test_cases = [
        ("https://amazon.com/dp/B08N5WRWNW", "B08N5WRWNW", "com"),
        ("https://amazon.de/dp/B08N5WRWNW", "B08N5WRWNW", "de"),
        ("https://amazon.fr/dp/B08N5WRWNW", "B08N5WRWNW", "fr"),
        ("https://amazon.es/dp/B08N5WRWNW", "B08N5WRWNW", "es"),
        ("https://amazon.co.uk/dp/B08N5WRWNW", "B08N5WRWNW", "uk"),
    ]

    for url, expected_asin, expected_marketplace in test_cases:
        asin, marketplace = data_reader.extract_asin(url)
        assert asin == expected_asin
        assert marketplace == expected_marketplace


def test_extract_asin_invalid_url():
    """Test ASIN extraction from invalid URL."""
    with pytest.raises(ValueError, match="Could not extract ASIN"):
        data_reader.extract_asin("https://amazon.it/invalid-url")


def test_extract_asin_no_marketplace():
    """Test ASIN extraction when marketplace cannot be determined."""
    # URL without amazon domain (should default to .it with warning)
    url = "https://example.org/dp/B08N5WRWNW"
    asin, marketplace = data_reader.extract_asin(url)
    assert asin == "B08N5WRWNW"
    assert marketplace == "it"  # Defaults to .it


# ============================================================================
# Affiliate URL builder tests
# ============================================================================


def test_build_affiliate_url_with_tag():
    """Test affiliate URL building with tag."""
    with patch.dict(os.environ, {"AMAZON_AFFILIATE_TAG": "mytag-21"}):
        # Reload module to pick up new env var
        import importlib

        importlib.reload(data_reader)

        url = data_reader.build_affiliate_url("B08N5WRWNW", "it")
        assert url == "https://amazon.it/dp/B08N5WRWNW?tag=mytag-21"


def test_build_affiliate_url_without_tag():
    """Test affiliate URL building without tag."""
    with patch.dict(os.environ, {"AMAZON_AFFILIATE_TAG": ""}):
        import importlib

        importlib.reload(data_reader)

        url = data_reader.build_affiliate_url("B08N5WRWNW", "it")
        assert url == "https://amazon.it/dp/B08N5WRWNW"


def test_build_affiliate_url_different_marketplaces():
    """Test affiliate URL building for different marketplaces."""
    with patch.dict(os.environ, {"AMAZON_AFFILIATE_TAG": "mytag-21"}):
        import importlib

        importlib.reload(data_reader)

        test_cases = [
            ("it", "https://amazon.it/dp/B08N5WRWNW?tag=mytag-21"),
            ("com", "https://amazon.com/dp/B08N5WRWNW?tag=mytag-21"),
            ("de", "https://amazon.de/dp/B08N5WRWNW?tag=mytag-21"),
        ]

        for marketplace, expected_url in test_cases:
            url = data_reader.build_affiliate_url("B08N5WRWNW", marketplace)
            assert url == expected_url


# ============================================================================
# Price parsing tests
# ============================================================================


def test_parse_price_euro_comma():
    """Test price parsing with Euro symbol and comma."""
    assert data_reader._parse_price("€59,90") == 59.90


def test_parse_price_euro_dot():
    """Test price parsing with Euro symbol and dot."""
    assert data_reader._parse_price("€59.90") == 59.90


def test_parse_price_with_trailing_euro():
    """Test price parsing with trailing Euro symbol."""
    assert data_reader._parse_price("59,90 €") == 59.90


def test_parse_price_dollar():
    """Test price parsing with dollar symbol."""
    assert data_reader._parse_price("$59.90") == 59.90


def test_parse_price_plain_number():
    """Test price parsing with plain number."""
    assert data_reader._parse_price("59.90") == 59.90


def test_parse_price_with_whitespace():
    """Test price parsing with whitespace."""
    assert data_reader._parse_price("  €59,90  ") == 59.90


def test_parse_price_range():
    """Test price parsing with range (should extract first price)."""
    assert data_reader._parse_price("59.90 - 69.90") == 59.90


def test_parse_price_invalid():
    """Test price parsing with invalid input."""
    assert data_reader._parse_price("No price here") is None
    assert data_reader._parse_price("") is None


def test_parse_price_integer():
    """Test price parsing with integer."""
    assert data_reader._parse_price("€50") == 50.0


# ============================================================================
# Price scraping tests (mocked)
# ============================================================================


@pytest.mark.asyncio
async def test_scrape_single_price_success():
    """Test successful price scraping."""
    # Mock Playwright components
    mock_page = AsyncMock()
    mock_element = AsyncMock()
    mock_element.inner_text = AsyncMock(return_value="€59,90")
    mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
    mock_page.goto = AsyncMock()
    mock_page.set_extra_http_headers = AsyncMock()
    mock_page.close = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)

    # Call function
    price = await data_reader._scrape_single_price(mock_browser, "B08N5WRWNW", "it")

    # Verify
    assert price == 59.90
    mock_page.goto.assert_called_once()
    assert "amazon.it/dp/B08N5WRWNW" in mock_page.goto.call_args[0][0]


@pytest.mark.asyncio
async def test_scrape_single_price_not_found():
    """Test price scraping when price element not found."""
    # Mock Playwright components - all selectors fail
    mock_page = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(
        side_effect=data_reader.TimeoutError("Selector not found")
    )
    mock_page.goto = AsyncMock()
    mock_page.set_extra_http_headers = AsyncMock()
    mock_page.close = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)

    # Call function
    price = await data_reader._scrape_single_price(mock_browser, "B08N5WRWNW", "it")

    # Should return None when price not found
    assert price is None


@pytest.mark.asyncio
async def test_scrape_single_price_network_error():
    """Test price scraping with network error."""
    # Mock Playwright components - goto fails
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=Exception("Network error"))
    mock_page.set_extra_http_headers = AsyncMock()

    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)

    # Call function
    price = await data_reader._scrape_single_price(mock_browser, "B08N5WRWNW", "it")

    # Should return None on error
    assert price is None


@pytest.mark.asyncio
async def test_scrape_prices_multiple_products():
    """Test scraping multiple products."""
    products = [
        {"id": 1, "asin": "ASIN00001"},
        {"id": 2, "asin": "ASIN00002"},
        {"id": 3, "asin": "ASIN00003"},
    ]

    # Mock _scrape_single_price to return predictable results
    async def mock_scrape(browser, asin, marketplace):
        # Simulate: first succeeds, second fails, third succeeds
        if asin == "ASIN00001":
            return 50.00
        elif asin == "ASIN00002":
            return None  # Failed to scrape
        elif asin == "ASIN00003":
            return 70.00

    with patch("data_reader._scrape_single_price", side_effect=mock_scrape):
        with patch("data_reader.async_playwright") as mock_playwright:
            # Mock playwright context manager
            mock_browser = AsyncMock()
            mock_playwright.return_value.__aenter__.return_value.chromium.launch = AsyncMock(
                return_value=mock_browser
            )
            mock_browser.close = AsyncMock()

            # Call function
            results = await data_reader.scrape_prices(products, rate_limit_seconds=0)

            # Verify
            assert len(results) == 2  # Only successful scrapes
            assert results[1] == 50.00  # product id 1
            assert results[3] == 70.00  # product id 3
            assert 2 not in results  # product id 2 failed


@pytest.mark.asyncio
async def test_scrape_prices_with_custom_marketplace():
    """Test scraping with custom marketplace."""
    products = [{"id": 1, "asin": "ASIN00001", "marketplace": "de"}]

    async def mock_scrape(browser, asin, marketplace):
        # Verify marketplace is passed correctly
        assert marketplace == "de"
        return 50.00

    with patch("data_reader._scrape_single_price", side_effect=mock_scrape):
        with patch("data_reader.async_playwright") as mock_playwright:
            mock_browser = AsyncMock()
            mock_playwright.return_value.__aenter__.return_value.chromium.launch = AsyncMock(
                return_value=mock_browser
            )
            mock_browser.close = AsyncMock()

            results = await data_reader.scrape_prices(products)
            assert results[1] == 50.00


@pytest.mark.asyncio
async def test_scrape_prices_deduplication():
    """Test that duplicate ASINs are scraped only once."""
    # 5 products: 3 share ASIN00001, 2 share ASIN00002
    products = [
        {"id": 1, "asin": "ASIN00001", "marketplace": "it"},
        {"id": 2, "asin": "ASIN00001", "marketplace": "it"},  # Duplicate ASIN
        {"id": 3, "asin": "ASIN00001", "marketplace": "it"},  # Duplicate ASIN
        {"id": 4, "asin": "ASIN00002", "marketplace": "it"},
        {"id": 5, "asin": "ASIN00002", "marketplace": "it"},  # Duplicate ASIN
    ]

    # Track how many times each ASIN is scraped
    scrape_counts = {"ASIN00001": 0, "ASIN00002": 0}

    async def mock_scrape(browser, asin, marketplace):
        # Count scrapes for each ASIN
        scrape_counts[asin] += 1

        # Return different prices for different ASINs
        if asin == "ASIN00001":
            return 100.00
        elif asin == "ASIN00002":
            return 200.00

    with patch("data_reader._scrape_single_price", side_effect=mock_scrape):
        with patch("data_reader.async_playwright") as mock_playwright:
            mock_browser = AsyncMock()
            mock_playwright.return_value.__aenter__.return_value.chromium.launch = AsyncMock(
                return_value=mock_browser
            )
            mock_browser.close = AsyncMock()

            # Call function
            results = await data_reader.scrape_prices(products, rate_limit_seconds=0)

            # Verify each ASIN was scraped only once
            assert scrape_counts["ASIN00001"] == 1, "ASIN00001 should be scraped only once"
            assert scrape_counts["ASIN00002"] == 1, "ASIN00002 should be scraped only once"

            # Verify all products got the correct price
            assert len(results) == 5  # All products should have results
            assert results[1] == 100.00  # Product 1 (ASIN00001)
            assert results[2] == 100.00  # Product 2 (ASIN00001)
            assert results[3] == 100.00  # Product 3 (ASIN00001)
            assert results[4] == 200.00  # Product 4 (ASIN00002)
            assert results[5] == 200.00  # Product 5 (ASIN00002)


@pytest.mark.asyncio
async def test_scrape_prices_deduplication_different_marketplaces():
    """Test that same ASIN on different marketplaces are scraped separately."""
    # Same ASIN on different marketplaces should be scraped separately
    products = [
        {"id": 1, "asin": "ASIN00001", "marketplace": "it"},
        {"id": 2, "asin": "ASIN00001", "marketplace": "de"},  # Different marketplace
        {"id": 3, "asin": "ASIN00001", "marketplace": "it"},  # Duplicate (it)
    ]

    scrape_counts = {}

    async def mock_scrape(browser, asin, marketplace):
        key = f"{asin}-{marketplace}"
        scrape_counts[key] = scrape_counts.get(key, 0) + 1

        # Return different prices for different marketplaces
        if marketplace == "it":
            return 100.00
        elif marketplace == "de":
            return 120.00

    with patch("data_reader._scrape_single_price", side_effect=mock_scrape):
        with patch("data_reader.async_playwright") as mock_playwright:
            mock_browser = AsyncMock()
            mock_playwright.return_value.__aenter__.return_value.chromium.launch = AsyncMock(
                return_value=mock_browser
            )
            mock_browser.close = AsyncMock()

            results = await data_reader.scrape_prices(products, rate_limit_seconds=0)

            # Verify each (ASIN, marketplace) combination was scraped once
            assert scrape_counts["ASIN00001-it"] == 1
            assert scrape_counts["ASIN00001-de"] == 1

            # Verify correct prices
            assert results[1] == 100.00  # it marketplace
            assert results[2] == 120.00  # de marketplace
            assert results[3] == 100.00  # it marketplace (duplicate)
