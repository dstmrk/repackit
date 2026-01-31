"""Tests for Amazon Creator API client."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from amazon_api import (
    API_BASE_URL,
    GET_ITEMS_ENDPOINT,
    ITEM_RESOURCES,
    MARKETPLACE_DOMAINS,
    MAX_ITEMS_PER_REQUEST,
    TOKEN_ENDPOINTS,
    TOKEN_REFRESH_BUFFER,
    AmazonCreatorAPI,
    AmazonCreatorAPIError,
    get_api_client,
    reset_api_client,
)

# ============================================================================
# Token endpoint tests
# ============================================================================


class TestTokenEndpoint:
    """Test OAuth token endpoint resolution."""

    def test_eu_endpoint(self):
        """Test EU credential version maps to correct endpoint."""
        api = AmazonCreatorAPI()
        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "2.2"
            endpoint = api._get_token_endpoint()
            assert "eu-south-2" in endpoint

    def test_na_endpoint(self):
        """Test NA credential version maps to correct endpoint."""
        api = AmazonCreatorAPI()
        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "2.1"
            endpoint = api._get_token_endpoint()
            assert "us-east-1" in endpoint

    def test_fe_endpoint(self):
        """Test FE credential version maps to correct endpoint."""
        api = AmazonCreatorAPI()
        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "2.3"
            endpoint = api._get_token_endpoint()
            assert "us-west-2" in endpoint

    def test_invalid_version(self):
        """Test invalid credential version raises error."""
        api = AmazonCreatorAPI()
        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "9.9"
            with pytest.raises(AmazonCreatorAPIError, match="Unknown credential version"):
                api._get_token_endpoint()


# ============================================================================
# Token fetch tests
# ============================================================================


class TestFetchAccessToken:
    """Test OAuth token fetching."""

    @pytest.mark.asyncio
    async def test_fetch_token_success(self):
        """Test successful token fetch."""
        api = AmazonCreatorAPI()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test-token-123",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "2.2"
            mock_config.return_value.amazon_client_id = "test-client-id"
            mock_config.return_value.amazon_client_secret = "test-client-secret"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                token, expires_in = await api._fetch_access_token()

                assert token == "test-token-123"
                assert expires_in == 3600

    @pytest.mark.asyncio
    async def test_fetch_token_missing_credentials(self):
        """Test token fetch with missing credentials."""
        api = AmazonCreatorAPI()

        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "2.2"
            mock_config.return_value.amazon_client_id = ""
            mock_config.return_value.amazon_client_secret = ""

            with pytest.raises(AmazonCreatorAPIError, match="must be set"):
                await api._fetch_access_token()

    @pytest.mark.asyncio
    async def test_fetch_token_http_error(self):
        """Test token fetch with HTTP error."""
        api = AmazonCreatorAPI()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "2.2"
            mock_config.return_value.amazon_client_id = "test-id"
            mock_config.return_value.amazon_client_secret = "test-secret"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                with pytest.raises(AmazonCreatorAPIError, match="Token fetch failed"):
                    await api._fetch_access_token()

    @pytest.mark.asyncio
    async def test_fetch_token_no_access_token_in_response(self):
        """Test token fetch when response lacks access_token."""
        api = AmazonCreatorAPI()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "something_wrong"}

        with patch("amazon_api.get_config") as mock_config:
            mock_config.return_value.amazon_credential_version = "2.2"
            mock_config.return_value.amazon_client_id = "test-id"
            mock_config.return_value.amazon_client_secret = "test-secret"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                with pytest.raises(AmazonCreatorAPIError, match="No access_token"):
                    await api._fetch_access_token()


# ============================================================================
# Token caching tests
# ============================================================================


class TestGetAccessToken:
    """Test token caching behavior."""

    @pytest.mark.asyncio
    async def test_token_cached(self):
        """Test that token is cached and reused."""
        api = AmazonCreatorAPI()
        api._access_token = "cached-token"
        api._token_expires_at = time.monotonic() + 3600  # Still valid

        token = await api._get_access_token()
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_token_refreshed_when_expired(self):
        """Test that expired token triggers refresh."""
        api = AmazonCreatorAPI()
        api._access_token = "old-token"
        api._token_expires_at = time.monotonic() - 100  # Expired

        with patch.object(api, "_fetch_access_token", return_value=("new-token", 3600)):
            token = await api._get_access_token()

        assert token == "new-token"
        assert api._access_token == "new-token"

    @pytest.mark.asyncio
    async def test_token_refreshed_when_none(self):
        """Test that None token triggers fetch."""
        api = AmazonCreatorAPI()

        with patch.object(api, "_fetch_access_token", return_value=("fresh-token", 3600)):
            token = await api._get_access_token()

        assert token == "fresh-token"


# ============================================================================
# Price extraction tests
# ============================================================================


class TestExtractPrice:
    """Test price extraction from API responses."""

    def test_extract_buybox_winner_price(self):
        """Test extracting price from BuyBox winner listing."""
        api = AmazonCreatorAPI()
        item = {
            "offersV2": {
                "listings": [
                    {
                        "isBuyBoxWinner": False,
                        "price": {"money": {"amount": 99.99, "currency": "EUR"}},
                    },
                    {
                        "isBuyBoxWinner": True,
                        "price": {"money": {"amount": 59.49, "currency": "EUR"}},
                    },
                ]
            }
        }

        price = api._extract_price_from_item(item)
        assert price == 59.49

    def test_extract_first_listing_fallback(self):
        """Test fallback to first listing when no BuyBox winner."""
        api = AmazonCreatorAPI()
        item = {
            "offersV2": {
                "listings": [
                    {
                        "isBuyBoxWinner": False,
                        "price": {"money": {"amount": 45.00, "currency": "EUR"}},
                    },
                ]
            }
        }

        price = api._extract_price_from_item(item)
        assert price == 45.00

    def test_extract_price_no_offers(self):
        """Test with no offers data."""
        api = AmazonCreatorAPI()
        assert api._extract_price_from_item({}) is None
        assert api._extract_price_from_item({"offersV2": None}) is None
        assert api._extract_price_from_item({"offersV2": {"listings": []}}) is None

    def test_extract_price_no_price_in_listing(self):
        """Test with listing that has no price."""
        api = AmazonCreatorAPI()
        item = {
            "offersV2": {
                "listings": [
                    {"isBuyBoxWinner": True, "price": None},
                ]
            }
        }
        assert api._extract_price_from_item(item) is None

    def test_extract_price_no_money_in_price(self):
        """Test with price that has no money field."""
        api = AmazonCreatorAPI()
        item = {
            "offersV2": {
                "listings": [
                    {"isBuyBoxWinner": True, "price": {"money": None}},
                ]
            }
        }
        assert api._extract_price_from_item(item) is None

    def test_extract_price_out_of_range(self):
        """Test with price outside reasonable range."""
        api = AmazonCreatorAPI()
        item = {
            "offersV2": {
                "listings": [
                    {
                        "isBuyBoxWinner": True,
                        "price": {"money": {"amount": 9999999, "currency": "EUR"}},
                    },
                ]
            }
        }
        assert api._extract_price_from_item(item) is None

    def test_extract_listing_price_invalid_amount(self):
        """Test with non-numeric price amount."""
        api = AmazonCreatorAPI()
        listing = {"price": {"money": {"amount": "invalid"}}}
        assert api._extract_listing_price(listing) is None


# ============================================================================
# Parse items response tests
# ============================================================================


class TestParseItemsResponse:
    """Test API response parsing."""

    def test_parse_successful_response(self):
        """Test parsing a successful multi-item response."""
        api = AmazonCreatorAPI()
        data = {
            "itemsResult": {
                "items": [
                    {
                        "asin": "B08N5WRWNW",
                        "offersV2": {
                            "listings": [
                                {
                                    "isBuyBoxWinner": True,
                                    "price": {"money": {"amount": 59.49, "currency": "EUR"}},
                                }
                            ]
                        },
                    },
                    {
                        "asin": "B09B2SBHQK",
                        "offersV2": {
                            "listings": [
                                {
                                    "isBuyBoxWinner": True,
                                    "price": {"money": {"amount": 45.00, "currency": "EUR"}},
                                }
                            ]
                        },
                    },
                ]
            }
        }

        results = api._parse_items_response(data, ["B08N5WRWNW", "B09B2SBHQK"])
        assert results["B08N5WRWNW"] == 59.49
        assert results["B09B2SBHQK"] == 45.00

    def test_parse_partial_response(self):
        """Test parsing when some items have no price."""
        api = AmazonCreatorAPI()
        data = {
            "itemsResult": {
                "items": [
                    {
                        "asin": "B08N5WRWNW",
                        "offersV2": {
                            "listings": [
                                {
                                    "isBuyBoxWinner": True,
                                    "price": {"money": {"amount": 59.49, "currency": "EUR"}},
                                }
                            ]
                        },
                    },
                    {
                        "asin": "B09B2SBHQK",
                        "offersV2": None,
                    },
                ]
            }
        }

        results = api._parse_items_response(data, ["B08N5WRWNW", "B09B2SBHQK"])
        assert results["B08N5WRWNW"] == 59.49
        assert results["B09B2SBHQK"] is None

    def test_parse_empty_response(self):
        """Test parsing empty response."""
        api = AmazonCreatorAPI()
        results = api._parse_items_response({}, ["B08N5WRWNW"])
        assert results["B08N5WRWNW"] is None

    def test_parse_missing_asin_in_item(self):
        """Test parsing item with no ASIN field."""
        api = AmazonCreatorAPI()
        data = {
            "itemsResult": {
                "items": [
                    {
                        "offersV2": {
                            "listings": [
                                {
                                    "isBuyBoxWinner": True,
                                    "price": {"money": {"amount": 59.49, "currency": "EUR"}},
                                }
                            ]
                        },
                    }
                ]
            }
        }

        results = api._parse_items_response(data, ["B08N5WRWNW"])
        assert results["B08N5WRWNW"] is None


# ============================================================================
# GetItems batch tests
# ============================================================================


class TestGetItemsBatch:
    """Test batch API calls."""

    @pytest.mark.asyncio
    async def test_get_items_batch_success(self):
        """Test successful batch API call."""
        api = AmazonCreatorAPI()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "itemsResult": {
                "items": [
                    {
                        "asin": "B08N5WRWNW",
                        "offersV2": {
                            "listings": [
                                {
                                    "isBuyBoxWinner": True,
                                    "price": {"money": {"amount": 59.49, "currency": "EUR"}},
                                }
                            ]
                        },
                    }
                ]
            }
        }

        with patch.object(api, "_get_access_token", return_value="test-token"):
            with patch("amazon_api.get_config") as mock_config:
                mock_config.return_value.amazon_credential_version = "2.2"
                mock_config.return_value.amazon_affiliate_tag = "test-21"

                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = mock_response
                    mock_client_cls.return_value.__aenter__.return_value = mock_client

                    results = await api._get_items_batch(["B08N5WRWNW"], "www.amazon.it")

                    assert results["B08N5WRWNW"] == 59.49

                    # Verify request payload
                    call_kwargs = mock_client.post.call_args
                    assert call_kwargs[0][0] == GET_ITEMS_ENDPOINT
                    payload = call_kwargs[1]["json"]
                    assert payload["itemIds"] == ["B08N5WRWNW"]
                    assert payload["marketplace"] == "www.amazon.it"
                    assert payload["partnerTag"] == "test-21"
                    assert "offersV2.listings.price" in payload["resources"]

    @pytest.mark.asyncio
    async def test_get_items_batch_http_error(self):
        """Test batch API call with HTTP error."""
        api = AmazonCreatorAPI()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(api, "_get_access_token", return_value="test-token"):
            with patch("amazon_api.get_config") as mock_config:
                mock_config.return_value.amazon_credential_version = "2.2"
                mock_config.return_value.amazon_affiliate_tag = "test-21"

                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.return_value = mock_response
                    mock_client_cls.return_value.__aenter__.return_value = mock_client

                    results = await api._get_items_batch(["B08N5WRWNW"], "www.amazon.it")

                    assert results["B08N5WRWNW"] is None

    @pytest.mark.asyncio
    async def test_get_items_batch_network_error(self):
        """Test batch API call with network error."""
        api = AmazonCreatorAPI()

        with patch.object(api, "_get_access_token", return_value="test-token"):
            with patch("amazon_api.get_config") as mock_config:
                mock_config.return_value.amazon_credential_version = "2.2"
                mock_config.return_value.amazon_affiliate_tag = "test-21"

                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client = AsyncMock()
                    mock_client.post.side_effect = httpx.ConnectError("Connection failed")
                    mock_client_cls.return_value.__aenter__.return_value = mock_client

                    results = await api._get_items_batch(["B08N5WRWNW"], "www.amazon.it")

                    assert results["B08N5WRWNW"] is None


# ============================================================================
# GetItems (with batching) tests
# ============================================================================


class TestGetItems:
    """Test get_items with automatic batching."""

    @pytest.mark.asyncio
    async def test_get_items_empty_list(self):
        """Test with empty ASIN list."""
        api = AmazonCreatorAPI()
        results = await api.get_items([])
        assert results == {}

    @pytest.mark.asyncio
    async def test_get_items_unknown_marketplace(self):
        """Test with unknown marketplace falls back to www.amazon.it."""
        api = AmazonCreatorAPI()

        with patch.object(api, "_get_items_batch", return_value={"ASIN0001XX": 50.0}) as mock_batch:
            results = await api.get_items(["ASIN0001XX"], "unknown")

            mock_batch.assert_called_once_with(["ASIN0001XX"], "www.amazon.it")
            assert results["ASIN0001XX"] == 50.0

    @pytest.mark.asyncio
    async def test_get_items_batching(self):
        """Test that large ASIN lists are batched correctly."""
        api = AmazonCreatorAPI()

        # Create 25 ASINs (should be split into 3 batches: 10, 10, 5)
        asins = [f"B{i:09d}" for i in range(25)]

        batch_calls = []

        async def mock_batch(batch_asins, marketplace_domain):
            batch_calls.append(len(batch_asins))
            return dict.fromkeys(batch_asins, 10.0)

        with patch.object(api, "_get_items_batch", side_effect=mock_batch):
            results = await api.get_items(asins, "it")

        assert len(results) == 25
        assert batch_calls == [10, 10, 5]

    @pytest.mark.asyncio
    async def test_get_items_marketplace_mapping(self):
        """Test marketplace code to domain mapping."""
        api = AmazonCreatorAPI()

        with patch.object(api, "_get_items_batch", return_value={"ASIN0001XX": 50.0}) as mock_batch:
            await api.get_items(["ASIN0001XX"], "it")
            mock_batch.assert_called_with(["ASIN0001XX"], "www.amazon.it")

        with patch.object(api, "_get_items_batch", return_value={"ASIN0001XX": 50.0}) as mock_batch:
            await api.get_items(["ASIN0001XX"], "de")
            mock_batch.assert_called_with(["ASIN0001XX"], "www.amazon.de")

        with patch.object(api, "_get_items_batch", return_value={"ASIN0001XX": 50.0}) as mock_batch:
            await api.get_items(["ASIN0001XX"], "uk")
            mock_batch.assert_called_with(["ASIN0001XX"], "www.amazon.co.uk")


# ============================================================================
# Singleton tests
# ============================================================================


class TestSingleton:
    """Test global singleton management."""

    def test_get_api_client_returns_singleton(self):
        """Test that get_api_client returns same instance."""
        reset_api_client()
        client1 = get_api_client()
        client2 = get_api_client()
        assert client1 is client2

    def test_reset_api_client(self):
        """Test that reset creates new instance."""
        reset_api_client()
        client1 = get_api_client()
        reset_api_client()
        client2 = get_api_client()
        assert client1 is not client2


# ============================================================================
# Constants tests
# ============================================================================


class TestConstants:
    """Test module constants."""

    def test_api_base_url(self):
        """Test API base URL."""
        assert API_BASE_URL == "https://creatorsapi.amazon"

    def test_get_items_endpoint(self):
        """Test GetItems endpoint."""
        assert GET_ITEMS_ENDPOINT == "https://creatorsapi.amazon/catalog/v1/getItems"

    def test_max_items_per_request(self):
        """Test max items per request."""
        assert MAX_ITEMS_PER_REQUEST == 10

    def test_token_refresh_buffer(self):
        """Test token refresh buffer is reasonable."""
        assert 30 <= TOKEN_REFRESH_BUFFER <= 300

    def test_item_resources_include_price(self):
        """Test that item resources include price."""
        assert "offersV2.listings.price" in ITEM_RESOURCES

    def test_marketplace_domains_italy(self):
        """Test Italy marketplace domain."""
        assert MARKETPLACE_DOMAINS["it"] == "www.amazon.it"

    def test_token_endpoints_all_regions(self):
        """Test all regional token endpoints are defined."""
        assert "2.1" in TOKEN_ENDPOINTS  # NA
        assert "2.2" in TOKEN_ENDPOINTS  # EU
        assert "2.3" in TOKEN_ENDPOINTS  # FE
