import os
import sys
import json
import pytest
import asyncio
import logging
from typing import Dict, Any
from unittest.mock import Mock, patch
from pathlib import Path

# Add the root directory to Python path for imports
root_dir = str(Path(__file__).resolve().parents[1])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from mcp import types as mcp_types
from app.jarvis.mcp_servers.amazon.server import (
    app,
    ADK_AMAZON_TOOLS,
    search_amazon_products,
    get_product_details,
    get_product_reviews,
    refine_search,
    AmazonBrowserManager,
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Test configuration
TEST_SEARCH_QUERY = "laptop"
TEST_CATEGORY = "Electronics"
TEST_PRICE_MIN = 20000
TEST_PRICE_MAX = 100000
TEST_MIN_RATING = 4.0

# Skip tests if running in CI environment
skip_if_ci = pytest.mark.skipif(
    os.environ.get("CI") == "true", reason="Integration tests skipped in CI environment"
)


class MockReadStream:
    """Mock read stream for testing"""

    def __init__(self, messages):
        self.messages = messages
        self.index = 0

    async def read(self):
        if self.index < len(self.messages):
            message = self.messages[self.index]
            self.index += 1
            return message
        return None


class MockWriteStream:
    """Mock write stream for testing"""

    def __init__(self):
        self.written = []

    async def write(self, data):
        self.written.append(data)


@pytest.fixture
def mock_streams():
    """Fixture to create mock read and write streams"""
    test_messages = [
        json.dumps({"type": "list_tools_request", "id": "test-1"}).encode(),
        json.dumps(
            {
                "type": "call_tool_request",
                "id": "test-2",
                "name": "search_amazon_products",
                "arguments": {"query": "laptop", "max_results": 2},
            }
        ).encode(),
    ]
    read_stream = MockReadStream(test_messages)
    write_stream = MockWriteStream()
    return read_stream, write_stream


@pytest.mark.asyncio
async def test_list_tools():
    """Test listing available tools"""
    tools = await app.list_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0

    # Verify each tool has required fields
    for tool in tools:
        assert isinstance(tool, mcp_types.Tool)
        assert tool.name
        assert tool.inputSchema
        assert tool.outputSchema


@pytest.mark.asyncio
async def test_call_tool_search():
    """Test calling search_amazon_products tool"""
    result = await app.call_tool(
        "search_amazon_products", {"query": "laptop", "max_results": 2}
    )
    assert isinstance(result, list)
    assert len(result) > 0
    assert isinstance(result[0], mcp_types.TextContent)

    # Parse response JSON
    response = json.loads(result[0].text)
    assert "status" in response
    if response["status"] == "success":
        assert "products" in response
        assert isinstance(response["products"], list)


@pytest.mark.asyncio
async def test_call_tool_product_details():
    """Test calling get_product_details tool"""
    result = await app.call_tool("get_product_details", {"asin": "B08H8VZ6PV"})
    assert isinstance(result, list)
    assert len(result) > 0
    assert isinstance(result[0], mcp_types.TextContent)

    # Parse response JSON
    response = json.loads(result[0].text)
    assert "status" in response
    if response["status"] == "success":
        assert "product" in response
        assert isinstance(response["product"], dict)


@pytest.mark.asyncio
async def test_call_tool_invalid():
    """Test calling non-existent tool"""
    result = await app.call_tool("non_existent_tool", {})
    assert isinstance(result, list)
    assert len(result) > 0

    # Parse response JSON
    response = json.loads(result[0].text)
    assert response["status"] == "error"
    assert "not implemented" in response["message"].lower()


@pytest.mark.asyncio
async def test_call_tool_missing_args():
    """Test calling tool with missing arguments"""
    result = await app.call_tool(
        "search_amazon_products", {}  # Missing required 'query' parameter
    )
    assert isinstance(result, list)
    assert len(result) > 0

    # Parse response JSON
    response = json.loads(result[0].text)
    assert response["status"] == "error"
    assert "missing" in response["message"].lower()


@pytest.mark.asyncio
async def test_mcp_server_communication(mock_streams):
    """Test MCP server communication flow"""
    read_stream, write_stream = mock_streams

    # Initialize server with mock streams
    await app.run(read_stream, write_stream, app.get_initialization_options())

    # Verify responses
    assert len(write_stream.written) >= 2  # Should have at least 2 responses

    # Parse and verify list_tools response
    list_tools_response = json.loads(write_stream.written[0].decode())
    assert list_tools_response["type"] == "list_tools_response"
    assert "tools" in list_tools_response

    # Parse and verify call_tool response
    call_tool_response = json.loads(write_stream.written[1].decode())
    assert call_tool_response["type"] == "call_tool_response"
    assert "result" in call_tool_response


@pytest.mark.asyncio
async def test_tool_registration():
    """Test tool registration and availability"""
    for tool_name, tool_instance in ADK_AMAZON_TOOLS.items():
        assert hasattr(tool_instance, "run_async")
        assert callable(tool_instance.run_async)


@pytest.fixture(scope="module")
async def browser_manager():
    """Module-scoped fixture for browser manager to reuse across tests"""
    manager = AmazonBrowserManager()
    try:
        success = await manager.create_browser_context()
        if not success:
            pytest.skip("Failed to create browser context")
        yield manager
    finally:
        await manager.close()


@skip_if_ci
@pytest.mark.asyncio
async def test_search_flow():
    """Test complete search and refinement flow"""
    # Initial search
    result = await search_amazon_products(query=TEST_SEARCH_QUERY, max_results=5)
    assert result["status"] == "success"
    assert len(result["products"]) > 0

    # Store first product ASIN for later tests
    first_product_asin = result["products"][0]["asin"]

    # Refine search
    refinements = {
        "price_min": TEST_PRICE_MIN,
        "price_max": TEST_PRICE_MAX,
        "min_rating": TEST_MIN_RATING,
        "category": TEST_CATEGORY,
    }

    refined_result = await refine_search(TEST_SEARCH_QUERY, refinements)
    assert refined_result["status"] == "success"
    assert len(refined_result["products"]) > 0

    # Get details of first product
    details_result = await get_product_details(first_product_asin)
    assert details_result["status"] == "success"
    assert details_result["product"]["asin"] == first_product_asin

    # Get reviews
    reviews_result = await get_product_reviews(first_product_asin, max_reviews=3)
    assert reviews_result["status"] == "success"
    assert len(reviews_result["reviews"]) > 0


@skip_if_ci
@pytest.mark.asyncio
async def test_search_with_filters():
    """Test search with various filter combinations"""
    test_cases = [
        {
            "query": "smartphone",
            "price_min": 10000,
            "price_max": 50000,
            "min_rating": 4.0,
            "category": "Electronics",
        },
        {"query": "headphones", "price_max": 5000, "min_rating": 4.5},
        {"query": "smartwatch", "category": "Electronics", "sort_by": "price-asc"},
    ]

    for case in test_cases:
        result = await search_amazon_products(**case)
        assert result["status"] == "success"
        assert len(result["products"]) > 0

        # Verify price filters
        if "price_min" in case or "price_max" in case:
            for product in result["products"]:
                price_text = product["price"].replace("₹", "").replace(",", "")
                try:
                    price = float(price_text)
                    if "price_min" in case:
                        assert price >= case["price_min"]
                    if "price_max" in case:
                        assert price <= case["price_max"]
                except ValueError:
                    continue  # Skip if price cannot be parsed


@skip_if_ci
@pytest.mark.asyncio
async def test_product_details_variations():
    """Test product details retrieval for different types of products"""
    # Search for different product types
    product_searches = ["book", "electronics", "clothing"]

    for search in product_searches:
        # Get a product ASIN from search
        search_result = await search_amazon_products(search, max_results=1)
        assert search_result["status"] == "success"
        assert len(search_result["products"]) > 0

        asin = search_result["products"][0]["asin"]

        # Get details for the product
        details = await get_product_details(asin)
        assert details["status"] == "success"
        assert details["product"]["asin"] == asin

        # Verify product type specific fields
        product = details["product"]
        if search == "book":
            assert "author" in product or "brand" in product
        elif search == "electronics":
            assert "specifications" in product
        elif search == "clothing":
            assert "brand" in product


@skip_if_ci
@pytest.mark.asyncio
async def test_reviews_pagination():
    """Test review retrieval with different page sizes"""
    # First get a product with reviews
    search_result = await search_amazon_products(
        "popular laptop", max_results=1, min_rating=4.0
    )
    assert search_result["status"] == "success"
    assert len(search_result["products"]) > 0

    asin = search_result["products"][0]["asin"]

    # Test different review counts
    review_counts = [1, 5, 10]
    previous_count = 0

    for count in review_counts:
        result = await get_product_reviews(asin, max_reviews=count)
        assert result["status"] == "success"
        assert len(result["reviews"]) <= count
        assert len(result["reviews"]) >= previous_count
        previous_count = len(result["reviews"])


@skip_if_ci
@pytest.mark.asyncio
async def test_error_handling_integration():
    """Test error handling with invalid inputs in integration context"""
    # Test invalid ASIN
    result = await get_product_details("INVALID123")
    assert result["status"] == "error"

    # Test empty search query
    result = await search_amazon_products("")
    assert result["status"] == "error"

    # Test invalid price range
    result = await search_amazon_products(
        "test", price_min=1000, price_max=500  # Invalid: min > max
    )
    assert result["status"] == "error"

    # Test invalid category
    result = await search_amazon_products("test", category="InvalidCategory123")
    assert result["status"] in [
        "error",
        "success",
    ]  # Both are valid (Amazon might ignore invalid category)


@skip_if_ci
@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test handling of concurrent requests"""
    # Prepare multiple search queries
    queries = ["laptop", "smartphone", "headphones", "smartwatch", "tablet"]

    # Run searches concurrently
    tasks = [search_amazon_products(query, max_results=2) for query in queries]
    results = await asyncio.gather(*tasks)

    # Verify all searches completed successfully
    for result in results:
        assert result["status"] == "success"
        assert len(result["products"]) > 0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
