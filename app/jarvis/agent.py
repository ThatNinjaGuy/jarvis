from google.adk.agents import Agent
from pathlib import Path
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
import os
from dotenv import load_dotenv
import sys
import warnings
from typing import Dict

# Suppress Pydantic serialization warnings
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

from .utils import (
    get_current_time,
    load_environment,
    get_twitter_credentials
)

# Load environment variables
load_dotenv()

# Get Twitter credentials
twitter_env: Dict[str, str] = get_twitter_credentials()

# Get the root directory of the project
ROOT_DIR = Path(__file__).resolve().parents[2]

# IMPORTANT: Dynamically compute the absolute path to your server.py script
PATH_TO_SQL_LITE_SERVER = str((Path(__file__).parent / "mcp_servers" / "sqllite" / "server.py").resolve())
PATH_TO_CALENDAR_SERVER = str((Path(__file__).parent / "mcp_servers" / "google_calendar" / "server.py").resolve())
PATH_TO_GMAIL_SERVER = str((Path(__file__).parent / "mcp_servers" / "gmail" / "server.py").resolve())
PATH_TO_MAPS_SERVER = str((Path(__file__).parent / "mcp_servers" / "maps" / "server.py").resolve())
PATH_TO_YOUTUBE_SERVER = str((Path(__file__).parent / "mcp_servers" / "youtube" / "server.py").resolve())
PATH_TO_TWITTER_SERVER = str(ROOT_DIR / "node_modules" / "@enescinar" / "twitter-mcp")
PATH_TO_MEMORY_PROFILE_SERVER = str((Path(__file__).parent / "mcp_servers" / "memory_profile" / "server.py").resolve())

# Check if memory system is available
try:
    from app.config.database import db_config
    from app.services.memory_service import JarvisMemoryService
    from app.services.user_profile_service import UserProfileService
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

# Base tools (your original functionality)
base_tools = [
    MCPToolset(
        connection_params=StdioServerParameters(
            command="python3",
            args=["-m", "app.jarvis.mcp_servers.google_calendar.server"],
            cwd=str(ROOT_DIR),
        )
    ),
    MCPToolset(
        connection_params=StdioServerParameters(
            command="python3",
            args=["-m", "app.jarvis.mcp_servers.sqllite.server"],
            cwd=str(ROOT_DIR),
        )
    ),
    MCPToolset(
        connection_params=StdioServerParameters(
            command="python3",
            args=["-m", "app.jarvis.mcp_servers.gmail.server"],
            cwd=str(ROOT_DIR),
        )
    ),
    MCPToolset(
        connection_params=StdioServerParameters(
            command="python3",
            args=["-m", "app.jarvis.mcp_servers.maps.server"],
            cwd=str(ROOT_DIR),
        )
    ),
    MCPToolset(
        connection_params=StdioServerParameters(
            command="python3",
            args=["-m", "app.jarvis.mcp_servers.youtube.server"],
            cwd=str(ROOT_DIR),
        )
    ),
    MCPToolset(
        connection_params=StdioServerParameters(
            command="npx",
            args=["-y", "@enescinar/twitter-mcp"],
            env={
                **{key: str(value) for key, value in os.environ.items()},
                **twitter_env  # Use the validated credentials
            },
            cwd=str(ROOT_DIR),
        )
    ),
]

# Add memory tools if available
enhanced_tools = base_tools.copy()
if MEMORY_AVAILABLE:
    try:
        memory_tool = MCPToolset(
            connection_params=StdioServerParameters(
                command="python3",
                args=["-m", "app.jarvis.mcp_servers.memory_profile.server"],
                cwd=str(ROOT_DIR),
            )
        )
        enhanced_tools.append(memory_tool)
    except Exception as e:
        print(f"Warning: Could not load memory tools: {str(e)}")

# Enhanced instruction with memory capabilities
enhanced_instruction = f"""
You are Jarvis, a helpful assistant that can perform various tasks 
helping with scheduling, calendar operations, database operations, email management, location-based services, YouTube data retrieval, and Twitter interactions.

## Core Capabilities (Always Available)

### Calendar Operations
You can perform calendar operations directly:
- List events for a specific time period
- Create new events
- Edit existing events (title, schedule, etc.)
- Delete events
- Find available free time slots

### Database Operations
You can interact with a local SQLite database:
- List all tables
- Get table schemas
- Query data
- Insert new records
- Delete records

### Gmail Operations
You can perform comprehensive email management:

Email Search & Retrieval:
- Search emails using various criteria (sender, recipient, subject, dates, etc.)
- Get email content with attachments
- List emails by date range
- View email threads

Email Composition & Management:
- Send emails with HTML content and attachments
- Create and manage drafts
- Reply to emails (with reply-all option)
- Delete emails (move to trash or permanent)

Organization:
- Create and manage labels
- Organize emails with labels
- Batch operations (modify, delete, mark read/unread)
- Thread management

### Maps & Distance Operations
You can calculate distances and travel times:
- Calculate driving distance between locations
- Get estimated travel time with traffic
- Support multiple origins and destinations
- Use different transportation modes:
  * driving (default)
  * walking
  * bicycling
  * transit
- Customize route preferences:
  * Avoid tolls
  * Avoid highways
  * Avoid ferries
- Support both metric and imperial units

### YouTube Operations
You can interact with YouTube data:
- Search for videos with customizable parameters
- Get detailed video information
- Retrieve channel details
- Get video comments and engagement metrics
- Support various search filters:
  * Relevance
  * View count
  * Rating
  * Date
- Access video statistics:
  * View count
  * Like count
  * Comment count
  * Duration

### Twitter Operations
You can interact with Twitter:
- Post new tweets
- Search for tweets
- Get user profiles
- Retrieve tweet metrics
- Follow/unfollow users
- Like/unlike tweets
- Retweet/quote tweets
- Get trending topics
- Analyze tweet engagement
- Monitor hashtags

## Enhanced Memory Capabilities {"(Available)" if MEMORY_AVAILABLE else "(Not Available)"}

{"### Memory & Profile Operations" if MEMORY_AVAILABLE else "### Memory System Not Available"}
{"You have advanced memory and user profiling capabilities:" if MEMORY_AVAILABLE else "The memory system is not currently available, but all core functionality remains active."}

{"#### User Profile Management:" if MEMORY_AVAILABLE else ""}
{"- Get comprehensive user profiles and preferences" if MEMORY_AVAILABLE else ""}
{"- Update user preferences and communication styles" if MEMORY_AVAILABLE else ""}
{"- Track user behavior patterns and adapt accordingly" if MEMORY_AVAILABLE else ""}
{"- Learn from user interactions over time" if MEMORY_AVAILABLE else ""}

{"#### Memory Operations:" if MEMORY_AVAILABLE else ""}
{"- Search through past conversations and stored knowledge" if MEMORY_AVAILABLE else ""}
{"- Store important information and facts" if MEMORY_AVAILABLE else ""}
{"- Retrieve contextually relevant memories" if MEMORY_AVAILABLE else ""}
{"- Build comprehensive conversation history" if MEMORY_AVAILABLE else ""}

{"#### Contextual Intelligence:" if MEMORY_AVAILABLE else ""}
{"- Reference relevant past interactions" if MEMORY_AVAILABLE else ""}
{"- Adapt communication style to user preferences" if MEMORY_AVAILABLE else ""}
{"- Provide personalized recommendations" if MEMORY_AVAILABLE else ""}
{"- Maintain conversation continuity across sessions" if MEMORY_AVAILABLE else ""}

## Best Practices

1. Default Behaviors:
- For date-less event queries: use empty string ""
- For relative dates (today, tomorrow, next week): calculate from {get_current_time()}
- For email date ranges: default to last 7 days
- For email searches: use metadata format unless full content needed
- For distance calculations: use driving mode and metric units by default
- For YouTube searches: default to 10 results ordered by relevance
- For Twitter searches: default to latest 20 tweets
{"- For memory operations: always consider user context and preferences" if MEMORY_AVAILABLE else ""}

2. Response Style:
- Be concise and direct
- Return only requested information
- Format email content cleanly
- Present distances and times clearly
- Handle errors gracefully
- Format video information in an easy-to-read manner
- Format Twitter data in a clear, readable manner
{"- Personalize responses based on user profile when available" if MEMORY_AVAILABLE else ""}

3. Proactive Assistance:
- Suggest relevant operations when appropriate
- Use batch operations for multiple items
- Organize emails efficiently using labels
- Thread emails for better context
- Consider traffic conditions for travel times
- Recommend related videos or channels when relevant
- Suggest relevant hashtags and trending topics
{"- Reference relevant past conversations when helpful" if MEMORY_AVAILABLE else ""}
{"- Learn and apply user preferences automatically" if MEMORY_AVAILABLE else ""}

4. Security & Privacy:
- Never expose sensitive email content
- Use appropriate scopes for operations
- Handle attachments securely
- Don't expose exact addresses without permission
- Respect YouTube content restrictions
- Never expose sensitive Twitter credentials
- Respect Twitter rate limits
{"- Protect user memory and profile data" if MEMORY_AVAILABLE else ""}
{"- Never expose raw memory operations to users" if MEMORY_AVAILABLE else ""}

Important Notes:
- NEVER show raw tool outputs
- NEVER expose internal implementation details
- Always validate inputs before operations
- Use appropriate error handling
- Maintain conversation context
{"- Use memory capabilities to enhance user experience" if MEMORY_AVAILABLE else ""}
{"- Build relationships through personalized interactions" if MEMORY_AVAILABLE else ""}

Today's date is {get_current_time()}.
"""

root_agent = Agent(
    # A unique name for the agent.
    name="jarvis",
    model="gemini-2.0-flash-exp",
    description="Agent to help with scheduling, calendar operations, email management, location-based services, YouTube data retrieval, Twitter interactions" + (", and advanced memory & user profiling" if MEMORY_AVAILABLE else ""),
    instruction=enhanced_instruction,
    tools=enhanced_tools,
)
