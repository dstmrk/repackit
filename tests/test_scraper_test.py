"""Unit tests for scraper_test.py."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import scraper_test
from scraper_test import (
    _print_debug_files,
    _print_price_verification,
    _print_product_info,
    _print_scraping_results,
    find_price_in_html,
    get_page_html,
    parse_args,
    print_error,
    print_header,
    print_info,
    print_result,
    print_results,
    print_success,
    run_scraper_test,
    save_debug_files,
    validate_asin,
    validate_price,
)


class TestValidation:
    """Test validation functions."""

    def test_validate_asin_valid(self):
        """Test ASIN validation with valid ASINs."""
        assert validate_asin("B08N5WRWNW") is True
        assert validate_asin("1234567890") is True
        assert validate_asin("ABCDEFGHIJ") is True

    def test_validate_asin_invalid(self):
        """Test ASIN validation with invalid ASINs."""
        assert validate_asin("B08N5WRWN") is False  # Too short
        assert validate_asin("B08N5WRWNW1") is False  # Too long
        assert validate_asin("b08n5wrwnw") is False  # Lowercase
        assert validate_asin("B08N5WRW W") is False  # Space
        assert validate_asin("") is False  # Empty

    def test_validate_price_valid(self):
        """Test price validation with valid prices."""
        assert validate_price(0.01) is True
        assert validate_price(59.90) is True
        assert validate_price(999999) is True
        assert validate_price(100.50) is True

    def test_validate_price_invalid(self):
        """Test price validation with invalid prices."""
        assert validate_price(0) is False  # Too low
        assert validate_price(0.005) is False  # Too low
        assert validate_price(1000000) is False  # Too high
        assert validate_price(-10) is False  # Negative


class TestArgumentParsing:
    """Test command line argument parsing."""

    def test_parse_args_minimal(self):
        """Test parsing with minimal required arguments."""
        with patch("sys.argv", ["scraper_test.py", "B08N5WRWNW", "59.90"]):
            args = parse_args()
            assert args.asin == "B08N5WRWNW"
            assert args.expected_price == 59.90
            assert args.marketplace == "it"
            assert args.save_debug is False
            assert args.verbose is False

    def test_parse_args_with_marketplace(self):
        """Test parsing with custom marketplace."""
        with patch("sys.argv", ["scraper_test.py", "B08N5WRWNW", "59.90", "-m", "de"]):
            args = parse_args()
            assert args.marketplace == "de"

    def test_parse_args_with_save_debug(self):
        """Test parsing with save debug flag."""
        with patch("sys.argv", ["scraper_test.py", "B08N5WRWNW", "59.90", "--save-debug"]):
            args = parse_args()
            assert args.save_debug is True

    def test_parse_args_with_verbose(self):
        """Test parsing with verbose flag."""
        with patch("sys.argv", ["scraper_test.py", "B08N5WRWNW", "59.90", "-v"]):
            args = parse_args()
            assert args.verbose is True

    def test_parse_args_all_options(self):
        """Test parsing with all options."""
        with patch(
            "sys.argv",
            ["scraper_test.py", "B08N5WRWNW", "59.90", "-m", "com", "-d", "-v"],
        ):
            args = parse_args()
            assert args.asin == "B08N5WRWNW"
            assert args.expected_price == 59.90
            assert args.marketplace == "com"
            assert args.save_debug is True
            assert args.verbose is True


class TestPriceSearchInHTML:
    """Test HTML price search functionality."""

    def test_find_price_exact_match_dot(self):
        """Test finding exact price with dot separator."""
        html = "<div>Price: 59.90</div>"
        result = find_price_in_html(html, 59.90)
        assert result["found"] is True
        assert result["count"] >= 1

    def test_find_price_exact_match_comma(self):
        """Test finding exact price with comma separator."""
        html = "<div>Prezzo: 59,90 €</div>"
        result = find_price_in_html(html, 59.90)
        assert result["found"] is True
        assert result["count"] >= 1

    def test_find_price_multiple_occurrences(self):
        """Test finding price with multiple occurrences."""
        html = "<div>Was: 59.90</div><div>Now: 59,90</div><div>Save: 59.90</div>"
        result = find_price_in_html(html, 59.90)
        assert result["found"] is True
        assert result["count"] >= 2

    def test_find_price_not_found(self):
        """Test when price is not found in HTML."""
        html = "<div>Price: 45.99</div>"
        result = find_price_in_html(html, 59.90)
        assert result["found"] is False
        assert result["count"] == 0

    def test_find_price_contexts(self):
        """Test that contexts are extracted."""
        html = "<div>Original price was 59.90 euros</div>"
        result = find_price_in_html(html, 59.90)
        assert result["found"] is True
        assert len(result["contexts"]) > 0
        assert "59.90" in result["contexts"][0] or "59,90" in result["contexts"][0]

    def test_find_price_context_limit(self):
        """Test that context results are limited to 5."""
        html = " ".join([f"<div>Price{i}: 59.90</div>" for i in range(20)])
        result = find_price_in_html(html, 59.90)
        assert len(result["contexts"]) <= 5


class TestPrintFunctions:
    """Test output printing functions."""

    def test_print_header(self, capsys):
        """Test header printing."""
        print_header("Test Header")
        captured = capsys.readouterr()
        assert "Test Header" in captured.out
        assert "=" in captured.out

    def test_print_success(self, capsys):
        """Test success message printing."""
        print_success("Success message")
        captured = capsys.readouterr()
        assert "Success message" in captured.out
        assert "✅" in captured.out

    def test_print_error(self, capsys):
        """Test error message printing."""
        print_error("Error message")
        captured = capsys.readouterr()
        assert "Error message" in captured.out
        assert "❌" in captured.out

    def test_print_info(self, capsys):
        """Test info message printing."""
        print_info("Info message")
        captured = capsys.readouterr()
        assert "Info message" in captured.out
        assert "ℹ️" in captured.out

    def test_print_result(self, capsys):
        """Test result line printing."""
        print_result("Label", "Value")
        captured = capsys.readouterr()
        assert "Label:" in captured.out
        assert "Value" in captured.out

    def test_print_product_info(self, capsys):
        """Test product info section printing."""
        results = {
            "asin": "B08N5WRWNW",
            "marketplace": "it",
            "expected_price": 59.90,
        }
        _print_product_info(results)
        captured = capsys.readouterr()
        assert "Product Information" in captured.out
        assert "B08N5WRWNW" in captured.out
        assert "amazon.it" in captured.out
        assert "59.90" in captured.out

    def test_print_scraping_results_success(self, capsys):
        """Test scraping results section with success."""
        results = {
            "success": True,
            "scraped_price": 45.00,
            "expected_price": 59.90,
            "duration_seconds": 2.5,
        }
        _print_scraping_results(results)
        captured = capsys.readouterr()
        assert "SUCCESSFUL" in captured.out
        assert "45.00" in captured.out

    def test_print_scraping_results_failure(self, capsys):
        """Test scraping results section with failure."""
        results = {
            "success": False,
            "error": "Test error",
            "duration_seconds": 30.0,
        }
        _print_scraping_results(results)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "Test error" in captured.out

    def test_print_price_verification_found(self, capsys):
        """Test price verification when price is found."""
        results = {
            "price_found_in_html": True,
            "expected_price": 59.90,
            "price_occurrences": 3,
            "price_contexts": ["Context 1", "Context 2"],
        }
        _print_price_verification(results)
        captured = capsys.readouterr()
        assert "Expected Price in HTML" in captured.out
        assert "Found" in captured.out

    def test_print_price_verification_not_found(self, capsys):
        """Test price verification when price is not found."""
        results = {
            "price_found_in_html": False,
            "expected_price": 59.90,
        }
        _print_price_verification(results)
        captured = capsys.readouterr()
        assert "NOT found" in captured.out

    def test_print_debug_files_present(self, capsys):
        """Test debug files section when files are present."""
        results = {
            "debug_files": {
                "html": "./debug_output/test.html",
                "screenshot": "./debug_output/test.png",
            }
        }
        _print_debug_files(results)
        captured = capsys.readouterr()
        assert "Debug Files" in captured.out
        assert "test.html" in captured.out
        assert "test.png" in captured.out

    def test_print_debug_files_empty(self, capsys):
        """Test debug files section when no files."""
        results = {"debug_files": {}}
        _print_debug_files(results)
        captured = capsys.readouterr()
        # Should print nothing
        assert "Debug Files" not in captured.out


class TestPrintResults:
    """Test results printing function."""

    def test_print_results_success(self, capsys):
        """Test printing successful results."""
        results = {
            "asin": "B08N5WRWNW",
            "marketplace": "it",
            "expected_price": 59.90,
            "scraped_price": 59.90,
            "success": True,
            "error": None,
            "duration_seconds": 2.5,
            "price_found_in_html": True,
            "price_occurrences": 3,
            "price_contexts": ["Context 1", "Context 2"],
            "debug_files": {},
        }
        print_results(results)
        captured = capsys.readouterr()
        assert "B08N5WRWNW" in captured.out
        assert "59.90" in captured.out
        assert "SUCCESSFUL" in captured.out

    def test_print_results_failure(self, capsys):
        """Test printing failed results."""
        results = {
            "asin": "B08N5WRWNW",
            "marketplace": "it",
            "expected_price": 59.90,
            "scraped_price": None,
            "success": False,
            "error": "Timeout error",
            "duration_seconds": 30.0,
            "price_found_in_html": False,
            "debug_files": {},
        }
        print_results(results)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "Timeout error" in captured.out

    def test_print_results_with_debug_files(self, capsys):
        """Test printing results with debug files."""
        results = {
            "asin": "B08N5WRWNW",
            "marketplace": "it",
            "expected_price": 59.90,
            "scraped_price": 59.90,
            "success": True,
            "duration_seconds": 2.5,
            "debug_files": {
                "html": "/tmp/test.html",
                "screenshot": "/tmp/test.png",
            },
        }
        print_results(results)
        captured = capsys.readouterr()
        assert "/tmp/test.html" in captured.out
        assert "/tmp/test.png" in captured.out

    def test_print_results_price_mismatch(self, capsys):
        """Test printing results with price mismatch."""
        results = {
            "asin": "B08N5WRWNW",
            "marketplace": "it",
            "expected_price": 59.90,
            "scraped_price": 45.00,
            "success": True,
            "duration_seconds": 2.5,
            "price_found_in_html": True,
            "price_occurrences": 1,
            "price_contexts": [],
            "debug_files": {},
        }
        print_results(results)
        captured = capsys.readouterr()
        assert "45.00" in captured.out
        assert "59.90" in captured.out


@pytest.mark.asyncio
class TestAsyncFunctions:
    """Test async functions with mocks."""

    async def test_get_page_html_success(self):
        """Test successful HTML retrieval."""
        mock_page = AsyncMock()
        mock_page.content.return_value = "<html>Test content</html>"
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        html = await get_page_html(mock_browser, "B08N5WRWNW", "it")

        assert html == "<html>Test content</html>"
        mock_browser.new_page.assert_called_once()
        mock_page.goto.assert_called_once()
        mock_page.close.assert_called_once()

    async def test_get_page_html_failure(self):
        """Test HTML retrieval failure."""
        mock_browser = AsyncMock()
        mock_browser.new_page.side_effect = Exception("Network error")

        html = await get_page_html(mock_browser, "B08N5WRWNW", "it")

        assert html is None

    async def test_save_debug_files_success(self, tmp_path):
        """Test successful debug file saving."""
        mock_page = AsyncMock()
        mock_page.content.return_value = "<html>Test</html>"
        mock_page.screenshot = AsyncMock()
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        html_path, screenshot_path = await save_debug_files(
            mock_browser, "B08N5WRWNW", "it", tmp_path
        )

        assert html_path is not None
        assert screenshot_path is not None
        assert html_path.exists()
        assert "B08N5WRWNW" in str(html_path)
        mock_page.screenshot.assert_called_once()

    async def test_save_debug_files_failure(self, tmp_path):
        """Test debug file saving failure."""
        mock_browser = AsyncMock()
        mock_browser.new_page.side_effect = Exception("Browser error")

        html_path, screenshot_path = await save_debug_files(
            mock_browser, "B08N5WRWNW", "it", tmp_path
        )

        assert html_path is None
        assert screenshot_path is None

    @patch("scraper_test._scrape_single_price")
    @patch("scraper_test.get_page_html")
    @patch("scraper_test.save_debug_files")
    async def test_test_scraper_success(self, mock_save_debug, mock_get_html, mock_scrape_price):
        """Test successful scraper test."""
        # Setup mocks
        mock_scrape_price.return_value = 45.99
        mock_get_html.return_value = "<html>Price: 59,90</html>"
        mock_save_debug.return_value = (Path("/tmp/test.html"), Path("/tmp/test.png"))

        # Mock playwright
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        mock_playwright.__aenter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.close = AsyncMock()

        with patch("scraper_test.async_playwright", return_value=mock_playwright):
            results = await run_scraper_test("B08N5WRWNW", 59.90, "it", save_debug=True)

        assert results["success"] is True
        assert results["scraped_price"] == 45.99
        assert results["expected_price"] == 59.90
        assert results["price_found_in_html"] is True
        assert "debug_files" in results

    @patch("scraper_test._scrape_single_price")
    async def test_test_scraper_failure(self, mock_scrape_price):
        """Test scraper test with scraping failure."""
        mock_scrape_price.return_value = None

        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        mock_playwright.__aenter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.close = AsyncMock()

        with patch("scraper_test.async_playwright", return_value=mock_playwright):
            results = await run_scraper_test("B08N5WRWNW", 59.90, "it", save_debug=False)

        assert results["success"] is False
        assert results["scraped_price"] is None

    @patch("scraper_test._scrape_single_price")
    async def test_test_scraper_exception(self, mock_scrape_price):
        """Test scraper test with exception."""
        mock_scrape_price.side_effect = Exception("Test error")

        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        mock_playwright.__aenter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.close = AsyncMock()

        with patch("scraper_test.async_playwright", return_value=mock_playwright):
            results = await run_scraper_test("B08N5WRWNW", 59.90, "it", save_debug=False)

        assert results["success"] is False
        assert results["error"] is not None
        assert "Test error" in results["error"]


@pytest.mark.asyncio
class TestMain:
    """Test main function."""

    @patch("scraper_test.run_scraper_test")
    async def test_main_success(self, mock_run_scraper_test):
        """Test main with successful scraping."""
        mock_run_scraper_test.return_value = {
            "asin": "B08N5WRWNW",
            "marketplace": "it",
            "expected_price": 59.90,
            "scraped_price": 59.90,
            "success": True,
            "duration_seconds": 2.5,
            "debug_files": {},
        }

        with patch("sys.argv", ["scraper_test.py", "B08N5WRWNW", "59.90"]):
            exit_code = await scraper_test.main()

        assert exit_code == 0

    @patch("scraper_test.run_scraper_test")
    async def test_main_scraping_failed(self, mock_run_scraper_test):
        """Test main with failed scraping."""
        mock_run_scraper_test.return_value = {
            "asin": "B08N5WRWNW",
            "marketplace": "it",
            "expected_price": 59.90,
            "scraped_price": None,
            "success": False,
            "error": None,
            "duration_seconds": 30.0,
            "debug_files": {},
        }

        with patch("sys.argv", ["scraper_test.py", "B08N5WRWNW", "59.90"]):
            exit_code = await scraper_test.main()

        assert exit_code == 1

    async def test_main_invalid_asin(self):
        """Test main with invalid ASIN."""
        with patch("sys.argv", ["scraper_test.py", "INVALID", "59.90"]):
            exit_code = await scraper_test.main()

        assert exit_code == 1

    async def test_main_invalid_price(self):
        """Test main with invalid price."""
        with patch("sys.argv", ["scraper_test.py", "B08N5WRWNW", "0"]):
            exit_code = await scraper_test.main()

        assert exit_code == 1

    @patch("scraper_test.run_scraper_test")
    async def test_main_with_all_options(self, mock_run_scraper_test):
        """Test main with all command line options."""
        mock_run_scraper_test.return_value = {
            "asin": "B08N5WRWNW",
            "marketplace": "de",
            "expected_price": 99.99,
            "scraped_price": 99.99,
            "success": True,
            "duration_seconds": 2.5,
            "debug_files": {"html": "/tmp/test.html"},
        }

        with patch(
            "sys.argv",
            ["scraper_test.py", "B08N5WRWNW", "99.99", "-m", "de", "-d", "-v"],
        ):
            exit_code = await scraper_test.main()

        assert exit_code == 0
        mock_run_scraper_test.assert_called_once()
        call_kwargs = mock_run_scraper_test.call_args[1]
        assert call_kwargs["asin"] == "B08N5WRWNW"
        assert call_kwargs["expected_price"] == 99.99
        assert call_kwargs["marketplace"] == "de"
        assert call_kwargs["save_debug"] is True
