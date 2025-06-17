import asyncio
import json
import logging
import os
import sys
import time
import uuid
import random
import re
from pathlib import Path
from typing import Dict, Optional, List, Any
from urllib.parse import quote_plus, quote, urlencode

# Add the root directory to Python path for imports
root_dir = str(Path(__file__).resolve().parents[4])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import mcp.server.stdio
from app.jarvis.utils import load_environment
from app.config.logging_config import setup_cloud_logging

# Setup cloud logging
setup_cloud_logging()

# ADK Tool Imports
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type

# MCP Server Imports
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# Playwright imports
try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        ElementHandle,
        Route,
    )
except ImportError:
    logging.error(
        "Playwright not installed. Please run: pip install playwright && playwright install"
    )
    sys.exit(1)

# Load environment variables
load_environment()

# --- Logging Setup ---
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "mcp_server_activity.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w"),
    ],
)

# --- Amazon Configuration ---
AMAZON_BASE_URL = "https://www.amazon.in"
AMAZON_SEARCH_URL = "https://www.amazon.in/s"

# Anti-detection configuration
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Response size limits to prevent WebSocket issues
MAX_PRODUCTS_RESPONSE = 20
MAX_REVIEWS_RESPONSE = 10

# Request limits and delays
MAX_RETRIES = 3
RETRY_DELAY = 2
MIN_REQUEST_DELAY = 1.5
MAX_REQUEST_DELAY = 4.0


def random_delay():
    """Generate random delay between requests"""
    return random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY)


class ResilientSelector:
    """Implements multiple fallback strategies for element extraction with performance tracking"""

    def __init__(
        self, page: Page, logger: logging.Logger = logging.getLogger(__name__)
    ):
        self.page = page
        self.logger = logger
        self._success_patterns = {}  # Cache successful patterns
        self._strategy_stats = {}  # Track strategy performance

    async def select_element(
        self,
        strategies: List[Dict[str, str]],
        timeout: float = 10000,
        context: str = "",
    ) -> Optional[ElementHandle]:
        """
        Try multiple selection strategies until one succeeds
        Args:
            strategies: List of strategy dictionaries
            timeout: Total timeout across all strategies
            context: Context for logging and tracking
        """
        strategies = self._sort_strategies(strategies)
        start_time = asyncio.get_event_loop().time()

        for strategy in strategies:
            if (asyncio.get_event_loop().time() - start_time) > timeout / 1000:
                break

            try:
                element = await self._try_strategy(strategy)
                if element:
                    self._update_stats(strategy, context, True)
                    self.logger.debug(f"Success with {strategy} for {context}")
                    return element
                self._update_stats(strategy, context, False)
            except Exception as e:
                self.logger.debug(f"Strategy failed {strategy}: {str(e)}")
                self._update_stats(strategy, context, False)

        return None

    def _sort_strategies(
        self, strategies: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Prioritize strategies based on success rate and speed"""

        def strategy_score(strategy):
            stats = self._strategy_stats.get(
                str(strategy), {"success": 0, "attempts": 0, "avg_time": 1.0}
            )
            success_rate = stats["success"] / max(stats["attempts"], 1)
            return success_rate / stats["avg_time"]

        return sorted(strategies, key=strategy_score, reverse=True)

    async def _try_strategy(self, strategy: Dict[str, str]) -> Optional[ElementHandle]:
        """Execute a single selection strategy with timing"""
        start_time = asyncio.get_event_loop().time()

        try:
            if strategy["type"] == "css":
                element = await self.page.query_selector(strategy["selector"])
            elif strategy["type"] == "xpath":
                element = await self.page.query_selector(
                    f"xpath={strategy['selector']}"
                )
            elif strategy["type"] == "text":
                element = await self.page.query_selector(f"text={strategy['selector']}")
            elif strategy["type"] == "aria":
                element = await self.page.query_selector(
                    f'[aria-label*="{strategy["selector"]}"]'
                )
            elif strategy["type"] == "data-attr":
                for attr in strategy.get("attributes", []):
                    element = await self.page.query_selector(
                        f'[data-{attr}*="{strategy["selector"]}"]'
                    )
                    if element:
                        break
            else:
                return None

            return element
        finally:
            elapsed = asyncio.get_event_loop().time() - start_time
            self._update_timing(strategy, elapsed)

    def _update_stats(self, strategy: Dict[str, str], context: str, success: bool):
        """Update strategy performance statistics"""
        key = str(strategy)
        if key not in self._strategy_stats:
            self._strategy_stats[key] = {
                "success": 0,
                "attempts": 0,
                "avg_time": 0.0,
                "contexts": set(),
            }

        stats = self._strategy_stats[key]
        stats["attempts"] += 1
        if success:
            stats["success"] += 1
        stats["contexts"].add(context)

    def _update_timing(self, strategy: Dict[str, str], elapsed: float):
        """Update average execution time for strategy"""
        key = str(strategy)
        if key in self._strategy_stats:
            stats = self._strategy_stats[key]
            stats["avg_time"] = (stats["avg_time"] * stats["attempts"] + elapsed) / (
                stats["attempts"] + 1
            )

    async def extract_text(
        self, strategies: List[Dict], context: str = ""
    ) -> Optional[str]:
        """Extract text using multiple fallback strategies"""
        element = await self.select_element(strategies, context=context)
        if element:
            return await element.inner_text()
        return None

    async def extract_price(self) -> Optional[str]:
        """Extract price using multiple strategies"""
        strategies = [
            {"type": "css", "selector": ".a-price .a-offscreen"},
            {"type": "css", "selector": ".a-price-whole"},
            {"type": "css", "selector": "span[data-a-color='price']"},
            {"type": "aria", "selector": "price"},
            {
                "type": "data-attr",
                "selector": "price",
                "attributes": ["price", "amount", "value"],
            },
            {"type": "text-match", "selector": "₹"},  # Currency symbol match
        ]
        return await self.extract_text(strategies, "price")

    async def extract_title(self) -> Optional[str]:
        """Extract title using multiple strategies"""
        strategies = [
            {"type": "css", "selector": "#productTitle"},
            {"type": "css", "selector": "h1.product-title"},
            {"type": "css", "selector": "h2 a span"},
            {"type": "aria", "selector": "product name"},
            {"type": "css", "selector": "[data-cy='title-recipe']"},
            {"type": "css", "selector": ".product-name"},
        ]
        return await self.extract_text(strategies, "title")

    async def extract_rating(self) -> Optional[float]:
        """Extract rating using multiple strategies"""
        strategies = [
            {"type": "css", "selector": ".a-icon-alt"},
            {"type": "css", "selector": "[data-hook='rating-out-of-text']"},
            {"type": "aria", "selector": "rating"},
            {"type": "css", "selector": ".review-rating"},
            {
                "type": "data-attr",
                "selector": "rating",
                "attributes": ["rating", "stars"],
            },
        ]

        rating_text = await self.extract_text(strategies, "rating")
        if rating_text:
            match = re.search(r"(\d+\.?\d*)", rating_text)
            return float(match.group(1)) if match else None
        return None

    async def extract_description(self) -> Optional[str]:
        """Extract description using multiple strategies"""
        strategies = [
            {"type": "css", "selector": "#feature-bullets ul"},
            {"type": "css", "selector": "#productDescription"},
            {"type": "css", "selector": ".product-description"},
            {
                "type": "data-attr",
                "selector": "description",
                "attributes": ["description", "product-desc"],
            },
            {"type": "css", "selector": "[data-hook='product-description']"},
        ]
        return await self.extract_text(strategies, "description")

    async def extract_images(self, max_images: int = 5) -> List[str]:
        """Extract image URLs using multiple strategies"""
        strategies = [
            {"type": "css", "selector": "#imgTagWrapperId img"},
            {"type": "css", "selector": "#imageBlock img"},
            {"type": "css", "selector": ".product-image img"},
            {"type": "css", "selector": "[data-hook='product-image'] img"},
        ]

        images = []
        for strategy in strategies:
            try:
                elements = await self.page.query_selector_all(strategy["selector"])
                for element in elements[:max_images]:
                    src = await element.get_attribute("src")
                    if src and "https:" in src and src not in images:
                        images.append(src)
                if images:
                    break
            except Exception:
                continue

        return images[:max_images]


class AmazonBrowserManager:
    """Manages browser instances with advanced anti-detection measures and performance optimizations"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.selector = None
        self._viewport_sizes = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1440, "height": 900},
            {"width": 1536, "height": 864},
        ]

    async def create_browser_context(self) -> bool:
        """Create browser context with enhanced anti-detection measures"""
        try:
            # Initialize playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )

            # Create context with random viewport
            viewport = random.choice(self._viewport_sizes)
            self.context = await self.browser.new_context(
                viewport=viewport,
                user_agent=USER_AGENTS[random.randint(0, len(USER_AGENTS) - 1)],
                locale="en-US",
            )

            # Create page and set up behaviors
            self.page = await self.context.new_page()
            if not await self._setup_page_behaviors():
                await self._cleanup()
                return False

            # Initialize selector
            self.selector = ResilientSelector(self.page)
            return True

        except Exception as e:
            logging.error(f"Error creating browser context: {e}")
            await self._cleanup()
            return False

    async def _setup_page_behaviors(self) -> bool:
        """Configure page behaviors with proper error handling"""
        try:
            if not self.page:
                logging.error("Page is not initialized")
                return False

            # Set reasonable timeouts
            await self.page.set_default_navigation_timeout(30000)
            await self.page.set_default_timeout(30000)

            # Basic stealth setup
            await self.page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                """
            )

            # Define blocked resource types
            BLOCKED_RESOURCE_TYPES = [
                "image",
                "media",
                "font",
                "texttrack",
                "object",
                "beacon",
                "csp_report",
                "imageset",
            ]

            # Set up request interception
            async def handle_route(route):
                if any(
                    pattern in route.request.resource_type.lower()
                    for pattern in BLOCKED_RESOURCE_TYPES
                ):
                    await route.abort()
                else:
                    await route.continue_()

            await self.page.route("**/*", handle_route)

            return True

        except Exception as e:
            logging.error(f"Error in _setup_page_behaviors: {e}")
            return False

    async def navigate_to_url(self, url: str, wait_for: str = None) -> bool:
        """Navigate to URL with enhanced error handling"""
        if not self.page:
            logging.error("Page is not initialized")
            return False

        try:
            response = await self.page.goto(
                url, wait_until="networkidle", timeout=30000
            )
            if not response:
                logging.error("Navigation failed - no response")
                return False

            if response.status >= 400:
                logging.error(f"Navigation failed - status code {response.status}")
                return False

            if wait_for:
                try:
                    await self.page.wait_for_selector(wait_for, timeout=10000)
                except Exception as e:
                    logging.warning(f"Wait for selector failed: {str(e)}")
                    # Continue anyway as the page might still be usable

            return True

        except Exception as e:
            logging.error(f"Navigation error: {e}")
            return False

    async def close(self) -> None:
        """Close all resources"""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")


async def search_amazon_products(query: str, max_results: int = 10) -> Dict[str, Any]:
    """Search for products on Amazon"""
    try:
        browser_manager = AmazonBrowserManager()
        if not await browser_manager.create_browser_context():
            return {
                "status": "error",
                "message": "Failed to initialize browser",
                "query": query,
            }

        # Build search URL
        search_url = f"https://www.amazon.in/s?k={quote(query)}"

        # Navigate to search page
        if not await browser_manager.navigate_to_url(search_url):
            return {
                "status": "error",
                "message": "Failed to load search results",
                "query": query,
            }

        # Extract product information
        products = []
        product_elements = await browser_manager.page.query_selector_all(
            "div[data-asin]:not([data-asin=''])"
        )

        for element in product_elements[:max_results]:
            try:
                asin = await element.get_attribute("data-asin")
                if not asin:
                    continue

                title = await browser_manager.selector.extract_text(
                    element, "h2 a span"
                )
                price = await browser_manager.selector.extract_text(
                    element, ".a-price-whole"
                )
                rating = await browser_manager.selector.extract_text(
                    element, ".a-icon-star-small"
                )

                products.append(
                    {
                        "asin": asin,
                        "title": title,
                        "price": price,
                        "rating": rating,
                        "product_url": f"https://www.amazon.in/dp/{asin}",
                    }
                )

            except Exception as e:
                logging.warning(f"Error extracting product info: {e}")
                continue

        await browser_manager.close()

        return {
            "status": "success",
            "query": query,
            "products": products,
        }

    except Exception as e:
        logging.error(f"Error in search_amazon_products: {e}")
        return {
            "status": "error",
            "message": str(e),
            "query": query,
        }


async def get_product_details(asin: str) -> Dict[str, Any]:
    """Get detailed information about a specific product"""
    try:
        browser_manager = AmazonBrowserManager()
        if not await browser_manager.create_browser_context():
            return {
                "status": "error",
                "message": "Failed to initialize browser",
                "asin": asin,
            }

        # Navigate to product page
        product_url = f"https://www.amazon.in/dp/{asin}"
        if not await browser_manager.navigate_to_url(product_url):
            return {
                "status": "error",
                "message": "Failed to load product page",
                "asin": asin,
            }

        # Extract product information
        title = await browser_manager.selector.extract_text(None, "#productTitle")
        price = await browser_manager.selector.extract_text(None, ".a-price-whole")
        rating = await browser_manager.selector.extract_text(
            None, "#acrPopover .a-icon-alt"
        )
        description = await browser_manager.selector.extract_text(
            None, "#productDescription"
        )
        images = await browser_manager.selector.extract_images(
            None, "#imgTagWrapperId img"
        )

        await browser_manager.close()

        return {
            "status": "success",
            "asin": asin,
            "product": {
                "title": title,
                "price": price,
                "rating": rating,
                "description": description,
                "images": images,
            },
        }

    except Exception as e:
        logging.error(f"Error in get_product_details: {e}")
        return {
            "status": "error",
            "message": str(e),
            "asin": asin,
        }


async def get_product_reviews(asin: str, max_reviews: int = 10) -> Dict[str, Any]:
    """Get reviews for a specific product"""
    try:
        browser_manager = AmazonBrowserManager()
        if not await browser_manager.create_browser_context():
            return {
                "status": "error",
                "message": "Failed to initialize browser",
                "asin": asin,
            }

        # Navigate to reviews page
        reviews_url = f"https://www.amazon.in/product-reviews/{asin}"
        if not await browser_manager.navigate_to_url(reviews_url):
            return {
                "status": "error",
                "message": "Failed to load reviews page",
                "asin": asin,
            }

        # Extract review information
        reviews = []
        review_elements = await browser_manager.page.query_selector_all(
            "div[data-hook='review']"
        )

        for element in review_elements[:max_reviews]:
            try:
                reviewer = await browser_manager.selector.extract_text(
                    element, ".a-profile-name"
                )
                rating = await browser_manager.selector.extract_text(
                    element, ".review-rating"
                )
                title = await browser_manager.selector.extract_text(
                    element, "[data-hook='review-title']"
                )
                content = await browser_manager.selector.extract_text(
                    element, "[data-hook='review-body']"
                )
                date = await browser_manager.selector.extract_text(
                    element, "[data-hook='review-date']"
                )

                reviews.append(
                    {
                        "reviewer": reviewer,
                        "rating": rating,
                        "title": title,
                        "content": content,
                        "date": date,
                    }
                )

            except Exception as e:
                logging.warning(f"Error extracting review info: {e}")
                continue

        await browser_manager.close()

        return {
            "status": "success",
            "asin": asin,
            "reviews": reviews,
        }

    except Exception as e:
        logging.error(f"Error in get_product_reviews: {e}")
        return {
            "status": "error",
            "message": str(e),
            "asin": asin,
        }


async def refine_search(
    query: str,
    refinements: Dict[str, Any],
    max_results: int = 10,
) -> Dict[str, Any]:
    """Refine product search with filters"""
    try:
        browser_manager = AmazonBrowserManager()
        if not await browser_manager.create_browser_context():
            return {
                "status": "error",
                "message": "Failed to initialize browser",
                "query": query,
            }

        # Build refined search URL
        search_params = {
            "k": query,
        }

        if refinements.get("category"):
            search_params["i"] = refinements["category"]
        if refinements.get("sort_by"):
            search_params["s"] = refinements["sort_by"]
        if refinements.get("price_min") and refinements.get("price_max"):
            search_params["rh"] = (
                f"p_{refinements['price_min']}-{refinements['price_max']}"
            )

        search_url = f"https://www.amazon.in/s?{urlencode(search_params)}"

        # Navigate to refined search page
        if not await browser_manager.navigate_to_url(search_url):
            return {
                "status": "error",
                "message": "Failed to load search results",
                "query": query,
            }

        # Extract product information
        products = []
        product_elements = await browser_manager.page.query_selector_all(
            "div[data-asin]:not([data-asin=''])"
        )

        for element in product_elements[:max_results]:
            try:
                asin = await element.get_attribute("data-asin")
                if not asin:
                    continue

                title = await browser_manager.selector.extract_text(
                    element, "h2 a span"
                )
                price = await browser_manager.selector.extract_text(
                    element, ".a-price-whole"
                )
                rating = await browser_manager.selector.extract_text(
                    element, ".a-icon-star-small"
                )

                # Filter by minimum rating if specified
                if refinements.get("min_rating"):
                    try:
                        product_rating = float(rating.split(" ")[0])
                        if product_rating < refinements["min_rating"]:
                            continue
                    except (ValueError, IndexError):
                        continue

                products.append(
                    {
                        "asin": asin,
                        "title": title,
                        "price": price,
                        "rating": rating,
                        "product_url": f"https://www.amazon.in/dp/{asin}",
                    }
                )

            except Exception as e:
                logging.warning(f"Error extracting product info: {e}")
                continue

        await browser_manager.close()

        return {
            "status": "success",
            "query": query,
            "refinements": refinements,
            "products": products,
        }

    except Exception as e:
        logging.error(f"Error in refine_search: {e}")
        return {
            "status": "error",
            "message": str(e),
            "query": query,
        }


# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for Amazon...")
app = Server("amazon-mcp-server")

# Wrap Amazon utility functions as ADK FunctionTools
ADK_AMAZON_TOOLS = {
    "search_amazon_products": FunctionTool(func=search_amazon_products),
    "get_product_details": FunctionTool(func=get_product_details),
    "get_product_reviews": FunctionTool(func=get_product_reviews),
    "refine_search": FunctionTool(func=refine_search),
}


@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_AMAZON_TOOLS.items():
        if not adk_tool_instance.name:
            adk_tool_instance.name = tool_name

        mcp_tool_schema = adk_to_mcp_tool_type(adk_tool_instance)
        logging.info(
            f"MCP Server: Advertising tool: {mcp_tool_schema.name}, InputSchema: {mcp_tool_schema.inputSchema}"
        )
        mcp_tools_list.append(mcp_tool_schema)
    return mcp_tools_list


@app.call_tool()
async def call_mcp_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    """MCP handler to execute a tool call requested by an MCP client."""
    logging.info(
        f"MCP Server: Received call_tool request for '{name}' with args: {arguments}"
    )

    if name in ADK_AMAZON_TOOLS:
        adk_tool_instance = ADK_AMAZON_TOOLS[name]
        try:
            logging.info(
                f"MCP Server: Executing ADK tool '{name}' with arguments: {json.dumps(arguments, indent=2)}"
            )

            # Validate required arguments
            if name == "search_amazon_products":
                if "query" not in arguments:
                    error_msg = f"Missing required 'query' parameter for {name}"
                    logging.error(f"MCP Server: {error_msg}")
                    return [
                        mcp_types.TextContent(
                            type="text",
                            text=json.dumps({"status": "error", "message": error_msg}),
                        )
                    ]
            elif name in ["get_product_details", "get_product_reviews"]:
                if "asin" not in arguments:
                    error_msg = f"Missing required 'asin' parameter for {name}"
                    logging.error(f"MCP Server: {error_msg}")
                    return [
                        mcp_types.TextContent(
                            type="text",
                            text=json.dumps({"status": "error", "message": error_msg}),
                        )
                    ]
            elif name == "refine_search":
                missing_params = []
                if "original_query" not in arguments:
                    missing_params.append("original_query")
                if "refinements" not in arguments:
                    missing_params.append("refinements")

                if missing_params:
                    error_msg = f"Missing required parameters for {name}: {', '.join(missing_params)}"
                    logging.error(f"MCP Server: {error_msg}")
                    return [
                        mcp_types.TextContent(
                            type="text",
                            text=json.dumps({"status": "error", "message": error_msg}),
                        )
                    ]

            # Execute the tool
            adk_tool_response = await adk_tool_instance.run_async(
                args=arguments,
                tool_context=None,  # type: ignore
            )

            logging.info(
                f"MCP Server: ADK tool '{name}' executed successfully. Response type: {type(adk_tool_response)}"
            )

            # Ensure response is JSON serializable and check size
            try:
                response_text = json.dumps(adk_tool_response, indent=2)
                response_size = len(response_text)

                logging.info(f"MCP Server: Response size: {response_size} characters")

                # If response is too large, try to compress it
                if response_size > 500000:  # 500KB limit
                    logging.warning(
                        f"MCP Server: Large response detected ({response_size} chars), attempting compression"
                    )

                    # Try compact JSON without indentation
                    response_text = json.dumps(adk_tool_response)
                    response_size = len(response_text)

                    if response_size > 500000:
                        # If still too large, return summary only
                        if (
                            isinstance(adk_tool_response, dict)
                            and adk_tool_response.get("status") == "success"
                        ):
                            summary_response = {
                                "status": "success",
                                "message": adk_tool_response.get("message", ""),
                                "query": adk_tool_response.get("query", ""),
                                "asin": adk_tool_response.get("asin", ""),
                                "total_results": len(
                                    adk_tool_response.get("products", [])
                                ),
                                "note": "Full product list truncated due to size. Use get_product_details for specific products.",
                            }
                            response_text = json.dumps(summary_response, indent=2)
                            logging.info(
                                f"MCP Server: Response compressed to summary ({len(response_text)} chars)"
                            )

                return [mcp_types.TextContent(type="text", text=response_text)]

            except TypeError as e:
                logging.error(f"MCP Server: Error serializing response to JSON: {e}")
                return [
                    mcp_types.TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "status": "error",
                                "message": "Failed to serialize response",
                                "error": str(e),
                            }
                        ),
                    )
                ]

        except Exception as e:
            error_msg = f"Failed to execute tool '{name}': {str(e)}"
            logging.error(f"MCP Server: {error_msg}", exc_info=True)
            error_payload = {
                "status": "error",
                "message": error_msg,
                "error_type": type(e).__name__,
            }
            error_text = json.dumps(error_payload)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        error_msg = f"Tool '{name}' not implemented by this server."
        logging.warning(f"MCP Server: {error_msg}")
        error_payload = {"status": "error", "message": error_msg}
        error_text = json.dumps(error_payload)
        return [mcp_types.TextContent(type="text", text=error_text)]


# --- MCP Server Runner ---
async def run_mcp_stdio_server():
    """Runs the MCP server, listening for connections over standard input/output."""
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logging.info("MCP Stdio Server: Starting handshake with client...")
            await app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=app.name,
                    server_version="0.1.0",
                    capabilities=app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
            logging.info("MCP Stdio Server: Run loop finished or client disconnected.")
    except Exception as e:
        logging.error("MCP Stdio Server: Error during server execution", exc_info=True)
        raise


if __name__ == "__main__":
    # Configure more detailed logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE_PATH, mode="w"),
            logging.StreamHandler(sys.stdout),  # Also log to console
        ],
    )

    logging.info("Launching Amazon MCP Server via stdio...")
    try:
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        logging.info("\nMCP Server (stdio) stopped by user.")
    except Exception as e:
        logging.critical(
            f"MCP Server (stdio) encountered an unhandled error: {e}", exc_info=True
        )
    finally:
        logging.info("MCP Server (stdio) process exiting.")
