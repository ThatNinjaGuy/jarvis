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

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import mcp.server.stdio
from google.adk.tools.function_tool import FunctionTool, Schema, Field
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

# --- Spotify Client Setup ---
SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "streaming",
    "app-remote-control",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
    "user-read-private",
    "user-read-email"
]

# Path for token storage
TOKEN_PATH = Path(os.path.expanduser("~/.credentials/spotify_token.json"))

def get_spotify_client():
    """
    Create an authenticated Spotify client using environment variables.
    
    Returns:
        spotipy.Spotify: Authenticated Spotify client
    """
    try:
        auth_manager = SpotifyOAuth(
            scope=SCOPES,
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
            open_browser=True,
            cache_path=str(TOKEN_PATH)
        )
        client = spotipy.Spotify(auth_manager=auth_manager)
        logging.info("Successfully created Spotify client")
        return client
    except Exception as e:
        logging.error(f"Failed to create Spotify client: {e}", exc_info=True)
        return None

def search_spotify(
    query: str,
    search_type: str = "track",
    limit: int = 10
) -> dict:
    """
    Search Spotify for tracks, albums, artists, or playlists.

    Args:
        query (str): The search query to find music content
        search_type (str): Type of search - 'track', 'album', 'artist', or 'playlist'
        limit (int): Maximum number of results to return (default: 10)

    Returns:
        dict: Search results or error details
    """
    try:
        client = get_spotify_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to authenticate with Spotify",
                "data": None
            }

        # Validate search type
        valid_types = ["track", "album", "artist", "playlist"]
        if search_type not in valid_types:
            return {
                "status": "error",
                "message": f"Invalid search type. Must be one of: {', '.join(valid_types)}",
                "data": None
            }

        # Perform search
        results = client.search(q=query, type=search_type, limit=limit)
        
        # Format results based on type
        formatted_results = []
        result_key = f"{search_type}s"  # Spotify API returns results in plural form
        
        for item in results[result_key]["items"]:
            result = {
                "id": item["id"],
                "name": item["name"],
                "uri": item["uri"]
            }
            
            # Add type-specific information
            if search_type == "track":
                result.update({
                    "artist": item["artists"][0]["name"],
                    "album": item["album"]["name"],
                    "duration_ms": item["duration_ms"]
                })
            elif search_type == "album":
                result.update({
                    "artist": item["artists"][0]["name"],
                    "release_date": item["release_date"],
                    "total_tracks": item["total_tracks"]
                })
            elif search_type == "playlist":
                result.update({
                    "owner": item["owner"]["display_name"],
                    "tracks_total": item["tracks"]["total"]
                })
            
            formatted_results.append(result)

        return {
            "status": "success",
            "message": f"Found {len(formatted_results)} {search_type}(s)",
            "data": formatted_results
        }

    except Exception as e:
        logging.error(f"Error searching Spotify: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }

def get_playback_state() -> dict:
    """
    Get current playback state.

    Returns:
        dict: Current playback state information
    """
    try:
        client = get_spotify_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to authenticate with Spotify",
                "data": None
            }

        playback = client.current_playback()
        if not playback:
            return {
                "status": "success",
                "message": "No active playback session",
                "data": {"is_playing": False}
            }

        data = {
            "is_playing": playback["is_playing"],
            "device": {
                "id": playback["device"]["id"],
                "name": playback["device"]["name"],
                "type": playback["device"]["type"],
                "volume": playback["device"]["volume_percent"]
            }
        }

        if playback["item"]:
            data["current_track"] = {
                "name": playback["item"]["name"],
                "artist": playback["item"]["artists"][0]["name"],
                "album": playback["item"]["album"]["name"],
                "duration_ms": playback["item"]["duration_ms"],
                "progress_ms": playback["progress_ms"]
            }

        return {
            "status": "success",
            "message": "Retrieved playback state",
            "data": data
        }

    except Exception as e:
        logging.error(f"Error getting playback state: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }

def control_playback(
    action: str,
    position_ms: int = 0,
    volume: int = 50
) -> dict:
    """
    Control Spotify playback.

    Args:
        action (str): Action to perform - 'play', 'pause', 'next', 'previous', or 'seek'
        position_ms (int): Position to seek to in milliseconds (only for 'seek' action)
        volume (int): Volume level to set (0-100)

    Returns:
        dict: Operation status and details
    """
    try:
        client = get_spotify_client()
        if not client:
            return {
                "status": "error",
                "message": "Failed to authenticate with Spotify",
                "data": None
            }

        # Validate action
        valid_actions = ["play", "pause", "next", "previous", "seek"]
        if action not in valid_actions:
            return {
                "status": "error",
                "message": f"Invalid action. Must be one of: {', '.join(valid_actions)}",
                "data": None
            }

        # Execute action
        if action == "play":
            client.start_playback()
        elif action == "pause":
            client.pause_playback()
        elif action == "next":
            client.next_track()
        elif action == "previous":
            client.previous_track()
        elif action == "seek":
            client.seek_track(position_ms)

        # Set volume if specified
        if volume != 50:  # Only change if not default
            client.volume(volume)

        return {
            "status": "success",
            "message": f"Successfully executed {action} command",
            "data": {"action": action, "position_ms": position_ms, "volume": volume}
        }

    except Exception as e:
        logging.error(f"Error controlling playback: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }

# Define input schemas for each tool
search_spotify_schema = Schema(
    fields=[
        Field("query", str, "The search query to find music content"),
        Field("search_type", str, "Type of search - 'track', 'album', 'artist', or 'playlist'", default="track"),
        Field("limit", int, "Maximum number of results to return", default=10)
    ]
)

get_playback_state_schema = Schema(
    fields=[]  # No input parameters needed
)

control_playback_schema = Schema(
    fields=[
        Field("action", str, "Action to perform - 'play', 'pause', 'next', 'previous', or 'seek'"),
        Field("position_ms", int, "Position to seek to in milliseconds (only for 'seek' action)", default=0),
        Field("volume", int, "Volume level to set (0-100)", default=50)
    ]
)

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for Spotify...")
app = Server("spotify-mcp-server")

# Wrap Spotify functions as ADK FunctionTools with schemas
ADK_SPOTIFY_TOOLS = {
    "search_spotify": FunctionTool(
        func=search_spotify,
        name="search_spotify",
        description="Search Spotify for tracks, albums, artists, or playlists",
        input_schema=search_spotify_schema
    ),
    "get_playback_state": FunctionTool(
        func=get_playback_state,
        name="get_playback_state",
        description="Get current Spotify playback state",
        input_schema=get_playback_state_schema
    ),
    "control_playback": FunctionTool(
        func=control_playback,
        name="control_playback",
        description="Control Spotify playback (play, pause, next, previous, seek)",
        input_schema=control_playback_schema
    ),
}

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_SPOTIFY_TOOLS.items():
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

    if name in ADK_SPOTIFY_TOOLS:
        adk_tool_instance = ADK_SPOTIFY_TOOLS[name]
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
                "status": "error",
                "message": f"Failed to execute tool '{name}': {str(e)}",
                "data": None
            }
            error_text = json.dumps(error_payload)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        logging.warning(f"MCP Server: Tool '{name}' not found/exposed by this server.")
        error_payload = {
            "status": "error",
            "message": f"Tool '{name}' not implemented by this server.",
            "data": None
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
    logging.info("Launching Spotify MCP Server via stdio...")
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