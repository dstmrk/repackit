"""Amazon scraper testing tool.

Manual testing tool for data_reader.py scraper functionality.
Allows testing ASIN scraping with expected price verification.

Usage:
    uv run python scraper_test.py B08N5WRWNW 59.90
    uv run python scraper_test.py B08N5WRWNW 59.90 --marketplace it
    uv run python scraper_test.py B08N5WRWNW 59.90 --save-debug
"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import Browser, async_playwright

from data_reader import _scrape_single_price, build_affiliate_url


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(text: str) -> None:
    """Print colored header."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}{text}{Colors.ENDC}")
    print("=" * 60)


def print_success(text: str) -> None:
    """Print success message."""
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ️  {text}{Colors.ENDC}")


def print_result(label: str, value: str, indent: int = 3) -> None:
    """Print result line with label and value."""
    print(f"{' ' * indent}{Colors.BOLD}{label}:{Colors.ENDC} {value}")


async def get_page_html(browser: Browser, asin: str, marketplace: str) -> str | None:
    """
    Get full HTML content of Amazon product page.

    Args:
        browser: Playwright browser instance
        asin: Amazon Standard Identification Number
        marketplace: Country code (e.g., "it")

    Returns:
        HTML content as string, or None if failed
    """
    url = f"https://amazon.{marketplace}/dp/{asin}"

    try:
        page = await browser.new_page()
        await page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        html = await page.content()
        await page.close()
        return html
    except Exception as e:
        logging.error(f"Failed to get page HTML: {e}")
        return None


async def save_debug_files(
    browser: Browser, asin: str, marketplace: str, output_dir: Path
) -> tuple[Path | None, Path | None]:
    """
    Save HTML and screenshot for debugging.

    Args:
        browser: Playwright browser instance
        asin: Amazon Standard Identification Number
        marketplace: Country code
        output_dir: Directory to save files

    Returns:
        Tuple of (html_path, screenshot_path), None if failed
    """
    url = f"https://amazon.{marketplace}/dp/{asin}"

    try:
        page = await browser.new_page()
        await page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Save HTML
        html = await page.content()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = output_dir / f"scraper_test_{asin}_{timestamp}.html"
        screenshot_path = output_dir / f"scraper_test_{asin}_{timestamp}.png"

        html_path.write_text(html, encoding="utf-8")
        await page.screenshot(path=str(screenshot_path), full_page=True)

        await page.close()
        return html_path, screenshot_path
    except Exception as e:
        logging.error(f"Failed to save debug files: {e}")
        return None, None


def find_price_in_html(html: str, expected_price: float) -> dict[str, any]:
    """
    Search for expected price in HTML content.

    Args:
        html: Full HTML content
        expected_price: Price to search for

    Returns:
        Dict with keys: found (bool), count (int), contexts (list of str)
    """
    # Format price in various ways Amazon might display it
    price_str = f"{expected_price:.2f}"
    price_comma = price_str.replace(".", ",")  # Italian format: 59,90
    price_int = str(int(expected_price))  # Just the integer part

    patterns = [
        re.escape(price_str),  # 59.90
        re.escape(price_comma),  # 59,90
        rf"{re.escape(price_int)}[,\.]\d{{2}}",  # 59.90 or 59,90
    ]

    found_contexts = []
    total_count = 0

    for pattern in patterns:
        matches = re.finditer(pattern, html, re.IGNORECASE)
        for match in matches:
            total_count += 1
            # Get context around the match (50 chars before and after)
            start = max(0, match.start() - 50)
            end = min(len(html), match.end() + 50)
            context = html[start:end].strip()
            # Clean HTML tags for readability
            context = re.sub(r"<[^>]+>", " ", context)
            context = re.sub(r"\s+", " ", context)
            if context and context not in found_contexts:
                found_contexts.append(context)

    return {
        "found": total_count > 0,
        "count": total_count,
        "contexts": found_contexts[:5],  # Limit to 5 examples
    }


async def run_scraper_test(
    asin: str, expected_price: float, marketplace: str = "it", save_debug: bool = False
) -> dict:
    """
    Test scraper for a specific ASIN with expected price.

    Args:
        asin: Amazon Standard Identification Number
        expected_price: Expected price to verify
        marketplace: Country code (default: "it")
        save_debug: Whether to save HTML and screenshot

    Returns:
        Dict with test results
    """
    results = {
        "asin": asin,
        "marketplace": marketplace,
        "expected_price": expected_price,
        "scraped_price": None,
        "success": False,
        "error": None,
        "duration_seconds": 0,
        "price_found_in_html": False,
        "debug_files": {},
    }

    start_time = datetime.now()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        try:
            # Scrape price
            price = await _scrape_single_price(browser, asin, marketplace)
            results["scraped_price"] = price
            results["success"] = price is not None

            # Get page HTML for price verification
            html = await get_page_html(browser, asin, marketplace)
            if html:
                price_search = find_price_in_html(html, expected_price)
                results["price_found_in_html"] = price_search["found"]
                results["price_occurrences"] = price_search["count"]
                results["price_contexts"] = price_search["contexts"]

            # Save debug files if requested
            if save_debug:
                # Use secure temporary directory instead of /tmp
                # Create debug_output directory in current working directory
                output_dir = Path.cwd() / "debug_output"
                output_dir.mkdir(exist_ok=True)
                html_path, screenshot_path = await save_debug_files(
                    browser, asin, marketplace, output_dir
                )
                if html_path:
                    results["debug_files"]["html"] = str(html_path)
                if screenshot_path:
                    results["debug_files"]["screenshot"] = str(screenshot_path)

        except Exception as e:
            results["error"] = str(e)
            logging.error(f"Scraper test failed: {e}", exc_info=True)
        finally:
            await browser.close()

    results["duration_seconds"] = (datetime.now() - start_time).total_seconds()
    return results


def _print_product_info(results: dict) -> None:
    """Print product information section."""
    print(f"\n{Colors.BOLD}📦 Product Information:{Colors.ENDC}")
    print_result("ASIN", results["asin"])
    print_result("Marketplace", f"amazon.{results['marketplace']}")
    print_result("Expected price", f"€{results['expected_price']:.2f}")
    affiliate_url = build_affiliate_url(results["asin"], results["marketplace"])
    print_result("URL", affiliate_url)


def _print_scraping_results(results: dict) -> None:
    """Print scraping results section."""
    print(f"\n{Colors.BOLD}📊 Scraping Results:{Colors.ENDC}")

    if results["success"]:
        print_success("SCRAPING SUCCESSFUL")
        scraped = results["scraped_price"]
        expected = results["expected_price"]

        print_result("Scraped price", f"€{scraped:.2f}")
        print_result("Expected price", f"€{expected:.2f}")

        # Price match
        match = abs(scraped - expected) < 0.01
        if match:
            print_result("Match", f"{Colors.OKGREEN}✅ YES{Colors.ENDC}")
        else:
            diff = abs(scraped - expected)
            print_result("Match", f"{Colors.WARNING}❌ NO (difference: €{diff:.2f}){Colors.ENDC}")
    else:
        print_error("SCRAPING FAILED")
        if results.get("error"):
            print_result("Error", results["error"])

    print_result("Duration", f"{results['duration_seconds']:.2f}s")


def _print_price_verification(results: dict) -> None:
    """Print price verification in HTML section."""
    if results.get("price_found_in_html") is None:
        return

    print(f"\n{Colors.BOLD}🔎 Expected Price in HTML:{Colors.ENDC}")
    if results["price_found_in_html"]:
        print_success(
            f"Found '{results['expected_price']:.2f}' in page HTML "
            f"({results['price_occurrences']} occurrences)"
        )
        if results.get("price_contexts"):
            print(f"\n{' ' * 3}{Colors.BOLD}Sample contexts:{Colors.ENDC}")
            for i, context in enumerate(results["price_contexts"][:3], 1):
                print(f"{' ' * 5}{i}. \"{context[:80]}...\"")
    else:
        print_error("Expected price NOT found in page HTML")


def _print_debug_files(results: dict) -> None:
    """Print debug files section."""
    if not results["debug_files"]:
        return

    print(f"\n{Colors.BOLD}💾 Debug Files:{Colors.ENDC}")
    if "html" in results["debug_files"]:
        print_result("HTML", results["debug_files"]["html"])
    if "screenshot" in results["debug_files"]:
        print_result("Screenshot", results["debug_files"]["screenshot"])


def print_results(results: dict) -> None:
    """
    Print test results in formatted output.

    Args:
        results: Dict with test results from run_scraper_test()
    """
    print_header("🔍 Amazon Scraper Test Results")
    _print_product_info(results)
    _print_scraping_results(results)
    _print_price_verification(results)
    _print_debug_files(results)
    print("\n" + "=" * 60 + "\n")


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Test Amazon scraper with ASIN and expected price",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s B08N5WRWNW 59.90
  %(prog)s B08N5WRWNW 59.90 --marketplace de
  %(prog)s B08N5WRWNW 59.90 --save-debug
  %(prog)s B08N5WRWNW 59.90 --verbose
        """,
    )

    parser.add_argument("asin", help="Amazon ASIN (10 characters, e.g., B08N5WRWNW)")

    parser.add_argument("expected_price", type=float, help="Expected price to verify (e.g., 59.90)")

    parser.add_argument(
        "--marketplace",
        "-m",
        default="it",
        help="Amazon marketplace country code (default: it)",
    )

    parser.add_argument(
        "--save-debug",
        "-d",
        action="store_true",
        help="Save HTML and screenshot to /tmp for debugging",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging (DEBUG level)"
    )

    return parser.parse_args()


def validate_asin(asin: str) -> bool:
    """
    Validate ASIN format.

    Args:
        asin: ASIN to validate

    Returns:
        True if valid, False otherwise
    """
    return bool(re.match(r"^[A-Z0-9]{10}$", asin))


def validate_price(price: float) -> bool:
    """
    Validate price value.

    Args:
        price: Price to validate

    Returns:
        True if valid, False otherwise
    """
    return 0.01 <= price <= 999999


async def main() -> int:
    """
    Main entry point for scraper test script.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Validate inputs
    if not validate_asin(args.asin):
        print_error(f"Invalid ASIN format: {args.asin}")
        print_info("ASIN must be 10 alphanumeric characters (e.g., B08N5WRWNW)")
        return 1

    if not validate_price(args.expected_price):
        print_error(f"Invalid price: {args.expected_price}")
        print_info("Price must be between €0.01 and €999,999")
        return 1

    # Run test
    print_info(f"Testing scraper for ASIN {args.asin}...")
    print_info(f"Marketplace: amazon.{args.marketplace}")
    print_info(f"Expected price: €{args.expected_price:.2f}")

    if args.save_debug:
        print_info("Debug files will be saved to ./debug_output")

    results = await run_scraper_test(
        asin=args.asin,
        expected_price=args.expected_price,
        marketplace=args.marketplace,
        save_debug=args.save_debug,
    )

    # Print results
    print_results(results)

    # Return exit code
    return 0 if results["success"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
