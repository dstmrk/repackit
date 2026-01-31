"""Tests for Amazon data reader."""

import os
from unittest.mock import AsyncMock, patch

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

        from config import reset_config

        reset_config()  # Reset config to reload from new env
        importlib.reload(data_reader)

        url = data_reader.build_affiliate_url("B08N5WRWNW", "it")
        assert url == "https://amazon.it/dp/B08N5WRWNW?tag=mytag-21"


def test_build_affiliate_url_without_tag():
    """Test affiliate URL building without tag."""
    with patch.dict(os.environ, {"AMAZON_AFFILIATE_TAG": ""}):
        import importlib

        from config import reset_config

        reset_config()  # Reset config to reload from new env
        importlib.reload(data_reader)

        url = data_reader.build_affiliate_url("B08N5WRWNW", "it")
        assert url == "https://amazon.it/dp/B08N5WRWNW"


def test_build_affiliate_url_different_marketplaces():
    """Test affiliate URL building for different marketplaces."""
    with patch.dict(os.environ, {"AMAZON_AFFILIATE_TAG": "mytag-21"}):
        import importlib

        from config import reset_config

        reset_config()  # Reset config to reload from new env
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
# Price fetching tests (mocked API)
# ============================================================================


@pytest.mark.asyncio
async def test_scrape_prices_multiple_products():
    """Test fetching prices for multiple products via API."""
    products = [
        {"id": 1, "asin": "ASIN00001"},
        {"id": 2, "asin": "ASIN00002"},
        {"id": 3, "asin": "ASIN00003"},
    ]

    mock_api = AsyncMock()
    mock_api.get_items.return_value = {
        "ASIN00001": 50.00,
        "ASIN00002": None,  # Failed to fetch
        "ASIN00003": 70.00,
    }

    with patch("data_reader.get_api_client", return_value=mock_api):
        results = await data_reader.scrape_prices(products)

        assert len(results) == 2  # Only successful fetches
        assert results[1] == 50.00  # product id 1
        assert results[3] == 70.00  # product id 3
        assert 2 not in results  # product id 2 failed


@pytest.mark.asyncio
async def test_scrape_prices_with_custom_marketplace():
    """Test fetching with custom marketplace."""
    products = [{"id": 1, "asin": "ASIN00001", "marketplace": "de"}]

    mock_api = AsyncMock()
    mock_api.get_items.return_value = {"ASIN00001": 50.00}

    with patch("data_reader.get_api_client", return_value=mock_api):
        results = await data_reader.scrape_prices(products)

        assert results[1] == 50.00
        # Verify marketplace was passed correctly
        mock_api.get_items.assert_called_once_with(["ASIN00001"], "de")


@pytest.mark.asyncio
async def test_scrape_prices_deduplication():
    """Test that duplicate ASINs are fetched only once."""
    # 5 products: 3 share ASIN00001, 2 share ASIN00002
    products = [
        {"id": 1, "asin": "ASIN00001", "marketplace": "it"},
        {"id": 2, "asin": "ASIN00001", "marketplace": "it"},  # Duplicate ASIN
        {"id": 3, "asin": "ASIN00001", "marketplace": "it"},  # Duplicate ASIN
        {"id": 4, "asin": "ASIN00002", "marketplace": "it"},
        {"id": 5, "asin": "ASIN00002", "marketplace": "it"},  # Duplicate ASIN
    ]

    mock_api = AsyncMock()
    mock_api.get_items.return_value = {
        "ASIN00001": 100.00,
        "ASIN00002": 200.00,
    }

    with patch("data_reader.get_api_client", return_value=mock_api):
        results = await data_reader.scrape_prices(products)

        # API should be called once with both unique ASINs
        mock_api.get_items.assert_called_once()
        call_args = mock_api.get_items.call_args
        assert sorted(call_args[0][0]) == ["ASIN00001", "ASIN00002"]

        # Verify all products got the correct price
        assert len(results) == 5
        assert results[1] == 100.00
        assert results[2] == 100.00
        assert results[3] == 100.00
        assert results[4] == 200.00
        assert results[5] == 200.00


@pytest.mark.asyncio
async def test_scrape_prices_deduplication_different_marketplaces():
    """Test that same ASIN on different marketplaces are fetched separately."""
    products = [
        {"id": 1, "asin": "ASIN00001", "marketplace": "it"},
        {"id": 2, "asin": "ASIN00001", "marketplace": "de"},  # Different marketplace
        {"id": 3, "asin": "ASIN00001", "marketplace": "it"},  # Duplicate (it)
    ]

    mock_api = AsyncMock()

    # Return different prices for different marketplaces
    async def mock_get_items(asins, marketplace):
        if marketplace == "it":
            return {"ASIN00001": 100.00}
        elif marketplace == "de":
            return {"ASIN00001": 120.00}
        return {}

    mock_api.get_items.side_effect = mock_get_items

    with patch("data_reader.get_api_client", return_value=mock_api):
        results = await data_reader.scrape_prices(products)

        # Should be called twice (once per marketplace)
        assert mock_api.get_items.call_count == 2

        # Verify correct prices
        assert results[1] == 100.00  # it marketplace
        assert results[2] == 120.00  # de marketplace
        assert results[3] == 100.00  # it marketplace (duplicate)


@pytest.mark.asyncio
async def test_scrape_prices_api_error():
    """Test handling API errors gracefully."""
    products = [
        {"id": 1, "asin": "ASIN00001", "marketplace": "it"},
    ]

    mock_api = AsyncMock()
    mock_api.get_items.side_effect = Exception("API connection error")

    with patch("data_reader.get_api_client", return_value=mock_api):
        results = await data_reader.scrape_prices(products)

        # Should return empty results on error
        assert len(results) == 0


# ============================================================================
# scrape_price() wrapper tests
# ============================================================================


async def test_scrape_price_success():
    """Test scrape_price() wrapper calls scrape_prices() correctly."""
    with patch("data_reader.scrape_prices") as mock_scrape_prices:
        # Mock scrape_prices to return a price for product id 0
        mock_scrape_prices.return_value = {0: 99.99}

        price = await data_reader.scrape_price("B08N5WRWNW", "it")

        # Verify scrape_prices was called with correct fake product
        mock_scrape_prices.assert_called_once()
        call_args = mock_scrape_prices.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["id"] == 0
        assert call_args[0]["asin"] == "B08N5WRWNW"
        assert call_args[0]["marketplace"] == "it"

        # Verify correct price returned
        assert price == 99.99


async def test_scrape_price_failure():
    """Test scrape_price() returns None when fetching fails."""
    with patch("data_reader.scrape_prices") as mock_scrape_prices:
        # Mock scrape_prices to return empty dict (fetching failed)
        mock_scrape_prices.return_value = {}

        price = await data_reader.scrape_price("B08N5WRWNW", "it")

        # Verify None returned
        assert price is None


async def test_scrape_price_custom_marketplace():
    """Test scrape_price() with custom marketplace."""
    with patch("data_reader.scrape_prices") as mock_scrape_prices:
        mock_scrape_prices.return_value = {0: 199.99}

        price = await data_reader.scrape_price("B08XYZ1234", "de")

        # Verify marketplace passed correctly
        call_args = mock_scrape_prices.call_args[0][0]
        assert call_args[0]["marketplace"] == "de"
        assert price == 199.99
