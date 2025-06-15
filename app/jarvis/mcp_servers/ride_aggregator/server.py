#!/usr/bin/env python3
"""
Ride Aggregator MCP Server

This server provides tools for ride booking operations through multiple providers (Uber, Ola),
allowing the agent to compare and book rides.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

# Add the root directory to Python path for imports
root_dir = str(Path(__file__).resolve().parents[4])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import mcp.server.stdio
from app.config.logging_config import setup_cloud_logging
from dotenv import load_dotenv

# ADK Tool Imports
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type
from google.genai.types import Schema, Type

# MCP Server Imports
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# Setup cloud logging
setup_cloud_logging()

# Load environment variables
load_dotenv()

# --- Logging Setup ---
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "mcp_server_activity.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w"),
    ],
)

logger = logging.getLogger("ride-aggregator-server")

# Create the server instance
app = Server("ride-aggregator-mcp-server")

# Initialize services with error handling
uber_service = None
ola_service = None

try:
    from app.jarvis.mcp_servers.ride_aggregator.auth.uber_auth import UberAuthManager
    from app.jarvis.mcp_servers.ride_aggregator.services.uber_service import UberService
    
    # Initialize Uber service
    uber_client_id = os.getenv("UBER_CLIENT_ID")
    uber_client_secret = os.getenv("UBER_CLIENT_SECRET")
    uber_server_token = os.getenv("UBER_SERVER_TOKEN")
    
    if uber_client_id and uber_client_secret and uber_server_token:
        uber_auth = UberAuthManager(
            client_id=uber_client_id,
            client_secret=uber_client_secret,
            server_token=uber_server_token
        )
        uber_service = UberService(uber_auth)
        logger.info("✅ Uber service initialized successfully")
    else:
        missing = []
        if not uber_client_id:
            missing.append("UBER_CLIENT_ID")
        if not uber_client_secret:
            missing.append("UBER_CLIENT_SECRET")
        if not uber_server_token:
            missing.append("UBER_SERVER_TOKEN")
        logger.warning(f"⚠️ Uber credentials not found in environment: missing {', '.join(missing)}")
except Exception as e:
    logger.error(f"❌ Failed to initialize Uber service: {str(e)}")

try:
    from app.jarvis.mcp_servers.ride_aggregator.auth.ola_auth import OlaAuthManager
    from app.jarvis.mcp_servers.ride_aggregator.services.ola_service import OlaService
    
    # Initialize Ola service
    ola_app_token = os.getenv("OLA_APP_TOKEN")
    
    if ola_app_token:
        ola_auth = OlaAuthManager(app_token=ola_app_token)
        ola_service = OlaService(ola_auth)
        if ola_auth.is_authenticated():
            logger.info("✅ Ola service initialized successfully")
        else:
            logger.warning("⚠️ Ola service initialized but not authenticated")
    else:
        logger.warning("⚠️ Ola credentials not found in environment")
except Exception as e:
    logger.error(f"❌ Failed to initialize Ola service: {str(e)}")

async def check_auth_status() -> Dict[str, Dict[str, bool]]:
    """Check authentication status of ride services.
    
    Returns:
        Dict[str, Dict[str, bool]]: Status of each ride service with availability and auth status
    """
    return {
        "uber": {
            "available": uber_service is not None,
            "authenticated": uber_service is not None,
            "method": "client_credentials"
        },
        "ola": {
            "available": ola_service is not None,
            "authenticated": ola_service.auth_manager.is_authenticated() if ola_service else False,
            "method": "oauth_user_token"
        }
    }

async def get_uber_estimates(
    pickup_latitude: float,
    pickup_longitude: float,
    drop_latitude: float,
    drop_longitude: float
) -> Dict[str, Union[str, float, List[Dict[str, Any]]]]:
    """Get estimates from Uber
    
    Args:
        pickup_latitude (float): Pickup location latitude
        pickup_longitude (float): Pickup location longitude
        drop_latitude (float): Drop-off location latitude
        drop_longitude (float): Drop-off location longitude
    
    Returns:
        Dict[str, Union[str, float, List[Dict[str, Any]]]]: Uber price and time estimates
    """
    if not uber_service:
        return {"error": "Uber service not available"}
    
    try:
        results = {
            "provider": "uber",
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Get estimates in parallel
        price_estimate, time_estimate = await asyncio.gather(
            uber_service.get_price_estimates(
                pickup_latitude, pickup_longitude,
                drop_latitude, drop_longitude
            ),
            uber_service.get_time_estimates(
                pickup_latitude, pickup_longitude
            )
        )
        
        results.update({
            "price_estimates": price_estimate,
            "time_estimates": time_estimate
        })
        
        return results
    except Exception as e:
        logger.error(f"Error getting Uber estimates: {e}")
        return {"error": f"Failed to get Uber estimates: {str(e)}"}

async def get_ride_estimates(
    pickup_latitude: float,
    pickup_longitude: float,
    drop_latitude: float,
    drop_longitude: float
) -> Dict[str, Union[float, Dict[str, Any], List[str], List[Dict[str, Any]], Optional[Dict[str, Any]]]]:
    """Get estimates from all available providers
    
    Args:
        pickup_latitude (float): Pickup location latitude
        pickup_longitude (float): Pickup location longitude
        drop_latitude (float): Drop-off location latitude
        drop_longitude (float): Drop-off location longitude
    
    Returns:
        Dict containing estimates from all available providers
    """
    results = {
        "timestamp": asyncio.get_event_loop().time(),
        "providers": {},
        "available_providers": [],
        "comparison": [],
        "recommendation": None,
        "errors": []
    }
    
    # Get estimates from available providers
    if uber_service:
        uber_results = await get_uber_estimates(
            pickup_latitude, pickup_longitude,
            drop_latitude, drop_longitude
        )
        
        if "error" in uber_results:
            results["errors"].append({
                "provider": "uber",
                "error": uber_results["error"]
            })
        elif isinstance(uber_results.get("price_estimates"), list) and isinstance(uber_results.get("time_estimates"), list):
            results["providers"]["uber"] = uber_results
            results["available_providers"].append("uber")
            
            # Process valid estimates
            try:
                for price_estimate in uber_results["price_estimates"]:
                    if not isinstance(price_estimate, dict):
                        logger.error(f"Invalid price estimate format: {price_estimate}")
                        continue
                        
                    estimate_entry = {
                        "provider": "uber",
                        "service": price_estimate.get("display_name", "Unknown"),
                        "price_range": f"{price_estimate.get('low_estimate', 'N/A')}-{price_estimate.get('high_estimate', 'N/A')} {price_estimate.get('currency_code', 'USD')}",
                        "surge": price_estimate.get("surge_multiplier", 1.0),
                    }
                    
                    # Find matching time estimate
                    product_id = price_estimate.get("product_id")
                    if product_id:
                        matching_time = next(
                            (t.get("estimate") for t in uber_results["time_estimates"] 
                             if isinstance(t, dict) and t.get("product_id") == product_id),
                            None
                        )
                        estimate_entry["eta"] = matching_time
                    
                    results["comparison"].append(estimate_entry)
            except Exception as e:
                logger.error(f"Error processing Uber estimates: {e}")
                results["errors"].append({
                    "provider": "uber",
                    "error": f"Error processing estimates: {str(e)}"
                })
    
    # Make recommendations only if we have valid comparisons
    if results["comparison"]:
        try:
            # Find the option with lowest price (using the low end of the range)
            results["recommendation"] = min(
                results["comparison"],
                key=lambda x: float(x["price_range"].split("-")[0]) if isinstance(x["price_range"], str) and x["price_range"].split("-")[0] != "N/A" else float("inf")
            )
        except Exception as e:
            logger.error(f"Error determining recommendation: {e}")
            results["errors"].append({
                "error": f"Could not determine recommendation: {str(e)}"
            })
    
    return results

async def book_uber_ride(
    pickup_latitude: float,
    pickup_longitude: float,
    drop_latitude: float,
    drop_longitude: float,
    product_id: str,
    payment_method_id: Optional[str] = None,
    rider_name: Optional[str] = None,
    rider_phone: Optional[str] = None
) -> Dict[str, Union[str, Dict[str, Any], float]]:
    """Book a ride with Uber
    
    Args:
        pickup_latitude (float): Pickup location latitude
        pickup_longitude (float): Pickup location longitude
        drop_latitude (float): Drop-off location latitude
        drop_longitude (float): Drop-off location longitude
        product_id (str): Uber product/service ID to book
        payment_method_id (Optional[str], optional): Payment method ID to use. Defaults to None.
        rider_name (Optional[str], optional): Name of the rider. Defaults to None.
        rider_phone (Optional[str], optional): Phone number of the rider. Defaults to None.
    
    Returns:
        Dict[str, Union[str, Dict[str, Any], float]]: Booking details or error information
    """
    if not uber_service:
        return {"error": "Uber service not available"}
    
    try:
        # Filter out None values from optional parameters
        booking_args = {
            "product_id": product_id,
            "pickup_latitude": pickup_latitude,
            "pickup_longitude": pickup_longitude,
            "drop_latitude": drop_latitude,
            "drop_longitude": drop_longitude
        }
        
        if payment_method_id is not None:
            booking_args["payment_method_id"] = payment_method_id
        if rider_name is not None:
            booking_args["rider_name"] = rider_name
        if rider_phone is not None:
            booking_args["rider_phone"] = rider_phone

        booking = await uber_service.request_ride(**booking_args)
        return booking
    except Exception as e:
        logger.error(f"Error booking Uber ride: {e}")
        return {"error": f"Failed to book Uber ride: {str(e)}"}

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for Ride Aggregator...")
app = Server("ride-aggregator-mcp-server")

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    return [
        mcp_types.Tool(
            name="check_auth_status",
            description="Check authentication status of ride services",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        mcp_types.Tool(
            name="get_ride_estimates",
            description="Get ride estimates from all available providers",
            inputSchema={
                "type": "object",
                "properties": {
                    "pickup_latitude": {
                        "type": "number",
                        "description": "Pickup location latitude"
                    },
                    "pickup_longitude": {
                        "type": "number",
                        "description": "Pickup location longitude"
                    },
                    "drop_latitude": {
                        "type": "number",
                        "description": "Drop-off location latitude"
                    },
                    "drop_longitude": {
                        "type": "number",
                        "description": "Drop-off location longitude"
                    }
                },
                "required": ["pickup_latitude", "pickup_longitude", "drop_latitude", "drop_longitude"]
            }
        ),
        mcp_types.Tool(
            name="book_uber_ride",
            description="Book a ride with Uber",
            inputSchema={
                "type": "object",
                "properties": {
                    "pickup_latitude": {
                        "type": "number",
                        "description": "Pickup location latitude"
                    },
                    "pickup_longitude": {
                        "type": "number",
                        "description": "Pickup location longitude"
                    },
                    "drop_latitude": {
                        "type": "number",
                        "description": "Drop-off location latitude"
                    },
                    "drop_longitude": {
                        "type": "number",
                        "description": "Drop-off location longitude"
                    },
                    "product_id": {
                        "type": "string",
                        "description": "Uber product/service ID to book"
                    },
                    "payment_method_id": {
                        "type": ["string", "null"],
                        "description": "Payment method ID to use (optional)"
                    },
                    "rider_name": {
                        "type": ["string", "null"],
                        "description": "Name of the rider (optional)"
                    },
                    "rider_phone": {
                        "type": ["string", "null"],
                        "description": "Phone number of the rider (optional)"
                    }
                },
                "required": ["pickup_latitude", "pickup_longitude", "drop_latitude", "drop_longitude", "product_id"]
            }
        )
    ]

# Map tool names to their implementations
TOOL_IMPLEMENTATIONS = {
    "check_auth_status": check_auth_status,
    "get_ride_estimates": get_ride_estimates,
    "book_uber_ride": book_uber_ride,
}

@app.call_tool()
async def call_mcp_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    """MCP handler to execute a tool call requested by an MCP client."""
    logging.info(
        f"MCP Server: Received call_tool request for '{name}' with args: {arguments}"
    )

    if name in TOOL_IMPLEMENTATIONS:
        try:
            tool_func = TOOL_IMPLEMENTATIONS[name]
            tool_response = await tool_func(**arguments)
            logging.info(
                f"MCP Server: Tool '{name}' executed. Response: {tool_response}"
            )
            response_text = json.dumps(tool_response, indent=2)
            return [mcp_types.TextContent(type="text", text=response_text)]

        except Exception as e:
            logging.error(
                f"MCP Server: Error executing tool '{name}': {e}", exc_info=True
            )
            error_payload = {
                "success": False,
                "message": f"Failed to execute tool '{name}': {str(e)}",
            }
            error_text = json.dumps(error_payload)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        logging.warning(f"MCP Server: Tool '{name}' not found/exposed by this server.")
        error_payload = {
            "success": False,
            "message": f"Tool '{name}' not implemented by this server.",
        }
        error_text = json.dumps(error_payload)
        return [mcp_types.TextContent(type="text", text=error_text)]

async def run_mcp_stdio_server():
    """Runs the MCP server, listening for connections over standard input/output."""
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

if __name__ == "__main__":
    logging.info("Launching Ride Aggregator MCP Server via stdio...")
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