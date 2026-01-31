"""Amazon data reader for price fetching via Creator API."""

import asyncio
import logging
import re

from amazon_api import get_api_client
from config import get_config

# Configure logging
logger = logging.getLogger(__name__)

# Get affiliate tag from environment

# ASIN pattern: 10 alphanumeric characters
# Supports: /dp/, /gp/product/, and short links /d/
ASIN_PATTERN = re.compile(r"/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})|/d/([A-Z0-9]{10})")
cfg = get_config()

# Module-level constants for backward compatibility with tests
TELEGRAM_TOKEN = cfg.telegram_token
AMAZON_AFFILIATE_TAG = cfg.amazon_affiliate_tag

# Marketplace pattern: extract domain suffix (it, com, de, fr, co.uk, etc.)
MARKETPLACE_PATTERN = re.compile(r"amazon\.(?:co\.)?([a-z]{2,3})")


def extract_asin(url: str) -> tuple[str, str]:
    """
    Extract ASIN and marketplace from Amazon URL.

    Supports multiple URL formats:
    - https://www.amazon.it/dp/B08N5WRWNW
    - https://amazon.it/gp/product/B08N5WRWNW/ref=...
    - https://www.amazon.it/Product-Name/dp/B08N5WRWNW/...
    - https://amzn.eu/d/B08N5WRWNW (short link)

    Args:
        url: Amazon product URL

    Returns:
        Tuple of (asin, marketplace)
        Example: ("B08N5WRWNW", "it")

    Raises:
        ValueError: If ASIN cannot be extracted from URL
    """
    # Extract ASIN
    asin_match = ASIN_PATTERN.search(url)
    if not asin_match:
        raise ValueError(f"Could not extract ASIN from URL: {url}")

    # Get first non-None group (/dp/, /gp/product/, or /d/ for short links)
    asin = asin_match.group(1) or asin_match.group(2) or asin_match.group(3)

    # Extract marketplace
    marketplace_match = MARKETPLACE_PATTERN.search(url)
    if not marketplace_match:
        # Default to .it if not found (common for short links)
        marketplace = "it"
        logger.warning(f"Could not extract marketplace from URL, defaulting to .it: {url}")
    else:
        marketplace = marketplace_match.group(1)

    logger.debug(f"Extracted ASIN={asin}, marketplace={marketplace} from {url}")
    return asin, marketplace


def build_affiliate_url(asin: str, marketplace: str = "it") -> str:
    """
    Build clean Amazon affiliate URL from ASIN.

    Args:
        asin: Amazon Standard Identification Number (10 chars)
        marketplace: Country code (it, com, de, fr, etc.)

    Returns:
        Clean affiliate URL: https://amazon.{marketplace}/dp/{asin}?tag={tag}
    """
    if cfg.amazon_affiliate_tag:
        return f"https://amazon.{marketplace}/dp/{asin}?tag={cfg.amazon_affiliate_tag}"
    else:
        return f"https://amazon.{marketplace}/dp/{asin}"


async def scrape_price(asin: str, marketplace: str = "it") -> float | None:
    """
    Fetch current price from Amazon via Creator API (convenience wrapper for single product).

    This is a thin wrapper around scrape_prices() for convenience when testing single products.
    For production use with multiple products, use scrape_prices() directly for better performance.

    Args:
        asin: Amazon Standard Identification Number
        marketplace: Country code (default: "it")

    Returns:
        Current price as float (e.g., 59.90)
        None if price cannot be fetched

    Example:
        >>> price = await scrape_price("B08N5WRWNW", "it")
        >>> print(f"Price: €{price:.2f}")
    """
    # Create a fake product dict for scrape_prices()
    fake_product = {"id": 0, "asin": asin, "marketplace": marketplace}

    # Use scrape_prices with single product (benefits from batch API, optimized logic)
    results = await scrape_prices([fake_product])

    # Return price or None
    return results.get(0)


async def scrape_prices(products: list[dict]) -> dict[int, float]:
    """
    Fetch prices for multiple products via Amazon Creator API.

    Uses the Creator API for efficient batch lookups. Each unique ASIN is fetched
    only once, even if multiple users are monitoring the same product.

    Args:
        products: List of product dicts with keys: id, asin, (optional) marketplace

    Returns:
        Dict mapping product_id -> price
        Products that failed to fetch are omitted from result

    Example:
        If 10 users monitor the same ASIN, it will be fetched only once,
        and the price will be mapped to all 10 product IDs.
    """
    results: dict[int, float] = {}

    # Group products by (asin, marketplace) to deduplicate fetching
    asin_to_product_ids: dict[tuple[str, str], list[int]] = {}
    for product in products:
        product_id = product["id"]
        asin = product["asin"]
        marketplace = product.get("marketplace", "it")
        key = (asin, marketplace)

        if key not in asin_to_product_ids:
            asin_to_product_ids[key] = []
        asin_to_product_ids[key].append(product_id)

    unique_asins = list(asin_to_product_ids.keys())
    logger.info(
        f"Fetching {len(unique_asins)} unique ASINs for {len(products)} total products "
        f"(deduplication saved {len(products) - len(unique_asins)} requests)"
    )

    # Group by marketplace for batched API calls
    marketplace_groups: dict[str, list[str]] = {}
    for asin, marketplace in unique_asins:
        if marketplace not in marketplace_groups:
            marketplace_groups[marketplace] = []
        marketplace_groups[marketplace].append(asin)

    # Fetch prices from API grouped by marketplace
    api_client = get_api_client()
    asin_prices: dict[str, dict[str, float | None]] = {}

    for marketplace, asins in marketplace_groups.items():
        try:
            prices = await api_client.get_items(asins, marketplace)
            asin_prices[marketplace] = prices
            logger.info(
                f"API returned prices for {sum(1 for p in prices.values() if p is not None)}"
                f"/{len(asins)} ASINs on amazon.{marketplace}"
            )
        except Exception as e:
            logger.error(f"API call failed for marketplace {marketplace}: {e}", exc_info=True)
            asin_prices[marketplace] = {}

    # Map API results back to product IDs
    for (asin, marketplace), product_ids in asin_to_product_ids.items():
        marketplace_prices = asin_prices.get(marketplace, {})
        price = marketplace_prices.get(asin)

        if price is not None:
            for product_id in product_ids:
                results[product_id] = price
            logger.debug(f"ASIN {asin} (€{price:.2f}) mapped to {len(product_ids)} product(s)")

    logger.info(f"Fetched {len(results)}/{len(products)} products successfully")
    return results


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    import database

    # Setup logging for manual testing
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Load environment variables
    load_dotenv()

    def _print_asin_extraction_test():
        """Print ASIN extraction test results."""
        test_urls = [
            "https://www.amazon.it/dp/B08N5WRWNW",
            "https://amazon.it/gp/product/B08N5WRWNW/ref=something",
            "https://www.amazon.it/Product-Name/dp/B08N5WRWNW/ref=sr_1_1",
        ]

        print("=" * 70)
        print("ASIN EXTRACTION TEST")
        print("=" * 70)
        for url in test_urls:
            asin, marketplace = extract_asin(url)
            print(f"\nURL: {url}")
            print(f"  ASIN: {asin}")
            print(f"  Marketplace: amazon.{marketplace}")
            print(f"  Affiliate URL: {build_affiliate_url(asin, marketplace)}")

        print("\n" + "=" * 70)

    async def _fetch_single_product(asin: str, marketplace: str):
        """Fetch a single product by ASIN."""
        print(f"SINGLE PRODUCT FETCH: {asin} (amazon.{marketplace})")
        print("=" * 70)

        price = await scrape_price(asin, marketplace)
        if price:
            print(f"✅ Price: €{price:.2f}")
        else:
            print("❌ Failed to fetch price")
            print("\nPossible reasons:")
            print(f"  - ASIN not found on amazon.{marketplace}")
            print("  - API credentials not configured")
            print("  - API rate limit reached")

    async def _fetch_all_products():
        """Fetch all products from database."""
        print("ALL PRODUCTS FETCH (from database)")
        print("=" * 70)

        # Initialize database
        await database.init_db()

        # Get all active products
        products = await database.get_all_active_products()

        if not products:
            print("❌ No active products found in database")
            print("\nTo fetch a single product, use:")
            print("  python data_reader.py <ASIN> [marketplace]")
            print("\nExamples:")
            print("  python data_reader.py B08N5WRWNW")
            print("  python data_reader.py B08N5WRWNW de")
            return

        print(f"Found {len(products)} active products\n")

        # Fetch all prices
        results = await scrape_prices(products)

        # Show results
        print("\n" + "=" * 70)
        print("FETCH RESULTS")
        print("=" * 70)

        for product in products:
            product_id = product["id"]
            asin = product["asin"]
            product_name = product.get("product_name") or f"ASIN {asin}"

            price = results.get(product_id)
            if price:
                print(f"\n✅ {product_name} ({asin})")
                print(f"   Price: €{price:.2f}")
            else:
                print(f"\n❌ {product_name} ({asin})")
                print("   Failed to fetch")

        # Calculate success rate
        success_count = sum(1 for p in results.values() if p is not None)
        total_count = len(products)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        print("\n" + "=" * 70)
        print(f"Success Rate: {success_count}/{total_count} ({success_rate:.1f}%)")
        print("=" * 70)

    async def main():
        """Main function for manual testing and fetching."""
        # Always show ASIN extraction test
        _print_asin_extraction_test()

        # Mode 1: Fetch single ASIN from command line
        if len(sys.argv) > 1:
            asin = sys.argv[1]
            marketplace = sys.argv[2] if len(sys.argv) > 2 else "it"
            await _fetch_single_product(asin, marketplace)
        # Mode 2: Fetch all products from database
        else:
            await _fetch_all_products()

    # Run async main
    asyncio.run(main())
