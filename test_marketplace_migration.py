#!/usr/bin/env python3
"""
Test script for marketplace migration.
Run this after deploying to verify the marketplace fix works correctly.

Usage:
    uv run python test_marketplace_migration.py
"""

import asyncio
import os
import sys
from datetime import date, timedelta

# Use test database
os.environ["DATABASE_PATH"] = "./data/test_marketplace.db"

import database
from data_reader import extract_asin


async def test_marketplace_feature():
    """Test marketplace extraction and database storage."""
    print("=" * 70)
    print("Testing Marketplace Feature Fix")
    print("=" * 70)
    print()

    try:
        # 1. Test ASIN extraction
        print("1. Testing ASIN and marketplace extraction:")
        test_urls = [
            ("https://www.amazon.it/dp/B08N5WRWNW", "B08N5WRWNW", "it"),
            ("https://www.amazon.com/dp/B08N5WRWNW", "B08N5WRWNW", "com"),
            ("https://www.amazon.de/dp/B08N5WRWNW", "B08N5WRWNW", "de"),
            ("https://www.amazon.co.uk/dp/B08N5WRWNW", "B08N5WRWNW", "uk"),
        ]

        for url, expected_asin, expected_marketplace in test_urls:
            asin, marketplace = extract_asin(url)
            assert asin == expected_asin, f"ASIN mismatch for {url}"
            assert marketplace == expected_marketplace, f"Marketplace mismatch for {url}"
            print(f"   ✅ {url} -> {marketplace}")
        print()

        # 2. Initialize database
        print("2. Initializing database with migration...")
        await database.init_db()
        print("   ✅ Database initialized")
        print()

        # 3. Add test user
        print("3. Adding test user...")
        await database.add_user(user_id=999999, language_code="it")
        print("   ✅ User added")
        print()

        # 4. Add products with different marketplaces
        print("4. Adding products from different marketplaces:")
        test_products = [
            ("B08N5WRWNW", "it", 59.90),
            ("B08N5WRWNX", "com", 69.90),
            ("B08N5WRWNY", "de", 79.90),
        ]

        for asin, marketplace, price in test_products:
            product_id = await database.add_product(
                user_id=999999,
                asin=asin,
                marketplace=marketplace,
                price_paid=price,
                return_deadline=date.today() + timedelta(days=30),
                min_savings_threshold=5.0,
            )
            print(f"   ✅ Added product {product_id}: amazon.{marketplace} / {asin}")
        print()

        # 5. Retrieve and verify products
        print("5. Retrieving products from database:")
        products = await database.get_user_products(user_id=999999)
        print(f"   Found {len(products)} products")
        print()

        print("6. Verifying marketplace field:")
        all_correct = True
        for product in products:
            asin = product["asin"]
            marketplace = product.get("marketplace")

            if marketplace is None:
                print(f"   ❌ Product {asin}: marketplace field is NULL!")
                all_correct = False
            else:
                print(f"   ✅ Product {asin}: marketplace = amazon.{marketplace}")

        print()

        # 7. Test get_all_active_products
        print("7. Testing get_all_active_products:")
        active = await database.get_all_active_products()
        test_products_found = [p for p in active if p["user_id"] == 999999]
        print(f"   Found {len(test_products_found)} active test products")
        for p in test_products_found:
            print(f"   - {p['asin']} on amazon.{p.get('marketplace', 'MISSING')}")
        print()

        # Cleanup
        print("8. Cleaning up test data...")
        for product in products:
            await database.delete_product(product["id"])
        print("   ✅ Test products deleted")
        print()

        if all_correct:
            print("=" * 70)
            print("🎉 ALL TESTS PASSED - Marketplace feature works correctly!")
            print("=" * 70)
            return 0
        else:
            print("=" * 70)
            print("⚠️  TESTS FAILED - Some issues detected")
            print("=" * 70)
            return 1

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_marketplace_feature())
    sys.exit(exit_code)
