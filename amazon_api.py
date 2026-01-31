"""Amazon Creator API client for fetching product prices."""

import logging
import time

import httpx

from config import get_config

logger = logging.getLogger(__name__)

# API base URL (same for all regions)
API_BASE_URL = "https://creatorsapi.amazon"
GET_ITEMS_ENDPOINT = f"{API_BASE_URL}/catalog/v1/getItems"

# Maximum items per API request
MAX_ITEMS_PER_REQUEST = 10

# Regional OAuth token endpoints
TOKEN_ENDPOINTS = {
    "2.1": "https://creatorsapi.auth.us-east-1.amazoncognito.com/oauth2/token",  # NA
    "2.2": "https://creatorsapi.auth.eu-south-2.amazoncognito.com/oauth2/token",  # EU
    "2.3": "https://creatorsapi.auth.us-west-2.amazoncognito.com/oauth2/token",  # FE
}

# Marketplace code to domain mapping
MARKETPLACE_DOMAINS = {
    "it": "www.amazon.it",
    "com": "www.amazon.com",
    "de": "www.amazon.de",
    "fr": "www.amazon.fr",
    "es": "www.amazon.es",
    "uk": "www.amazon.co.uk",
    "nl": "www.amazon.nl",
    "be": "www.amazon.com.be",
    "se": "www.amazon.se",
    "pl": "www.amazon.pl",
    "jp": "www.amazon.co.jp",
    "au": "www.amazon.com.au",
    "ca": "www.amazon.ca",
    "br": "www.amazon.com.br",
}

# Resources to request from the API
ITEM_RESOURCES = [
    "offersV2.listings.price",
    "offersV2.listings.availability",
    "offersV2.listings.condition",
    "offersV2.listings.isBuyBoxWinner",
    "itemInfo.title",
]

# Token refresh buffer (seconds before expiry to refresh)
TOKEN_REFRESH_BUFFER = 60


class AmazonCreatorAPIError(Exception):
    """Raised when the Amazon Creator API returns an error."""


class AmazonCreatorAPI:
    """
    Client for Amazon Creator API.

    Handles OAuth token management with caching and product price lookups.
    """

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    def _get_token_endpoint(self) -> str:
        """Get the OAuth token endpoint for the configured credential version."""
        cfg = get_config()
        version = cfg.amazon_credential_version
        endpoint = TOKEN_ENDPOINTS.get(version)
        if not endpoint:
            raise AmazonCreatorAPIError(
                f"Unknown credential version: {version}. "
                f"Valid versions: {', '.join(TOKEN_ENDPOINTS.keys())}"
            )
        return endpoint

    async def _fetch_access_token(self) -> tuple[str, int]:
        """
        Fetch a new OAuth access token from Amazon Cognito.

        Returns:
            Tuple of (access_token, expires_in_seconds)

        Raises:
            AmazonCreatorAPIError: If token fetch fails
        """
        cfg = get_config()
        token_endpoint = self._get_token_endpoint()

        if not cfg.amazon_client_id or not cfg.amazon_client_secret:
            raise AmazonCreatorAPIError("AMAZON_CLIENT_ID and AMAZON_CLIENT_SECRET must be set")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_endpoint,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": cfg.amazon_client_id,
                    "client_secret": cfg.amazon_client_secret,
                    "scope": "creatorsapi/default",
                },
                timeout=10.0,
            )

        if response.status_code != 200:
            raise AmazonCreatorAPIError(
                f"Token fetch failed (HTTP {response.status_code}): {response.text}"
            )

        data = response.json()
        access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)

        if not access_token:
            raise AmazonCreatorAPIError(f"No access_token in response: {data}")

        logger.info(f"Obtained new Amazon API access token (expires in {expires_in}s)")
        return access_token, expires_in

    async def _get_access_token(self) -> str:
        """
        Get a valid access token, fetching a new one if expired.

        Returns:
            Valid access token string
        """
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        token, expires_in = await self._fetch_access_token()
        self._access_token = token
        self._token_expires_at = time.monotonic() + expires_in - TOKEN_REFRESH_BUFFER
        return token

    async def get_items(self, asins: list[str], marketplace: str = "it") -> dict[str, float | None]:
        """
        Fetch prices for a list of ASINs via the Creator API.

        Automatically batches requests if more than MAX_ITEMS_PER_REQUEST ASINs.

        Args:
            asins: List of ASINs to look up
            marketplace: Marketplace code (e.g., "it", "com", "de")

        Returns:
            Dict mapping ASIN -> price (float) or None if price unavailable
        """
        if not asins:
            return {}

        marketplace_domain = MARKETPLACE_DOMAINS.get(marketplace)
        if not marketplace_domain:
            logger.warning(f"Unknown marketplace '{marketplace}', falling back to www.amazon.it")
            marketplace_domain = "www.amazon.it"

        results: dict[str, float | None] = {}

        # Batch ASINs into groups of MAX_ITEMS_PER_REQUEST
        for i in range(0, len(asins), MAX_ITEMS_PER_REQUEST):
            batch = asins[i : i + MAX_ITEMS_PER_REQUEST]
            batch_results = await self._get_items_batch(batch, marketplace_domain)
            results.update(batch_results)

        return results

    async def _get_items_batch(
        self, asins: list[str], marketplace_domain: str
    ) -> dict[str, float | None]:
        """
        Fetch prices for a batch of ASINs (max 10).

        Args:
            asins: List of ASINs (max 10)
            marketplace_domain: Full marketplace domain (e.g., "www.amazon.it")

        Returns:
            Dict mapping ASIN -> price or None
        """
        cfg = get_config()
        token = await self._get_access_token()

        headers = {
            "Authorization": f"Bearer {token}, Version {cfg.amazon_credential_version}",
            "Content-Type": "application/json",
            "x-marketplace": marketplace_domain,
        }

        payload = {
            "itemIds": asins,
            "itemIdType": "ASIN",
            "marketplace": marketplace_domain,
            "partnerTag": cfg.amazon_affiliate_tag,
            "resources": ITEM_RESOURCES,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    GET_ITEMS_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=15.0,
                )
        except httpx.HTTPError as e:
            logger.error(f"API request failed: {e}")
            return dict.fromkeys(asins)

        if response.status_code != 200:
            logger.error(f"API returned HTTP {response.status_code}: {response.text}")
            return dict.fromkeys(asins)

        return self._parse_items_response(response.json(), asins)

    def _parse_items_response(
        self, data: dict, requested_asins: list[str]
    ) -> dict[str, float | None]:
        """
        Parse GetItems API response and extract prices.

        Args:
            data: Raw API response JSON
            requested_asins: List of ASINs that were requested

        Returns:
            Dict mapping ASIN -> price or None
        """
        results: dict[str, float | None] = dict.fromkeys(requested_asins)

        items_result = data.get("itemsResult", {})
        items = items_result.get("items", [])

        for item in items:
            asin = item.get("asin")
            if not asin:
                continue

            price = self._extract_price_from_item(item)
            if price is not None:
                results[asin] = price
                logger.debug(f"ASIN {asin}: price €{price:.2f}")
            else:
                logger.warning(f"ASIN {asin}: no price available in API response")

        return results

    def _extract_price_from_item(self, item: dict) -> float | None:
        """
        Extract the best price from an item's offersV2 data.

        Prefers the BuyBox winner listing. Falls back to first listing with a price.

        Args:
            item: Single item dict from API response

        Returns:
            Price as float or None if not available
        """
        offers_v2 = item.get("offersV2")
        if not offers_v2:
            return None

        listings = offers_v2.get("listings", [])
        if not listings:
            return None

        # Try to find the BuyBox winner first
        for listing in listings:
            if listing.get("isBuyBoxWinner"):
                price = self._extract_listing_price(listing)
                if price is not None:
                    return price

        # Fallback: first listing with a price
        for listing in listings:
            price = self._extract_listing_price(listing)
            if price is not None:
                return price

        return None

    def _extract_listing_price(self, listing: dict) -> float | None:
        """
        Extract price from a single listing.

        Args:
            listing: Single listing dict from offersV2

        Returns:
            Price as float or None
        """
        price_data = listing.get("price")
        if not price_data:
            return None

        money = price_data.get("money")
        if not money:
            return None

        amount = money.get("amount")
        if amount is not None:
            try:
                price = float(amount)
                if 0.01 <= price <= 999999:
                    return price
                logger.warning(f"Price {price} out of reasonable range")
            except (ValueError, TypeError):
                logger.warning(f"Could not parse price amount: {amount}")

        return None


# Global singleton instance
_api_client: AmazonCreatorAPI | None = None


def get_api_client() -> AmazonCreatorAPI:
    """
    Get the global API client instance.

    Returns:
        AmazonCreatorAPI singleton instance
    """
    global _api_client
    if _api_client is None:
        _api_client = AmazonCreatorAPI()
    return _api_client


def reset_api_client() -> None:
    """Reset the global API client instance (useful for testing)."""
    global _api_client
    _api_client = None
