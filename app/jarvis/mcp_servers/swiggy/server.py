import asyncio
import json
import logging
import os
import sys
import requests
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, List
from urllib.parse import urlencode

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

# --- Swiggy API Configuration ---
SWIGGY_BASE_URL = "https://www.swiggy.com/dapi/restaurants/search/v3"
SWIGGY_MENU_URL = "https://www.swiggy.com/dapi/menu/pl"
SWIGGY_HOMEPAGE = "https://www.swiggy.com"

# Default coordinates (Pune, India)
DEFAULT_LAT = "18.52110"
DEFAULT_LNG = "73.85020"

# Maximum retries and retry delay
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Response size limits to prevent WebSocket issues
MAX_RESTAURANTS_RESPONSE = 20  # Limit to top 20 restaurants
MAX_DISHES_RESPONSE = 50  # Limit to top 50 dishes


class SwiggySessionManager:
    def __init__(self):
        self.session = requests.Session()
        # Use browser-like cookies (these can be updated periodically)
        self.cookies = {
            "__SW": "aojuUvU9qS_Zv_qWG7ZtzY-zRaip2y5J",
            "_device_id": str(uuid.uuid4()),  # Generate unique device ID
            "userLocation": f'{{"lat":"{DEFAULT_LAT}","lng":"{DEFAULT_LNG}","address":"","area":"","showUserDefaultAddressHint":false}}',
            "fontsLoaded": "1",
            "_gcl_au": "1.1.1738814332.1750095074",
            "_gid": f"GA1.2.{int(time.time() * 1000)}.{int(time.time())}",
            "_guest_tid": str(uuid.uuid4()),
            "_sid": str(uuid.uuid4()),
            "_ga": f"GA1.2.{int(time.time() * 1000)}.{int(time.time())}",
            "_gat_0": "1",
        }

        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8,en-US;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "__fetch_req__": "true",
            "sec-ch-ua": '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "Priority": "u=1, i",
        }

    def _get_api_headers(self, query: str) -> Dict[str, str]:
        """Get headers for API request"""
        return {
            **self.base_headers,
            "Referer": f"https://www.swiggy.com/search?query={query}",
            "Origin": SWIGGY_HOMEPAGE,
        }

    def _get_cookie_header(self) -> str:
        """Convert cookies dictionary to Cookie header string"""
        return "; ".join([f"{k}={v}" for k, v in self.cookies.items()])

    def initialize_session(self) -> bool:
        """Initialize session (cookies are already set in __init__)"""
        logging.info("Initializing Swiggy session...")

        try:
            # Log cookies being used
            logging.debug("Using cookies:")
            for name, value in self.cookies.items():
                logging.debug(f"  {name}: {value}")

            return True

        except Exception as e:
            logging.error(f"Error initializing session: {str(e)}", exc_info=True)
            return False

    def make_api_request(self, query: str, lat: str, lng: str) -> Optional[Dict]:
        """Make API request with retry logic"""
        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    logging.info(f"Retry attempt {attempt + 1}/{MAX_RETRIES}")
                    time.sleep(RETRY_DELAY)

                # Update userLocation cookie if different coordinates are provided
                if lat != DEFAULT_LAT or lng != DEFAULT_LNG:
                    self.cookies["userLocation"] = (
                        f'{{"lat":"{lat}","lng":"{lng}","address":"","area":"","showUserDefaultAddressHint":false}}'
                    )

                params = {
                    "lat": lat,
                    "lng": lng,
                    "str": query,
                    "trackingId": "undefined",
                    "submitAction": "ENTER",
                    "queryUniqueId": str(uuid.uuid4()),
                }

                response = requests.get(
                    SWIGGY_BASE_URL,
                    params=params,
                    headers=self._get_api_headers(query),
                    cookies=self.cookies,
                    timeout=10,
                )

                logging.info(f"API request status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()

                    # Check for API-level error
                    if data.get("statusCode") != 0:
                        error_msg = data.get("statusMessage", "Unknown error")
                        logging.error(f"API error: {error_msg}")
                        return {
                            "status": "error",
                            "message": error_msg,
                            "debug_info": {
                                "status_code": data.get("statusCode"),
                                "status_message": error_msg,
                                "sid": data.get("sid"),
                                "tid": data.get("tid"),
                                "device_id": data.get("deviceId"),
                            },
                        }

                    return data

                logging.error(
                    f"Request failed with status code: {response.status_code}"
                )
                logging.error(f"Response text: {response.text[:500]}")

            except Exception as e:
                logging.error(f"Request error: {str(e)}", exc_info=True)

        return None

    def make_menu_api_request(
        self, restaurant_id: str, lat: str, lng: str
    ) -> Optional[Dict]:
        """Make API request for restaurant menu with retry logic"""
        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    logging.info(f"Retry attempt {attempt + 1}/{MAX_RETRIES}")
                    time.sleep(RETRY_DELAY)

                # Update userLocation cookie if different coordinates are provided
                if lat != DEFAULT_LAT or lng != DEFAULT_LNG:
                    self.cookies["userLocation"] = (
                        f'{{"lat":"{lat}","lng":"{lng}","address":"","area":"","showUserDefaultAddressHint":false}}'
                    )

                params = {
                    "page-type": "REGULAR_MENU",
                    "complete-menu": "true",
                    "lat": lat,
                    "lng": lng,
                    "restaurantId": restaurant_id,
                    "catalog_qa": "undefined",
                    "submitAction": "ENTER",
                }

                response = requests.get(
                    SWIGGY_MENU_URL,
                    params=params,
                    headers={
                        **self.base_headers,
                        "Referer": f"https://www.swiggy.com/restaurants/-/{restaurant_id}",
                        "Origin": SWIGGY_HOMEPAGE,
                    },
                    cookies=self.cookies,
                    timeout=10,
                )

                logging.info(f"Menu API request status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()

                    # Check for API-level error
                    if data.get("statusCode") != 0:
                        error_msg = data.get("statusMessage", "Unknown error")
                        logging.error(f"Menu API error: {error_msg}")
                        return {
                            "status": "error",
                            "message": error_msg,
                            "debug_info": {
                                "status_code": data.get("statusCode"),
                                "status_message": error_msg,
                                "sid": data.get("sid"),
                                "tid": data.get("tid"),
                                "device_id": data.get("deviceId"),
                            },
                        }

                    return data

                logging.error(
                    f"Menu request failed with status code: {response.status_code}"
                )
                logging.error(f"Response text: {response.text[:500]}")

            except Exception as e:
                logging.error(f"Menu request error: {str(e)}", exc_info=True)

        return None


def extract_restaurant_details(
    data: Dict, limit: int = MAX_RESTAURANTS_RESPONSE
) -> List[Dict]:
    """Extract dish and restaurant details from API response with size limit"""
    results = []

    try:
        # 1. Navigate to the cards list
        cards = data.get("data", {}).get("cards", [])
        if len(cards) < 2:
            return []

        # Get the DISH cards
        grouped_card = cards[1].get("groupedCard", {})
        card_group_map = grouped_card.get("cardGroupMap", {})
        dish_cards = card_group_map.get("DISH", {}).get("cards", [])

        # 2. Iterate through cards and filter by type
        for card in dish_cards:
            # Stop if we've reached the limit
            if len(results) >= limit:
                break

            card_data = card.get("card", {}).get("card", {})
            if not card_data:
                continue

            # Filter items by type
            if (
                card_data.get("@type")
                == "type.googleapis.com/swiggy.presentation.food.v2.Dish"
            ):
                try:
                    # 3. Extract all required fields
                    info = card_data.get("info", {})
                    restaurant = card_data.get("restaurant", {}).get("info", {})
                    ratings = info.get("ratings", {}).get("aggregatedRating", {})

                    result = {
                        # Food details
                        "food_id": info.get("id"),
                        "food_name": info.get("name"),
                        "original_price": info.get("price"),
                        "offer_price": info.get("finalPrice"),
                        "food_rating": ratings.get("rating"),
                        # Restaurant details
                        "restaurant_id": restaurant.get("id"),
                        "restaurant_name": restaurant.get("name"),
                        "delivery_time": restaurant.get("sla", {}).get("deliveryTime"),
                        "restaurant_rating": restaurant.get("avgRating"),
                    }

                    # Only add if we have at least the essential IDs
                    if result["food_id"] and result["restaurant_id"]:
                        results.append(result)

                except Exception as e:
                    logging.warning(f"Error processing individual card: {str(e)}")
                    continue

    except Exception as e:
        logging.error(f"Error extracting dish and restaurant details: {str(e)}")

    return results


def extract_dish_data(data: Dict, limit: int = MAX_DISHES_RESPONSE) -> List[Dict]:
    """Extract dish data from the API response with size limit"""
    try:
        cards = data.get("data", {}).get("cards", [])
        if len(cards) < 2:
            return []

        grouped_card = cards[1].get("groupedCard", {})
        card_group_map = grouped_card.get("cardGroupMap", {})
        dish_cards = card_group_map.get("DISH", {}).get("cards", [])

        dishes = []
        count = 0

        for card in dish_cards:
            if count >= limit:
                break

            if card.get("card", {}).get("card", {}):
                dish_data = card["card"]["card"]
                dish_type = dish_data.get("@type", "")

                # Only include actual dish data, not filter widgets
                if dish_type == "type.googleapis.com/swiggy.presentation.food.v2.Dish":
                    # Create a simplified dish object
                    simplified_dish = {
                        "@type": dish_type,
                        "info": dish_data.get("info", {}),
                        "restaurant": {
                            "info": dish_data.get("restaurant", {}).get("info", {})
                        },
                    }
                    dishes.append(simplified_dish)
                    count += 1

        return dishes
    except Exception as e:
        logging.error(f"Error extracting dish data: {e}")
        return []


def search_food(
    query: str,
    latitude: str = DEFAULT_LAT,
    longitude: str = DEFAULT_LNG,
) -> Dict:
    """
    Search for food options on Swiggy.

    Args:
        query (str): Food item to search for (e.g., "biryani", "pizza", "burger")
        latitude (str): Latitude coordinate for location (defaults to Pune)
        longitude (str): Longitude coordinate for location (defaults to Pune)

    Returns:
        dict: Search results from Swiggy API with dish and restaurant details
    """
    logging.info(f"Searching for food: {query} at location: {latitude}, {longitude}")

    # Create session manager
    session_mgr = SwiggySessionManager()

    try:
        # Initialize session
        if not session_mgr.initialize_session():
            return {
                "status": "error",
                "message": "Failed to initialize session",
                "query": query,
            }

        # Make API request
        result = session_mgr.make_api_request(query, latitude, longitude)

        if result is None:
            return {
                "status": "error",
                "message": "Failed to get response after retries",
                "query": query,
            }

        if result.get("status") == "error":
            return result

        # Extract dish and restaurant data with size limit
        items = extract_restaurant_details(result, limit=MAX_RESTAURANTS_RESPONSE)

        response = {
            "status": "success",
            "message": f"Found {len(items)} food items matching '{query}'"
            + (
                f" (limited to top {MAX_RESTAURANTS_RESPONSE})"
                if len(items) == MAX_RESTAURANTS_RESPONSE
                else ""
            ),
            "query": query,
            "location": f"{latitude}, {longitude}",
            "total_items": len(items),
            "items": items,
        }

        # Monitor response size
        response_size = len(json.dumps(response))
        logging.info(f"Response size: {response_size} characters")

        return response

    except Exception as e:
        error_msg = f"Error searching for food: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg, "query": query}
    finally:
        # Clean up the session
        session_mgr.session.close()


def extract_menu_categories(data: Dict) -> List[Dict]:
    """Extract menu categories from restaurant menu API response"""
    categories = []

    try:
        # Navigate to the menu cards
        cards = data.get("data", {}).get("cards", [])
        if len(cards) < 5:
            return []

        # Get the REGULAR cards
        grouped_card = cards[4].get("groupedCard", {})
        card_group_map = grouped_card.get("cardGroupMap", {})
        regular_cards = card_group_map.get("REGULAR", {}).get("cards", [])

        for card in regular_cards:
            card_data = card.get("card", {}).get("card", {})
            if not card_data:
                continue

            # Filter by type
            card_type = card_data.get("@type")
            if card_type in [
                "type.googleapis.com/swiggy.presentation.food.v2.MenuCarousel",
                "type.googleapis.com/swiggy.presentation.food.v2.ItemCategory",
            ]:
                category_title = card_data.get("title")
                if category_title:
                    categories.append(
                        {
                            "title": category_title,
                            "type": card_type,
                            "item_count": len(card_data.get("itemCards", [])),
                        }
                    )

    except Exception as e:
        logging.error(f"Error extracting menu categories: {str(e)}")

    return categories


def extract_menu_items_from_category(data: Dict, category_name: str) -> List[Dict]:
    """Extract menu items from a specific category"""
    items = []

    try:
        # Navigate to the menu cards
        cards = data.get("data", {}).get("cards", [])
        if len(cards) < 5:
            return []

        # Get the REGULAR cards
        grouped_card = cards[4].get("groupedCard", {})
        card_group_map = grouped_card.get("cardGroupMap", {})
        regular_cards = card_group_map.get("REGULAR", {}).get("cards", [])

        for card in regular_cards:
            card_data = card.get("card", {}).get("card", {})
            if not card_data:
                continue

            # Check if this is the category we're looking for
            card_type = card_data.get("@type")
            category_title = card_data.get("title")

            if (
                card_type
                in [
                    "type.googleapis.com/swiggy.presentation.food.v2.MenuCarousel",
                    "type.googleapis.com/swiggy.presentation.food.v2.ItemCategory",
                ]
                and category_title
                and category_title.lower() == category_name.lower()
            ):

                # Extract items from this category
                item_cards = card_data.get("itemCards", [])
                for item_card in item_cards:
                    item_info = item_card.get("card", {}).get("info", {})
                    if item_info:
                        # Extract prices using correct field names as specified
                        offer_price = item_info.get("finalPrice")  # Offer price
                        original_price = item_info.get("defaultPrice")  # Original price

                        # Convert from paise to rupees if available
                        offer_price_rupees = (
                            (offer_price / 100) if offer_price else None
                        )
                        original_price_rupees = (
                            (original_price / 100) if original_price else None
                        )

                        # Use offer price if available, otherwise original price
                        display_price = (
                            offer_price_rupees
                            if offer_price_rupees
                            else original_price_rupees
                        )

                        # Check for variants with different prices
                        variants_info = []
                        variants = item_info.get("variants", {}).get(
                            "variantGroups", []
                        )
                        for variant_group in variants:
                            group_name = variant_group.get("name", "")
                            variations = variant_group.get("variations", [])
                            for variation in variations:
                                var_name = variation.get("name", "")
                                var_price = variation.get("price")
                                var_price_rupees = (
                                    (var_price / 100) if var_price else None
                                )
                                is_default = variation.get("default", 0) == 1

                                variants_info.append(
                                    {
                                        "group": group_name,
                                        "name": var_name,
                                        "price": var_price_rupees,
                                        "is_default": is_default,
                                        "in_stock": variation.get("inStock", 0) == 1,
                                    }
                                )

                        # Get ratings
                        ratings = item_info.get("ratings", {}).get(
                            "aggregatedRating", {}
                        )
                        rating_value = ratings.get("rating")
                        rating_count = ratings.get("ratingCount", "")

                        item_data = {
                            "food_id": item_info.get("id"),
                            "food_name": item_info.get("name"),
                            "description": item_info.get("description", ""),
                            "category": category_title,
                            "offer_price": offer_price_rupees,
                            "original_price": original_price_rupees,
                            "display_price": display_price,
                            "variants": variants_info if variants_info else None,
                            "in_stock": item_info.get("inStock", 0) == 1,
                            "is_bestseller": item_info.get("isBestseller", False),
                            "veg_classifier": item_info.get("itemAttribute", {}).get(
                                "vegClassifier", ""
                            ),
                            "rating": rating_value,
                            "rating_count": rating_count,
                            "image_id": item_info.get("imageId"),
                        }

                        items.append(item_data)
                break

    except Exception as e:
        logging.error(f"Error extracting menu items from category: {str(e)}")

    return items


def get_restaurant_top_picks(
    restaurant_id: str,
    latitude: str = DEFAULT_LAT,
    longitude: str = DEFAULT_LNG,
) -> Dict:
    """
    Get top picks menu options for a particular restaurant.

    Args:
        restaurant_id (str): Swiggy restaurant ID
        latitude (str): Latitude coordinate for location (defaults to Pune)
        longitude (str): Longitude coordinate for location (defaults to Pune)

    Returns:
        dict: Top picks menu items from the restaurant
    """
    logging.info(
        f"Getting top picks for restaurant: {restaurant_id} at location: {latitude}, {longitude}"
    )

    # Create session manager
    session_mgr = SwiggySessionManager()

    try:
        # Initialize session
        if not session_mgr.initialize_session():
            return {
                "status": "error",
                "message": "Failed to initialize session",
                "restaurant_id": restaurant_id,
            }

        # Make API request
        result = session_mgr.make_menu_api_request(restaurant_id, latitude, longitude)

        if result is None:
            return {
                "status": "error",
                "message": "Failed to get menu response after retries",
                "restaurant_id": restaurant_id,
            }

        if result.get("status") == "error":
            return result

        # Look for "Top Picks" or "Recommended" categories
        top_picks_items = []
        recommended_items = []

        top_picks_items = extract_menu_items_from_category(result, "Top Picks")
        if not top_picks_items:
            recommended_items = extract_menu_items_from_category(result, "Recommended")

        items = top_picks_items if top_picks_items else recommended_items
        category_name = "Top Picks" if top_picks_items else "Recommended"

        if not items:
            return {
                "status": "success",
                "message": "No top picks or recommended items found for this restaurant",
                "restaurant_id": restaurant_id,
                "location": f"{latitude}, {longitude}",
                "items": [],
            }

        response = {
            "status": "success",
            "message": f"Found {len(items)} items in {category_name} for restaurant",
            "restaurant_id": restaurant_id,
            "location": f"{latitude}, {longitude}",
            "category": category_name,
            "total_items": len(items),
            "items": items,
        }

        return response

    except Exception as e:
        error_msg = f"Error getting top picks for restaurant: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg, "restaurant_id": restaurant_id}
    finally:
        # Clean up the session
        session_mgr.session.close()


def get_restaurant_menu_categories(
    restaurant_id: str,
    latitude: str = DEFAULT_LAT,
    longitude: str = DEFAULT_LNG,
) -> Dict:
    """
    Get all menu categories for a restaurant.

    Args:
        restaurant_id (str): Swiggy restaurant ID
        latitude (str): Latitude coordinate for location (defaults to Pune)
        longitude (str): Longitude coordinate for location (defaults to Pune)

    Returns:
        dict: List of menu categories for the restaurant
    """
    logging.info(
        f"Getting menu categories for restaurant: {restaurant_id} at location: {latitude}, {longitude}"
    )

    # Create session manager
    session_mgr = SwiggySessionManager()

    try:
        # Initialize session
        if not session_mgr.initialize_session():
            return {
                "status": "error",
                "message": "Failed to initialize session",
                "restaurant_id": restaurant_id,
            }

        # Make API request
        result = session_mgr.make_menu_api_request(restaurant_id, latitude, longitude)

        if result is None:
            return {
                "status": "error",
                "message": "Failed to get menu response after retries",
                "restaurant_id": restaurant_id,
            }

        if result.get("status") == "error":
            return result

        # Extract menu categories
        categories = extract_menu_categories(result)

        response = {
            "status": "success",
            "message": f"Found {len(categories)} menu categories for restaurant",
            "restaurant_id": restaurant_id,
            "location": f"{latitude}, {longitude}",
            "total_categories": len(categories),
            "categories": categories,
        }

        return response

    except Exception as e:
        error_msg = f"Error getting menu categories for restaurant: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return {"status": "error", "message": error_msg, "restaurant_id": restaurant_id}
    finally:
        # Clean up the session
        session_mgr.session.close()


def get_restaurant_menu_items(
    restaurant_id: str,
    category_name: str,
    latitude: str = DEFAULT_LAT,
    longitude: str = DEFAULT_LNG,
) -> Dict:
    """
    Get menu items for a specific menu category from a restaurant.

    Args:
        restaurant_id (str): Swiggy restaurant ID
        category_name (str): Name of the menu category (e.g., "Biryani", "Chinese", etc.)
        latitude (str): Latitude coordinate for location (defaults to Pune)
        longitude (str): Longitude coordinate for location (defaults to Pune)

    Returns:
        dict: Menu items for the specified category
    """
    logging.info(
        f"Getting menu items for category '{category_name}' from restaurant: {restaurant_id} at location: {latitude}, {longitude}"
    )

    # Create session manager
    session_mgr = SwiggySessionManager()

    try:
        # Initialize session
        if not session_mgr.initialize_session():
            return {
                "status": "error",
                "message": "Failed to initialize session",
                "restaurant_id": restaurant_id,
                "category": category_name,
            }

        # Make API request
        result = session_mgr.make_menu_api_request(restaurant_id, latitude, longitude)

        if result is None:
            return {
                "status": "error",
                "message": "Failed to get menu response after retries",
                "restaurant_id": restaurant_id,
                "category": category_name,
            }

        if result.get("status") == "error":
            return result

        # Extract menu items from the specific category
        items = extract_menu_items_from_category(result, category_name)

        if not items:
            # If no items found, list available categories
            categories = extract_menu_categories(result)
            available_categories = [cat["title"] for cat in categories]

            return {
                "status": "error",
                "message": f"Category '{category_name}' not found",
                "restaurant_id": restaurant_id,
                "category": category_name,
                "available_categories": available_categories,
            }

        response = {
            "status": "success",
            "message": f"Found {len(items)} items in category '{category_name}'",
            "restaurant_id": restaurant_id,
            "location": f"{latitude}, {longitude}",
            "category": category_name,
            "total_items": len(items),
            "items": items,
        }

        return response

    except Exception as e:
        error_msg = f"Error getting menu items for category: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return {
            "status": "error",
            "message": error_msg,
            "restaurant_id": restaurant_id,
            "category": category_name,
        }
    finally:
        # Clean up the session
        session_mgr.session.close()


# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for Swiggy...")
app = Server("swiggy-mcp-server")

# Wrap Swiggy utility functions as ADK FunctionTools
ADK_SWIGGY_TOOLS = {
    "search_food": FunctionTool(func=search_food),
    "get_restaurant_top_picks": FunctionTool(func=get_restaurant_top_picks),
    "get_restaurant_menu_categories": FunctionTool(func=get_restaurant_menu_categories),
    "get_restaurant_menu_items": FunctionTool(func=get_restaurant_menu_items),
}


@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_SWIGGY_TOOLS.items():
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

    if name in ADK_SWIGGY_TOOLS:
        adk_tool_instance = ADK_SWIGGY_TOOLS[name]
        try:
            logging.info(
                f"MCP Server: Executing ADK tool '{name}' with arguments: {json.dumps(arguments, indent=2)}"
            )

            # Validate required arguments
            if name in ["search_food"]:
                if "query" not in arguments:
                    error_msg = f"Missing required 'query' parameter for {name}"
                    logging.error(f"MCP Server: {error_msg}")
                    return [
                        mcp_types.TextContent(
                            type="text",
                            text=json.dumps({"status": "error", "message": error_msg}),
                        )
                    ]
            elif name in ["get_restaurant_top_picks", "get_restaurant_menu_categories"]:
                if "restaurant_id" not in arguments:
                    error_msg = f"Missing required 'restaurant_id' parameter for {name}"
                    logging.error(f"MCP Server: {error_msg}")
                    return [
                        mcp_types.TextContent(
                            type="text",
                            text=json.dumps({"status": "error", "message": error_msg}),
                        )
                    ]
            elif name == "get_restaurant_menu_items":
                missing_params = []
                if "restaurant_id" not in arguments:
                    missing_params.append("restaurant_id")
                if "category_name" not in arguments:
                    missing_params.append("category_name")

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
                                "location": adk_tool_response.get("location", ""),
                                "total_restaurants": adk_tool_response.get(
                                    "total_restaurants",
                                    adk_tool_response.get("restaurant_count", 0),
                                ),
                                "note": "Full restaurant list truncated due to size. Use search_restaurants for detailed results.",
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
                    server_version="0.3.1",
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

    logging.info("Launching Swiggy MCP Server via stdio...")
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
