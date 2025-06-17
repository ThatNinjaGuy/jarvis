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

import mcp.server.stdio
from app.jarvis.utils import get_token_path, get_google_credentials, load_environment
from app.config.logging_config import setup_cloud_logging

# Setup cloud logging
setup_cloud_logging()

# YouTube API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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

# --- YouTube API Setup ---
# Define scopes needed for YouTube Data API
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

# Get paths from environment utility
TOKEN_PATH = Path(os.path.expanduser("~/.credentials/youtube_token.json"))

def get_youtube_service():
    """
    Authenticate and create a YouTube service object.

    Returns:
        A YouTube service object or None if authentication fails
    """
    creds = None

    # Check if token exists and is valid
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(TOKEN_PATH.read_text()), SCOPES
            )
            logging.debug("Successfully loaded existing credentials")
        except Exception as e:
            logging.warning(f"Failed to load existing credentials: {e}", exc_info=True)
            # If token is corrupted or invalid, we'll create new credentials
            pass

    # If credentials don't exist or are invalid, refresh or get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Successfully refreshed expired credentials")
            except Exception as e:
                logging.error(f"Failed to refresh credentials: {e}", exc_info=True)
                return None
        else:
            # Get credentials from environment or file
            creds_info = get_google_credentials()
            if not creds_info:
                logging.error("No valid credentials found. Please check configuration.")
                return None

            try:
                flow = InstalledAppFlow.from_client_config(creds_info, SCOPES)
                creds = flow.run_local_server(port=0)
                logging.info("Successfully created new credentials through OAuth flow")
            except Exception as e:
                logging.error(f"Error in authentication flow: {e}", exc_info=True)
                return None

        # Save the credentials for the next run
        try:
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_PATH.write_text(creds.to_json())
            logging.debug(f"Saved credentials to {TOKEN_PATH}")
        except Exception as e:
            logging.warning(f"Failed to save credentials: {e}", exc_info=True)

    # Create and return the YouTube service
    try:
        service = build("youtube", "v3", credentials=creds)
        logging.debug("Successfully created YouTube service")
        return service
    except Exception as e:
        logging.error(f"Failed to create YouTube service: {e}", exc_info=True)
        return None

# --- MCP Tool Functions ---
def search_videos(
    query: str,
    max_results: int = 10,
    order: str = "relevance"
) -> dict:
    """
    Search for YouTube videos based on a query.

    Args:
        query (str): Search query
        max_results (int): Maximum number of results to return (default: 10)
        order (str): Order of results (default: relevance)

    Returns:
        dict: Search results or error details
    """
    try:
        service = get_youtube_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with YouTube API.",
                "videos": []
            }

        # Call the search.list method to retrieve results matching the specified query term
        search_response = service.search().list(
            q=query,
            part="id,snippet",
            maxResults=max_results,
            type="video",
            order=order
        ).execute()

        videos = []
        for search_result in search_response.get("items", []):
            video = {
                "id": search_result["id"]["videoId"],
                "title": search_result["snippet"]["title"],
                "description": search_result["snippet"]["description"],
                "thumbnail": search_result["snippet"]["thumbnails"]["default"]["url"],
                "channel_title": search_result["snippet"]["channelTitle"],
                "published_at": search_result["snippet"]["publishedAt"]
            }
            videos.append(video)

        return {
            "status": "success",
            "message": f"Found {len(videos)} videos",
            "videos": videos
        }

    except HttpError as e:
        logging.error(f"YouTube API error: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"YouTube API error: {str(e)}",
            "videos": []
        }
    except Exception as e:
        logging.error(f"Error searching videos: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error searching videos: {str(e)}",
            "videos": []
        }

def get_video_details(
    video_id: str
) -> dict:
    """
    Get detailed information about a specific video.

    Args:
        video_id (str): YouTube video ID

    Returns:
        dict: Video details or error information
    """
    try:
        service = get_youtube_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with YouTube API."
            }

        # Call the videos.list method to retrieve video details
        video_response = service.videos().list(
            part="snippet,contentDetails,statistics",
            id=video_id
        ).execute()

        if not video_response.get("items"):
            return {
                "status": "error",
                "message": f"Video {video_id} not found."
            }

        video = video_response["items"][0]
        video_details = {
            "id": video["id"],
            "title": video["snippet"]["title"],
            "description": video["snippet"]["description"],
            "published_at": video["snippet"]["publishedAt"],
            "channel_title": video["snippet"]["channelTitle"],
            "thumbnails": video["snippet"]["thumbnails"],
            "duration": video["contentDetails"]["duration"],
            "view_count": video["statistics"].get("viewCount", "0"),
            "like_count": video["statistics"].get("likeCount", "0"),
            "comment_count": video["statistics"].get("commentCount", "0")
        }

        return {
            "status": "success",
            "message": "Video details retrieved successfully",
            "video": video_details
        }

    except HttpError as e:
        logging.error(f"YouTube API error: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"YouTube API error: {str(e)}"
        }
    except Exception as e:
        logging.error(f"Error getting video details: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error getting video details: {str(e)}"
        }

def get_channel_info(
    channel_id: str
) -> dict:
    """
    Get information about a YouTube channel.

    Args:
        channel_id (str): YouTube channel ID

    Returns:
        dict: Channel information or error details
    """
    try:
        service = get_youtube_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with YouTube API."
            }

        # Call the channels.list method to retrieve channel details
        channel_response = service.channels().list(
            part="snippet,contentDetails,statistics",
            id=channel_id
        ).execute()

        if not channel_response.get("items"):
            return {
                "status": "error",
                "message": f"Channel {channel_id} not found."
            }

        channel = channel_response["items"][0]
        channel_info = {
            "id": channel["id"],
            "title": channel["snippet"]["title"],
            "description": channel["snippet"]["description"],
            "custom_url": channel["snippet"].get("customUrl", ""),
            "published_at": channel["snippet"]["publishedAt"],
            "thumbnails": channel["snippet"]["thumbnails"],
            "subscriber_count": channel["statistics"].get("subscriberCount", "0"),
            "video_count": channel["statistics"].get("videoCount", "0"),
            "view_count": channel["statistics"].get("viewCount", "0")
        }

        return {
            "status": "success",
            "message": "Channel information retrieved successfully",
            "channel": channel_info
        }

    except HttpError as e:
        logging.error(f"YouTube API error: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"YouTube API error: {str(e)}"
        }
    except Exception as e:
        logging.error(f"Error getting channel info: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error getting channel info: {str(e)}"
        }

def get_video_comments(
    video_id: str,
    max_results: int = 20
) -> dict:
    """
    Get comments for a specific video.

    Args:
        video_id (str): YouTube video ID
        max_results (int): Maximum number of comments to return (default: 20)

    Returns:
        dict: Video comments or error details
    """
    try:
        service = get_youtube_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with YouTube API.",
                "comments": []
            }

        # Call the commentThreads.list method to retrieve video comments
        comments_response = service.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_results,
            textFormat="plainText"
        ).execute()

        comments = []
        for item in comments_response.get("items", []):
            comment = item["snippet"]["topLevelComment"]["snippet"]
            comment_info = {
                "id": item["id"],
                "text": comment["textDisplay"],
                "author": comment["authorDisplayName"],
                "published_at": comment["publishedAt"],
                "like_count": comment["likeCount"],
                "reply_count": item["snippet"]["totalReplyCount"]
            }
            comments.append(comment_info)

        return {
            "status": "success",
            "message": f"Found {len(comments)} comments",
            "comments": comments
        }

    except HttpError as e:
        logging.error(f"YouTube API error: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"YouTube API error: {str(e)}",
            "comments": []
        }
    except Exception as e:
        logging.error(f"Error getting video comments: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error getting video comments: {str(e)}",
            "comments": []
        }

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for YouTube...")
app = Server("youtube-mcp-server")

# Wrap YouTube utility functions as ADK FunctionTools
ADK_YOUTUBE_TOOLS = {
    "search_videos": FunctionTool(func=search_videos),
    "get_video_details": FunctionTool(func=get_video_details),
    "get_channel_info": FunctionTool(func=get_channel_info),
    "get_video_comments": FunctionTool(func=get_video_comments)
}

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_YOUTUBE_TOOLS.items():
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

    if name in ADK_YOUTUBE_TOOLS:
        adk_tool_instance = ADK_YOUTUBE_TOOLS[name]
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
    logging.info("Launching YouTube MCP Server via stdio...")
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