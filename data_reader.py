"""Amazon data reader for price scraping."""

import asyncio
import logging
import os
import re

from playwright.async_api import Browser, TimeoutError, async_playwright

# Configure logging
logger = logging.getLogger(__name__)

# Get affiliate tag from environment
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "")

# Retry configuration for scraping
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0  # seconds
BACKOFF_MULTIPLIER = 2.0

# ASIN pattern: 10 alphanumeric characters
# Supports: /dp/, /gp/product/, and short links /d/
ASIN_PATTERN = re.compile(r"/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})|/d/([A-Z0-9]{10})")

# Marketplace pattern: extract domain suffix (it, com, de, fr, co.uk, etc.)
MARKETPLACE_PATTERN = re.compile(r"amazon\.(?:co\.)?([a-z]{2,3})")

# Price selectors to try in order (Amazon's HTML structure changes frequently)
# More specific selectors first to avoid capturing wrong prices (variants, other sellers, etc.)
PRICE_SELECTORS = [
    # Desktop buy box - most specific
    "#corePriceDisplay_desktop_feature_div .a-price[data-a-color='price'] .a-offscreen",
    # Core price section with explicit price color
    "#corePrice_feature_div .a-price[data-a-color='price'] .a-offscreen",
    # Buy box with large text (typical of main price)
    ".a-section.a-spacing-none.aok-align-center .a-price[data-a-size='xl'] .a-offscreen",
    # Mobile buy box
    "#corePriceDisplay_mobile_feature_div .a-price .a-offscreen",
    # Generic core price (less specific, but still better than completely generic)
    "#corePrice_feature_div .a-price .a-offscreen",
    # Legacy selectors (old Amazon layout)
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    # Fallback to generic selector (may pick wrong price, but better than nothing)
    ".a-price .a-offscreen",
    ".a-price-whole",  # Separated price (need to combine with decimal)
]


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
    if AMAZON_AFFILIATE_TAG:
        return f"https://amazon.{marketplace}/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
    else:
        return f"https://amazon.{marketplace}/dp/{asin}"


async def scrape_price(asin: str, marketplace: str = "it") -> float | None:
    """
    Scrape current price from Amazon product page (convenience wrapper for manual testing).

    This is a thin wrapper around scrape_prices() for convenience when testing single products.
    For production use with multiple products, use scrape_prices() directly for better performance.

    Args:
        asin: Amazon Standard Identification Number
        marketplace: Country code (default: "it")

    Returns:
        Current price as float (e.g., 59.90)
        None if price cannot be scraped

    Example:
        >>> price = await scrape_price("B08N5WRWNW", "it")
        >>> print(f"Price: €{price:.2f}")
    """
    # Create a fake product dict for scrape_prices()
    fake_product = {"id": 0, "asin": asin, "marketplace": marketplace}

    # Use scrape_prices with single product (benefits from shared browser, optimized logic)
    results = await scrape_prices([fake_product])

    # Return price or None
    return results.get(0)


async def _scrape_single_price(browser: Browser, asin: str, marketplace: str) -> float | None:
    """
    Internal function to scrape price using existing browser instance.

    Args:
        browser: Playwright browser instance
        asin: Amazon Standard Identification Number
        marketplace: Country code

    Returns:
        Price as float or None if not found
    """
    url = f"https://amazon.{marketplace}/dp/{asin}"

    try:
        # Create new page
        page = await browser.new_page()

        # Set realistic user agent to avoid detection
        await page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )

        # Navigate to product page
        logger.debug(f"Scraping {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Try each price selector
        price_text = None
        for i, selector in enumerate(PRICE_SELECTORS, 1):
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    price_text = await element.inner_text()
                    if price_text:
                        logger.info(f"Found price with selector #{i} '{selector}': {price_text}")
                        break
            except TimeoutError:
                logger.debug(f"Selector #{i} '{selector}' not found, trying next...")
                continue

        await page.close()

        if not price_text:
            logger.warning(f"Could not find price for ASIN {asin} on amazon.{marketplace}")
            return None

        # Parse price from text (handle various formats)
        price = _parse_price(price_text)
        if price:
            logger.info(f"Successfully scraped price for {asin}: €{price}")
        return price

    except Exception as e:
        logger.error(f"Error scraping {asin} from amazon.{marketplace}: {e}", exc_info=True)
        return None


def _parse_price(price_text: str) -> float | None:
    """
    Parse price from text, handling various formats including thousands separators.

    Examples:
    - "€59,90" -> 59.90
    - "59.90" -> 59.90
    - "59,90 €" -> 59.90
    - "$59.90" -> 59.90
    - "1.999,99" (Italian: thousands.decimal) -> 1999.99
    - "1,999.99" (English: thousands.decimal) -> 1999.99

    Args:
        price_text: Raw price text from page

    Returns:
        Price as float or None if parsing fails
    """
    try:
        # Remove currency symbols and whitespace
        cleaned = price_text.strip().replace("€", "").replace("$", "").replace(" ", "")

        # Determine decimal separator by checking which appears last
        # (decimal separator is always at the end, thousands in the middle)
        last_comma = cleaned.rfind(",")
        last_dot = cleaned.rfind(".")

        if last_comma > last_dot:
            # Format: "1.999,99" (Italian) - comma is decimal separator
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif last_dot > last_comma:
            # Format: "1,999.99" (English) - dot is decimal separator
            cleaned = cleaned.replace(",", "")
        # else: no separators or only one type - handle normally

        # Extract first number (handles cases like "59.90 - 69.90")
        match = re.search(r"(\d+\.?\d*)", cleaned)
        if match:
            price = float(match.group(1))
            # Sanity check: prices should be reasonable (0.01 to 999999)
            if 0.01 <= price <= 999999:
                return price
            logger.warning(f"Price {price} out of reasonable range from '{price_text}'")
            return None

        return None
    except (ValueError, AttributeError) as e:
        logger.warning(f"Could not parse price from '{price_text}': {e}")
        return None


async def scrape_prices(products: list[dict], rate_limit_seconds: float = 1.5) -> dict[int, float]:
    """
    Scrape prices for multiple products efficiently.

    Uses a single browser instance and applies rate limiting to avoid detection.
    Optimizes scraping by deduplicating ASINs - each unique ASIN is scraped only once,
    even if multiple users are monitoring the same product.

    Args:
        products: List of product dicts with keys: id, asin, (optional) marketplace
        rate_limit_seconds: Delay between requests (default: 1.5s)

    Returns:
        Dict mapping product_id -> price
        Products that failed to scrape are omitted from result

    Example:
        If 10 users monitor the same ASIN, it will be scraped only once,
        and the price will be mapped to all 10 product IDs.
    """
    results = {}

    # Group products by (asin, marketplace) to deduplicate scraping
    asin_to_product_ids = {}
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
        f"Scraping {len(unique_asins)} unique ASINs for {len(products)} total products "
        f"(deduplication saved {len(products) - len(unique_asins)} requests)"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],  # Docker compatibility
        )

        try:
            for i, (asin, marketplace) in enumerate(unique_asins):
                # Scrape price once for this ASIN
                price = await _scrape_single_price(browser, asin, marketplace)

                # Map price to all product IDs that share this ASIN
                if price is not None:
                    product_ids = asin_to_product_ids[(asin, marketplace)]
                    for product_id in product_ids:
                        results[product_id] = price
                    logger.debug(
                        f"ASIN {asin} (€{price:.2f}) mapped to {len(product_ids)} product(s)"
                    )

                # Rate limiting: wait before next request
                if i < len(unique_asins) - 1:  # Don't wait after last ASIN
                    await asyncio.sleep(rate_limit_seconds)

        finally:
            await browser.close()

    logger.info(f"Scraped {len(results)}/{len(products)} products successfully")
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

    async def main():
        """Main function for manual testing and scraping."""
        # Test ASIN extraction (always shown)
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

        # Mode 1: Scrape single ASIN from command line
        if len(sys.argv) > 1:
            asin = sys.argv[1]
            marketplace = sys.argv[2] if len(sys.argv) > 2 else "it"

            print(f"SINGLE PRODUCT SCRAPE: {asin} (amazon.{marketplace})")
            print("=" * 70)

            price = await scrape_price(asin, marketplace)
            if price:
                print(f"✅ Price: €{price:.2f}")
            else:
                print("❌ Failed to scrape price")
                print("\nPossible reasons:")
                print("  - ASIN not found on amazon.{marketplace}")
                print("  - Network error")
                print("  - Amazon blocked the request")

        # Mode 2: Scrape all products from database
        else:
            print("ALL PRODUCTS SCRAPE (from database)")
            print("=" * 70)

            # Initialize database
            await database.init_db()

            # Get all active products
            products = await database.get_all_active_products()

            if not products:
                print("❌ No active products found in database")
                print("\nTo scrape a single product, use:")
                print("  python data_reader.py <ASIN> [marketplace]")
                print("\nExamples:")
                print("  python data_reader.py B08N5WRWNW")
                print("  python data_reader.py B08N5WRWNW de")
                return

            print(f"Found {len(products)} active products\n")

            # Scrape all prices
            results = await scrape_prices(products)

            # Show results
            print("\n" + "=" * 70)
            print("SCRAPING RESULTS")
            print("=" * 70)

            for product in products:
                product_id = product["id"]
                asin = product["asin"]
                marketplace = product.get("marketplace", "it")
                product_name = product.get("product_name") or f"ASIN {asin}"

                price = results.get(product_id)

                if price:
                    print(f"\n✅ {product_name}")
                    print(f"   ASIN: {asin} (amazon.{marketplace})")
                    print(f"   Price: €{price:.2f}")
                else:
                    print(f"\n❌ {product_name}")
                    print(f"   ASIN: {asin} (amazon.{marketplace})")
                    print("   Failed to scrape")

            # Summary
            success_count = len(results)
            total_count = len(products)
            success_rate = (success_count / total_count * 100) if total_count > 0 else 0

            print("\n" + "=" * 70)
            print(f"Successfully scraped: {success_count}/{total_count} ({success_rate:.1f}%)")
            print("=" * 70)

    # Run async main
    asyncio.run(main())
