import os
import sys
import pytest
import asyncio
import logging
from typing import Dict, Any
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page

# Add the root directory to Python path for imports
root_dir = str(Path(__file__).resolve().parents[1])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.jarvis.mcp_servers.amazon.server import (
    AmazonBrowserManager,
    ResilientSelector,
    search_amazon_products,
    get_product_details,
    get_product_reviews,
    refine_search,
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Test data
TEST_ASIN = "B08H8VZ6PV"  # Example ASIN
TEST_SEARCH_QUERY = "laptop"
TEST_PRODUCT_URL = f"https://www.amazon.in/dp/{TEST_ASIN}"
TEST_PRODUCT_ID = "B08N5KWB9H"

MOCK_PRODUCT = {
    "asin": "B08N5KWB9H",
    "title": "Test Product",
    "price": "₹999.00",
    "rating": 4.5,
    "reviews_count": "1,234",
    "image_url": "https://example.com/image.jpg",
    "product_url": "https://www.amazon.in/dp/B08N5KWB9H",
}


@pytest_asyncio.fixture
async def mock_browser():
    """Create a mock browser instance"""
    browser = AsyncMock()
    context = AsyncMock()
    page = AsyncMock()

    # Configure browser
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    # Configure context
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()

    # Configure page
    page.close = AsyncMock()
    page.goto = AsyncMock(return_value=AsyncMock(status=200))
    page.wait_for_selector = AsyncMock(return_value=AsyncMock())
    page.query_selector = AsyncMock(return_value=AsyncMock())
    page.query_selector_all = AsyncMock(return_value=[AsyncMock()])
    page.evaluate = AsyncMock(return_value="Test Text")
    page.route = AsyncMock()
    page.set_default_navigation_timeout = AsyncMock()
    page.set_default_timeout = AsyncMock()
    page.add_init_script = AsyncMock()
    page.mouse = AsyncMock()
    page.keyboard = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>Test Content</body></html>")

    return browser


@pytest_asyncio.fixture
async def mock_page(mock_browser):
    """Create a mock page instance with proper response mocking"""
    context = await mock_browser.new_context()
    page = await context.new_page()

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.ok = True

    # Configure page behaviors
    page.goto = AsyncMock(return_value=mock_response)
    page.wait_for_selector = AsyncMock(return_value=AsyncMock())
    page.query_selector = AsyncMock(return_value=AsyncMock())
    page.query_selector_all = AsyncMock(return_value=[AsyncMock()])
    page.evaluate = AsyncMock(return_value="Test Text")
    page.route = AsyncMock()
    page.set_default_navigation_timeout = AsyncMock()
    page.set_default_timeout = AsyncMock()
    page.mouse = AsyncMock()
    page.keyboard = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>Test Page</body></html>")
    page.wait_for_load_state = AsyncMock()
    page.close = AsyncMock()
    page.add_init_script = AsyncMock()

    # Mock element methods
    mock_element = AsyncMock()
    mock_element.inner_text = AsyncMock(return_value="Test Text")
    mock_element.get_attribute = AsyncMock(return_value="test-value")
    mock_element.evaluate = AsyncMock(return_value="Test Text")

    page.query_selector = AsyncMock(return_value=mock_element)
    page.query_selector_all = AsyncMock(return_value=[mock_element] * 5)

    return page


@pytest_asyncio.fixture
async def browser_manager(mock_browser):
    """Create a browser manager instance with mocked components"""
    with patch(
        "app.jarvis.mcp_servers.amazon.server.async_playwright"
    ) as mock_playwright:
        mock_playwright_instance = AsyncMock()
        mock_playwright_instance.chromium = AsyncMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_instance.stop = AsyncMock()
        mock_playwright.return_value.start = AsyncMock(
            return_value=mock_playwright_instance
        )

        manager = AmazonBrowserManager()
        manager.browser = mock_browser
        manager.context = mock_browser.new_context.return_value
        manager.page = mock_browser.new_context.return_value.new_page.return_value
        manager.playwright = mock_playwright_instance

        # Mock page behaviors
        manager.page.set_default_navigation_timeout = AsyncMock()
        manager.page.set_default_timeout = AsyncMock()
        manager.page.add_init_script = AsyncMock()
        manager.page.route = AsyncMock()

        # Configure selector
        manager.selector = AsyncMock()
        manager.selector.extract_text = AsyncMock(return_value="Test Text")
        manager.selector.extract_images = AsyncMock(
            return_value=["https://example.com/image.jpg"]
        )
        manager.selector.select_element = AsyncMock(
            return_value=AsyncMock(
                inner_text=AsyncMock(return_value="Test Text"),
                get_attribute=AsyncMock(return_value="test-value"),
            )
        )

        # Mock _setup_page_behaviors to return True
        manager._setup_page_behaviors = AsyncMock(return_value=True)

        # Mock create_browser_context to return True
        manager.create_browser_context = AsyncMock(return_value=True)

        return manager


class TestAmazonBrowserManager:
    """Test cases for AmazonBrowserManager class"""

    @pytest.mark.asyncio
    async def test_create_browser_context(self, mock_browser):
        """Test browser context creation"""
        with patch(
            "app.jarvis.mcp_servers.amazon.server.async_playwright"
        ) as mock_playwright:
            mock_playwright_instance = AsyncMock()
            mock_playwright_instance.chromium = AsyncMock()
            mock_playwright_instance.chromium.launch = AsyncMock(
                return_value=mock_browser
            )
            mock_playwright_instance.stop = AsyncMock()
            mock_playwright.return_value.start = AsyncMock(
                return_value=mock_playwright_instance
            )

            manager = AmazonBrowserManager()
            success = await manager.create_browser_context()
            assert success is True

    @pytest.mark.asyncio
    async def test_navigate_to_url(self, browser_manager):
        """Test URL navigation"""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.ok = True
        browser_manager.page.goto = AsyncMock(return_value=mock_response)

        success = await browser_manager.navigate_to_url(TEST_PRODUCT_URL)
        assert success is True

    @pytest.mark.asyncio
    async def test_cleanup(self, browser_manager):
        """Test resource cleanup"""
        # Store references before cleanup
        context = browser_manager.context
        browser = browser_manager.browser
        page = browser_manager.page

        await browser_manager._cleanup()

        # Verify cleanup calls
        page.close.assert_called_once()
        context.close.assert_called_once()
        browser.close.assert_called_once()


class TestResilientSelector:
    """Test cases for ResilientSelector class"""

    @pytest.mark.asyncio
    async def test_select_element(self, mock_page):
        """Test element selection with multiple strategies"""
        selector = ResilientSelector(mock_page)
        strategies = [
            {"type": "css", "selector": "#test"},
            {"type": "xpath", "selector": "//div[@id='test']"},
        ]

        # Configure mock to return an element
        mock_element = AsyncMock()
        mock_element.inner_text = AsyncMock(return_value="Test Text")
        mock_page.query_selector.return_value = mock_element

        element = await selector.select_element(strategies, context="test")
        assert element is not None
        mock_page.query_selector.assert_called()

    @pytest.mark.asyncio
    async def test_extract_text(self, mock_page):
        """Test text extraction"""
        selector = ResilientSelector(mock_page)
        strategies = [
            {"type": "css", "selector": "#test"},
        ]

        # Configure mock to return text
        mock_element = AsyncMock()
        mock_element.inner_text = AsyncMock(return_value="Test Text")
        mock_page.query_selector.return_value = mock_element

        text = await selector.extract_text(strategies, context="test")
        assert text == "Test Text"
        mock_page.query_selector.assert_called()


@pytest.mark.asyncio
async def test_search_products_success(browser_manager):
    """Test successful product search"""
    # Mock successful product search response
    mock_products = [
        {
            "asin": f"B08TEST{i}",
            "title": f"Test Product {i}",
            "price": f"₹{1000 + i}.00",
            "rating": 4.5,
            "product_url": f"https://www.amazon.in/dp/B08TEST{i}",
        }
        for i in range(5)
    ]

    # Configure page behavior for product search
    browser_manager.page.content = AsyncMock(
        return_value="<html><body><div class='s-result-item'>Product Results</div></body></html>"
    )

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.ok = True
    browser_manager.page.goto = AsyncMock(return_value=mock_response)

    # Mock product elements
    mock_elements = []
    for i in range(5):
        mock_element = AsyncMock()
        mock_element.get_attribute = AsyncMock(return_value=f"B08TEST{i}")
        mock_element.inner_text = AsyncMock(return_value=f"Test Product {i}")
        mock_elements.append(mock_element)
    browser_manager.page.query_selector_all = AsyncMock(return_value=mock_elements)

    # Mock selector methods
    browser_manager.selector = ResilientSelector(browser_manager.page)
    browser_manager.selector.extract_text = AsyncMock(
        side_effect=lambda *args, **kwargs: (
            "Test Product"
            if "title" in str(args)
            else "₹1000.00" if "price" in str(args) else "4.5 out of 5 stars"
        )
    )
    browser_manager.selector.select_element = AsyncMock(
        return_value=AsyncMock(
            inner_text=AsyncMock(return_value="Test Text"),
            get_attribute=AsyncMock(return_value="test-value"),
        )
    )

    # Execute search
    result = await search_amazon_products(query=TEST_SEARCH_QUERY, max_results=5)

    assert result["status"] == "success"
    assert "products" in result
    assert len(result["products"]) == 5
    assert result["products"][0]["asin"] == "B08TEST0"


@pytest.mark.asyncio
async def test_get_product_details_success(browser_manager):
    """Test successful product details retrieval"""
    # Mock product page content
    browser_manager.page.content = AsyncMock(
        return_value="<html><body><div id='productTitle'>Test Product</div></body></html>"
    )

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.ok = True
    browser_manager.page.goto = AsyncMock(return_value=mock_response)

    # Mock selector methods
    browser_manager.selector = ResilientSelector(browser_manager.page)
    browser_manager.selector.extract_text = AsyncMock(
        side_effect=lambda *args, **kwargs: {
            "title": "Test Product",
            "price": "₹999.00",
            "rating": "4.5 out of 5 stars",
            "description": "Product Description",
        }.get(str(args[0]), "Test Text")
    )
    browser_manager.selector.extract_images = AsyncMock(
        return_value=[
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
        ]
    )

    # Execute product details retrieval
    result = await get_product_details(TEST_ASIN)

    assert result["status"] == "success"
    assert result["asin"] == TEST_ASIN
    assert "product" in result
    assert result["product"]["title"] == "Test Product"


@pytest.mark.asyncio
async def test_get_product_reviews_success(browser_manager):
    """Test successful product reviews retrieval"""
    # Mock reviews page content
    browser_manager.page.content = AsyncMock(
        return_value="<html><body><div class='review'>Test Review</div></body></html>"
    )

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.ok = True
    browser_manager.page.goto = AsyncMock(return_value=mock_response)

    # Mock review elements
    mock_reviews = []
    for i in range(5):
        mock_review = AsyncMock()
        mock_review.get_attribute = AsyncMock(return_value=f"review{i}")
        mock_review.inner_text = AsyncMock(return_value=f"Review {i}")
        mock_reviews.append(mock_review)
    browser_manager.page.query_selector_all = AsyncMock(return_value=mock_reviews)

    # Mock selector methods
    browser_manager.selector = ResilientSelector(browser_manager.page)
    browser_manager.selector.extract_text = AsyncMock(
        side_effect=lambda *args, **kwargs: {
            "reviewer": "Test Reviewer",
            "rating": "4.5 out of 5 stars",
            "title": "Great Product",
            "content": "This is a test review",
            "date": "Reviewed on January 1, 2024",
        }.get(str(args[0]), "Test Text")
    )

    # Execute reviews retrieval
    result = await get_product_reviews(TEST_ASIN)

    assert result["status"] == "success"
    assert result["asin"] == TEST_ASIN
    assert "reviews" in result
    assert len(result["reviews"]) > 0
    assert all(
        key in result["reviews"][0]
        for key in ["reviewer", "rating", "title", "content", "date"]
    )


@pytest.mark.asyncio
async def test_refine_search_success(browser_manager):
    """Test successful search refinement"""
    refinements = {
        "price_min": 1000,
        "price_max": 5000,
        "min_rating": 4,
        "category": "Electronics",
        "sort_by": "price-asc",
    }

    # Mock refined search page content
    browser_manager.page.content = AsyncMock(
        return_value="<html><body><div class='s-result-item'>Refined Results</div></body></html>"
    )

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.ok = True
    browser_manager.page.goto = AsyncMock(return_value=mock_response)

    # Mock product elements
    mock_elements = []
    for i in range(5):
        mock_element = AsyncMock()
        mock_element.get_attribute = AsyncMock(return_value=f"B08TEST{i}")
        mock_element.inner_text = AsyncMock(return_value=f"Refined Product {i}")
        mock_elements.append(mock_element)
    browser_manager.page.query_selector_all = AsyncMock(return_value=mock_elements)

    # Mock selector methods
    browser_manager.selector = ResilientSelector(browser_manager.page)
    browser_manager.selector.extract_text = AsyncMock(
        side_effect=lambda *args, **kwargs: {
            "title": "Refined Product",
            "price": "₹1500.00",
            "rating": "4.5 out of 5 stars",
        }.get(str(args[0]), "Test Text")
    )

    # Execute refined search
    result = await refine_search(TEST_SEARCH_QUERY, refinements)

    assert result["status"] == "success"
    assert "products" in result
    assert len(result["products"]) > 0
    assert all(
        key in result["products"][0]
        for key in ["asin", "title", "price", "rating", "product_url"]
    )


@pytest.mark.asyncio
async def test_search_products_browser_failure(browser_manager):
    """Test product search with browser initialization failure"""
    # Configure browser manager to fail
    browser_manager.create_browser_context = AsyncMock(return_value=False)

    results = await search_amazon_products(TEST_SEARCH_QUERY)
    assert isinstance(results, dict)
    assert results.get("status") == "error"
    assert "Failed to initialize browser" in results.get("message", "")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
