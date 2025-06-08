import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add the root directory to Python path for imports
root_dir = str(Path(__file__).resolve().parents[4])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import requests
import mcp.server.stdio
from google.adk.tools.function_tool import FunctionTool
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type

from app.jarvis.utils import load_environment
from app.config.logging_config import setup_cloud_logging

# Setup cloud logging
setup_cloud_logging()

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

# Get API key from environment
MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not MAPS_API_KEY:
    raise ValueError("GOOGLE_MAPS_API_KEY environment variable not set")

def calculate_distance(
    origins: List[str],
    destinations: List[str],
    mode: str = "driving",
    units: str = "metric",
    departure_time: str = "now",
    avoid: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Calculate distance and duration between origins and destinations using Google Maps Distance Matrix API.

    Args:
        origins (List[str]): List of origin addresses or coordinates
        destinations (List[str]): List of destination addresses or coordinates
        mode (str): Mode of transport (driving, walking, bicycling, transit)
        units (str): Unit system (metric or imperial)
        departure_time (str): Departure time (now or timestamp)
        avoid (List[str], optional): Features to avoid (tolls, highways, ferries)

    Returns:
        dict: Distance matrix results containing distances and durations
    """
    try:
        logging.info(f"Calculating distance between {origins} and {destinations}")
        
        # Build API URL
        base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        
        # Prepare parameters
        params = {
            "origins": "|".join(origins),
            "destinations": "|".join(destinations),
            "mode": mode,
            "units": units,
            "departure_time": departure_time,
            "key": MAPS_API_KEY
        }
        
        # Add avoid parameters if specified
        if avoid:
            params["avoid"] = "|".join(avoid)

        # Make API request
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        if data["status"] != "OK":
            return {
                "status": "error",
                "message": f"API Error: {data['status']}",
                "results": []
            }

        # Process results
        results = []
        for i, origin_row in enumerate(data["rows"]):
            origin = origins[i]
            for j, element in enumerate(origin_row["elements"]):
                destination = destinations[j]
                if element["status"] == "OK":
                    result = {
                        "origin": origin,
                        "destination": destination,
                        "distance": element["distance"]["text"],
                        "distance_meters": element["distance"]["value"],
                        "duration": element["duration"]["text"],
                        "duration_seconds": element["duration"]["value"]
                    }
                    
                    # Add traffic duration if available
                    if "duration_in_traffic" in element:
                        result["duration_in_traffic"] = element["duration_in_traffic"]["text"]
                        result["duration_in_traffic_seconds"] = element["duration_in_traffic"]["value"]
                    
                    results.append(result)
                else:
                    results.append({
                        "origin": origin,
                        "destination": destination,
                        "status": "error",
                        "message": f"Route calculation failed: {element['status']}"
                    })

        return {
            "status": "success",
            "message": f"Found {len(results)} route(s)",
            "results": results
        }

    except Exception as e:
        logging.error(f"Error calculating distance: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error calculating distance: {str(e)}",
            "results": []
        }

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for Google Maps...")
app = Server("maps-mcp-server")

# Wrap Maps utility functions as ADK FunctionTools
ADK_MAPS_TOOLS = {
    "calculate_distance": FunctionTool(func=calculate_distance),
}

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_MAPS_TOOLS.items():
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

    if name in ADK_MAPS_TOOLS:
        adk_tool_instance = ADK_MAPS_TOOLS[name]
        try:
            adk_tool_response = await adk_tool_instance.run_async(
                args=arguments,
                tool_context=None,  # type: ignore
            )
            logging.info(
                f"MCP Server: ADK tool '{name}' executed. Response: {adk_tool_response}"
            )
            response_text = json.dumps(adk_tool_response, indent=2)
            return [mcp_types.TextContent(type="text", text=response_text)]

        except Exception as e:
            logging.error(
                f"MCP Server: Error executing ADK tool '{name}': {e}", exc_info=True
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

# --- MCP Server Runner ---
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
    logging.info("Launching Google Maps MCP Server via stdio...")
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